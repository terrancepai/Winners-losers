"""Runs once a day after the close: pick the day's top market stories and summarize them with Claude.

Claude only sees headlines and short blurbs from Finnhub's news feed, and may only
pick from that list. Links always come from the feed, never from the model.

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

PROMPT = """You are the markets editor of an investor dashboard. Below are today's news items as JSON.

Pick the 5 items that matter most for ordinary investors holding index funds, target-date funds,
tech funds, bonds or bitcoin. Prefer stories that moved markets, interest rates or big companies.

Rules:
- Use ONLY facts stated in the items. Do not add numbers, names or events that are not there.
- Write in your own words. No quotes from the source text.
- If something is an allegation or a report, say so ("reported", "alleged").
- Headline: at most 14 words. Summary: at most 2 short sentences.
- kicker: one or two words naming the topic (e.g. "Nvidia", "Rates", "Oil").
- tickers: up to 3 tickers or markets it moved (e.g. "NVDA", "10-yr yield", "Oil").
- day_headline: at most 8 words naming the single biggest market driver today.

Reply with JSON only, in exactly this shape:
{"day_headline": "...", "stories": [{"id": 0, "kicker": "...", "headline": "...", "summary": "...", "tickers": ["..."]}]}

Items:
"""


def parse_json(text):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def main():
    fkey = os.environ.get("FINNHUB_API_KEY")
    if not fkey or not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set FINNHUB_API_KEY and ANTHROPIC_API_KEY.")
    now = datetime.now(timezone.utc)
    ny = now.astimezone(ZoneInfo(config.TIMEZONE))
    today, ts = ny.date().isoformat(), now.strftime("%Y-%m-%dT%H:%M:%SZ")
    con = db.connect()

    cutoff = time.time() - 30 * 3600
    raw = [n for n in sources.finnhub_news(fkey) if n.get("datetime", 0) >= cutoff and n.get("headline")]
    items = [{"id": i, "source": n.get("source", ""), "headline": n["headline"],
              "blurb": (n.get("summary") or "")[:300], "related": n.get("related", "")}
             for i, n in enumerate(raw[:40])]
    if not items:
        db.log_run(con, ts, "news", ok=False, note="no news items")
        return

    try:
        out = parse_json(sources.claude(PROMPT + json.dumps(items, ensure_ascii=False), config.CLAUDE_MODEL))
    except Exception as e:
        db.log_run(con, ts, "news", ok=False, note=f"Claude: {e}")
        raise

    con.execute("DELETE FROM stories WHERE date = ?", (today,))
    rank = 0
    for s in out.get("stories", [])[:5]:
        i = s.get("id")
        if not isinstance(i, int) or not 0 <= i < len(items):
            continue  # ignore anything that does not point at a real item
        src = raw[i]
        rank += 1
        con.execute("INSERT INTO stories VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            today, rank, s.get("kicker", "")[:30], s.get("headline", "")[:140], s.get("summary", "")[:400],
            ",".join(s.get("tickers", [])[:3]), src.get("source", ""), src.get("url", "")))
    if out.get("day_headline"):
        con.execute("INSERT OR REPLACE INTO day_headlines (date, headline) VALUES (?, ?)",
                    (today, out["day_headline"][:80]))
    con.commit()
    db.log_run(con, ts, "news", ok=True, note=f"{rank} stories")
    export.main(con)
    print(f"Saved {rank} stories for {today}.")


if __name__ == "__main__":
    main()
