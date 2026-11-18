"""Runs once a day after the close. Two jobs:

1. Top market stories: Claude picks the day's 5 most important headlines and summarizes them.
2. Mover stories: for each company or market force that moved a model portfolio most over
   the past 5 days, Claude explains why it moved, using that company's own news.

Claude only sees headlines and short blurbs from Finnhub's feeds and may only pick from them.
Links always come from the feed, never from the model.

Run it yourself with:  FINNHUB_API_KEY=xxx ANTHROPIC_API_KEY=yyy python pipeline/update_news.py
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
import config
import db
import export
import sources

RULES = """Rules:
- Use ONLY facts stated in the items. Do not add numbers, names or events that are not there.
- Write in your own words. No quotes from the source text.
- If something is an allegation or a report, say so ("reported", "alleged").
"""

TOP_PROMPT = """You are the markets editor of an investor dashboard. Below are today's news items as JSON.

Pick the 5 items that matter most for ordinary investors holding index funds, target-date funds,
tech funds, bonds or bitcoin. Prefer stories that moved markets, interest rates or big companies.
If two items cover the same story, pick only one. When stories are equally important, mix outlets.

""" + RULES + """- Headline: at most 14 words. Summary: at most 2 short sentences.
- kicker: one or two words naming the topic (e.g. "Nvidia", "Rates", "Oil").
- tickers: up to 3 tickers or markets it moved (e.g. "NVDA", "10-yr yield", "Oil").
- day_headline: at most 8 words naming the single biggest market driver today.

Reply with JSON only, in exactly this shape:
{"day_headline": "...", "stories": [{"id": 0, "kicker": "...", "headline": "...", "summary": "...", "tickers": ["..."]}]}

Items:
"""

MOVER_PROMPT = """You are the markets editor of an investor dashboard. Each "mover" below moved investors'
portfolios over the past five trading days. For each one, explain WHY it moved, using its news items.

""" + RULES + """- If the items don't explain the move, say so plainly (e.g. "No single story explains the drop; it fell with other chip stocks.") and only mention what the items support.
- headline: at most 12 words, says which way it moved and the main reason.
- story: at most 2 short sentences.
- source: the id of the one item that best supports the story, or null.

Reply with JSON only, in exactly this shape:
{"movers": [{"id": "NVDA", "headline": "...", "story": "...", "source": "NVDA-2"}]}

Movers:
"""


def parse_json(text):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def top_stories(con, today, general):
    items = [{"id": i, "source": n.get("source", ""), "headline": n["headline"],
              "blurb": (n.get("summary") or "")[:300], "related": n.get("related", "")}
             for i, n in enumerate(general[:40])]
    if not items:
        return 0
    out = parse_json(sources.claude(TOP_PROMPT + json.dumps(items, ensure_ascii=False), config.CLAUDE_MODEL))
    con.execute("DELETE FROM stories WHERE date = ?", (today,))
    rank = 0
    for s in out.get("stories", [])[:5]:
        i = s.get("id")
        if not isinstance(i, int) or not 0 <= i < len(items):
            continue  # ignore anything that does not point at a real item
        src = general[i]
        rank += 1
        con.execute("INSERT INTO stories VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            today, rank, s.get("kicker", "")[:30], s.get("headline", "")[:140], s.get("summary", "")[:400],
            ",".join(s.get("tickers", [])[:3]), src.get("source", ""), src.get("url", "")))
    if out.get("day_headline"):
        con.execute("INSERT OR REPLACE INTO day_headlines (date, headline) VALUES (?, ?)", (today, out["day_headline"][:80]))
    return rank


def pick_movers(pool):
    """Every mover that is in some model portfolio's top 4. That's all the site can show."""
    chosen = {}
    for p in config.PORTFOLIOS:
        ranked = sorted(pool, key=lambda m: -abs(sum(w / 100 * m["returns"].get(k, 0) for k, w in p["w"].items())))
        for m in ranked[:4]:
            chosen[m["id"]] = m
    return list(chosen.values())


def mover_stories(con, today, general, fkey):
    px, _ = export.closes(con)
    yl = export.yields(con)
    base, days = export.window(px)
    if not days:
        return 0
    pool, _ = export.mover_pool(px, yl, base, days[-1])
    movers = pick_movers(pool)

    lookup, payload = {}, []
    general_items = []
    for i, n in enumerate(general[:30]):
        key = f"N-{i}"
        lookup[key] = n
        general_items.append({"id": key, "source": n.get("source", ""), "headline": n["headline"], "blurb": (n.get("summary") or "")[:200]})
    for m in movers:
        entry = {"id": m["id"], "name": m["name"], "move_over_5_days": m["move_label"]}
        if m["kind"] == "company":
            try:
                news = sources.finnhub_company_news(m["symbol"], base, today, fkey)
            except Exception as e:
                print(f"{m['symbol']} news: {e}")
                news = []
            time.sleep(1.1)
            # prefer the four outlets; use other sources only if none of them covered it
            mine = [n | {"source": sources.outlet(n.get("source"))} for n in news if sources.outlet(n.get("source"))]
            news = sorted(mine or news, key=lambda n: -n.get("datetime", 0))[:8]
            entry["items"] = []
            for j, n in enumerate(news):
                key = f"{m['id']}-{j}"
                lookup[key] = n
                entry["items"].append({"id": key, "source": n.get("source", ""), "headline": n.get("headline", ""),
                                       "blurb": (n.get("summary") or "")[:200]})
        else:
            entry["items"] = "use the market news items below"
        payload.append(entry)

    prompt = MOVER_PROMPT + json.dumps(payload, ensure_ascii=False) + "\n\nMarket news items (may also cover the companies above):\n" + json.dumps(general_items, ensure_ascii=False)
    out = parse_json(sources.claude(prompt, config.CLAUDE_MODEL, max_tokens=2500))
    valid = {m["id"] for m in movers}
    saved = 0
    for s in out.get("movers", []):
        if s.get("id") not in valid or not s.get("headline"):
            continue
        src = lookup.get(s.get("source") or "")
        con.execute("INSERT OR REPLACE INTO mover_stories VALUES (?, ?, ?, ?, ?, ?)", (
            today, s["id"], s["headline"][:120], (s.get("story") or "")[:400],
            src.get("source", "") if src else None, src.get("url", "") if src else None))
        saved += 1
    return saved


def main():
    fkey = os.environ.get("FINNHUB_API_KEY")
    if not fkey or not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set FINNHUB_API_KEY and ANTHROPIC_API_KEY.")
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(config.TIMEZONE)).date().isoformat()
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    con = db.connect()

    # Top stories come from Reuters, CNBC, Yahoo Finance and Bloomberg. If those can't be reached,
    # fall back to every source in Finnhub's general feed so the section never goes stale.
    cutoff = time.time() - 30 * 3600
    general = [n for n in sources.outlet_news(fkey) if n.get("datetime", 0) >= cutoff]
    print("Items by outlet:", {o: sum(n["source"] == o for n in general) for o in sources.OUTLETS})
    if len(general) < 5:
        print("::warning::Fewer than 5 recent items from Reuters, CNBC, Yahoo Finance and Bloomberg; adding other sources.")
        try:
            general += [n for n in sources.finnhub_news(fkey) if n.get("datetime", 0) >= cutoff and n.get("headline")]
        except Exception as e:
            print(f"Finnhub news: {e}")

    notes, ok = [], True
    for name, job in (("top stories", lambda: top_stories(con, today, general)),
                      ("mover stories", lambda: mover_stories(con, today, general, fkey))):
        try:
            notes.append(f"{name}: {job()}")
            con.commit()
        except Exception as e:  # one failing doesn't stop the other
            ok = False
            notes.append(f"{name} failed: {e}")
    db.log_run(con, ts, "news", ok=ok, note="; ".join(notes))
    export.main(con)
    print(*notes, sep="\n")
    if not ok:  # shows as a yellow warning in the Actions tab; the site still updates
        print("::warning::Part of the news job failed: " + "; ".join(n for n in notes if "failed" in n))


if __name__ == "__main__":
    main()
