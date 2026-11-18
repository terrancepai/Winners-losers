"""Turn the database into site/data/latest.json, the only file the website reads.

The pipeline does the finance math. The website only multiplies each portfolio's
weights by the asset returns in this file and draws the result.

Two kinds of "shock" go to the site:
  - week:  the last 5 trading days, every market moving at once
  - mover: one thing that moved portfolios, on its own. Either a company inside the
           stock funds (its move x its weight in each fund), or a market force:
           interest rates, bitcoin, international stocks, or the rest of the U.S. market.
The site shows the week, then the 4 movers that hit the selected portfolio hardest.
"""
import json
import os
import sys
from datetime import date as Date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import config
import db

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "site", "data", "latest.json")
WINDOW = 5  # trading days


# ---------- reading the database ----------
def closes(con):
    """{symbol: {date: close}} and the set of not-yet-final (date, symbol)."""
    data, live = {}, set()
    for r in con.execute("SELECT symbol, date, close, final FROM daily_close"):
        data.setdefault(r["symbol"], {})[r["date"]] = r["close"]
        if not r["final"]:
            live.add((r["date"], r["symbol"]))
    return data, live


def yields(con):
    out = {}
    for r in con.execute("SELECT series, date, value FROM yields"):
        out.setdefault(r["series"], {})[r["date"]] = r["value"]
    return out


def at_or_before(series, day):
    """Value on `day`, or the most recent one before it (weekends, holidays, missing data)."""
    if not series:
        return None
    if day in series:
        return series[day]
    earlier = [d for d in series if d <= day]
    return series[max(earlier)] if earlier else None


def change(series, start, end):
    p0, p1 = at_or_before(series, start), at_or_before(series, end)
    return (p1 / p0 - 1) if p0 and p1 else None


def anchor_symbol():
    return next(a["symbol"] for a in config.ASSETS if a["id"] == "sp")


def window(px):
    """Base close and the last WINDOW trading days after it (rolling 5 days)."""
    days = sorted(px.get(anchor_symbol(), {}))
    if len(days) < 2:
        return None, []
    days = days[-(WINDOW + 1):]
    return days[0], days[1:]


def label(day):
    d = Date.fromisoformat(day)
    return d.strftime("%a %b ") + str(d.day)


def short_label(day):
    d = Date.fromisoformat(day)
    return d.strftime("%a ") + str(d.day)


def pct_move(lbl, r):
    return {"label": lbl, "value": round((r or 0) * 100, 2), "unit": "%"}


# ---------- movers ----------
def mover_pool(px, yl, base, end):
    """Everything that could have moved a portfolio over the window, each on its own."""
    fund = {a["id"]: (change(px.get(a["symbol"]), base, end) or 0.0) for a in config.ASSETS}
    pool = []
    explained = {}  # how much of each stock fund's move its top holdings explain
    for sym, h in config.HOLDINGS.items():
        r = change(px.get(sym), base, end)
        if r is None:
            continue
        returns = {fid: w / 100 * r for fid, w in h["w"].items()}
        for fid, v in returns.items():
            explained[fid] = explained.get(fid, 0) + v
        pool.append({"id": sym, "kind": "company", "name": h["name"], "symbol": sym, "move": r,
                     "move_label": f"{sym} {r * 100:+.2f}%", "chips": [pct_move(h["name"], r)],
                     "weights": h["w"], "returns": returns})

    # the rest of each U.S. stock fund, after taking out the companies above
    rest = {fid: fund[fid] - explained.get(fid, 0) for fid in ("sp", "ustm", "ndx")}
    top_w = sum(h["w"].get("sp", 0) for h in config.HOLDINGS.values()) / 100
    rest_move = rest["sp"] / (1 - top_w) if top_w < 1 else 0
    pool.append({"id": "rest", "kind": "market", "name": "The rest of the U.S. market",
                 "move": rest_move, "move_label": f"Other S&P 500 stocks {rest_move * 100:+.2f}%",
                 "chips": [pct_move("Other S&P 500 stocks", rest_move)], "returns": rest})

    bonds = {a["id"]: fund[a["id"]] for a in config.ASSETS if a["kind"] == "bd"}
    y0, y1 = at_or_before(yl.get("r10"), base), at_or_before(yl.get("r10"), end)
    r10 = (y1 - y0) * 100 if y0 is not None and y1 is not None else None
    pool.append({"id": "rates", "kind": "market", "name": "Interest rates", "move": fund["usb"],
                 "move_label": (f"10-yr yield {r10:+.1f} bp" if r10 is not None else f"U.S. bonds {fund['usb'] * 100:+.2f}%"),
                 "chips": ([{"label": "10-yr yield", "value": round(r10, 1), "unit": "bp"}] if r10 is not None else []) +
                          [pct_move("U.S. bonds", fund["usb"]), pct_move("Intl bonds", fund["intlb"]), pct_move("Short Treasuries", fund["short"])],
                 "returns": bonds})
    pool.append({"id": "btc", "kind": "market", "name": "Bitcoin", "move": fund["btc"],
                 "move_label": f"Bitcoin {fund['btc'] * 100:+.2f}%", "chips": [pct_move("Bitcoin", fund["btc"])],
                 "returns": {"btc": fund["btc"]}})
    pool.append({"id": "intl", "kind": "market", "name": "International stocks", "move": fund["intl"],
                 "move_label": f"VXUS {fund['intl'] * 100:+.2f}%", "chips": [pct_move("International stocks (VXUS)", fund["intl"])],
                 "returns": {"intl": fund["intl"]}})
    return pool, fund


def biggest_impact(m):
    """The largest hit this mover gives any model portfolio (used to pick which get news)."""
    return max(abs(sum(w / 100 * m["returns"].get(k, 0) for k, w in p["w"].items())) for p in config.PORTFOLIOS)


# ---------- building the file ----------
def main(con=None, out_path=OUT, demo=False):
    con = con or db.connect()
    px, live = closes(con)
    yl = yields(con)
    base, days = window(px)
    if not days:
        print("Not enough price history yet. Run backfill.py or wait for a few price runs.")
        return None
    end, anchor = days[-1], anchor_symbol()
    is_live = (end, anchor) in live
    pool, fund = mover_pool(px, yl, base, end)

    stories = {}
    for r in con.execute("SELECT mover_id, headline, story, source, url, date FROM mover_stories WHERE date >= ? ORDER BY date",
                         (base,)):
        stories[r["mover_id"]] = dict(r)  # latest wins

    shocks = [{
        "id": "week", "kind": "week", "name": "How you did this week",
        "date": f"Past 5 days · {short_label(days[0])} – {short_label(end)}" + (" · live" if is_live else ""),
        "card": "Everything moving at once, measured with real fund prices.",
        "story": "Your portfolio over the past five trading days, with every market moving together. "
                 "The four boxes next to this one are what moved your kind of portfolio most.",
        "moves": [pct_move("S&P 500", fund["sp"]), pct_move("Nasdaq-100", fund["ndx"]), pct_move("Intl stocks", fund["intl"]),
                  pct_move("U.S. bonds", fund["usb"]), pct_move("Bitcoin", fund["btc"])],
        "returns": fund,
    }]
    for m in pool:
        st = stories.get(m["id"])
        verb = "rose" if m["move"] > 0 else "fell"
        fallback = (f"{m['name']} {verb} {abs(m['move']) * 100:.1f}% over the past five days."
                    if m["id"] != "rates" else f"U.S. bonds {verb} {abs(m['move']) * 100:.1f}% as yields moved.")
        shocks.append({
            "id": m["id"], "kind": "mover", "mover_kind": m["kind"], "name": m["name"], "symbol": m.get("symbol"),
            "date": m["move_label"],
            "card": st["headline"] if st else fallback,
            "story": (st["story"] if st and st.get("story") else fallback + " The news summary appears after the next market close."),
            "source": st.get("source") if st else None, "url": st.get("url") if st else None,
            "moves": m["chips"],
            "weights": m.get("weights"),
            "returns": m["returns"],
        })

    # 5-day race: buy at the base close, hold through the window
    xdays = [base] + days
    paths = []
    for p in config.PORTFOLIOS:
        path = []
        for d in xdays:
            v = sum(w / 100 * (1 + (change(px.get(a["symbol"]), base, d) or 0)) for a in config.ASSETS for k, w in p["w"].items() if k == a["id"])
            path.append(round(v - sum(p["w"].values()) / 100, 6))
        paths.append(path)

    # ticker strip: change over the same 5 days
    ticker = []
    for lbl, sym, _ in config.TICKER:
        s = px.get(sym, {})
        p0, p1 = at_or_before(s, base), at_or_before(s, end)
        if p0 and p1:
            ticker.append({"name": lbl, "value": p1, "change": round((p1 / p0 - 1) * 100, 2), "unit": "%"})
    y0, y1 = at_or_before(yl.get("r10"), base), at_or_before(yl.get("r10"), end)
    if y0 is not None and y1 is not None:
        ticker.insert(4, {"name": "10-yr yield", "value": y1, "change": round((y1 - y0) * 100, 1), "unit": "bp", "is_rate": True})

    story_date = con.execute("SELECT MAX(date) FROM stories").fetchone()[0]
    top = [dict(r) for r in con.execute("SELECT kicker, headline, summary, tickers, source, url FROM stories WHERE date = ? ORDER BY rank", (story_date,))] if story_date else []
    last = con.execute("SELECT MAX(ts) FROM quotes").fetchone()[0]

    data = {
        "demo": demo,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_quote": last,
        "price_day": end,
        "price_day_live": is_live,
        "week_label": f"Past 5 trading days, {label(days[0])} – {label(end)}",
        "x_labels": [short_label(d) for d in xdays],
        "assets": [{k: a[k] for k in ("id", "name", "symbol", "kind")} |
                   ({"dv01_years": a["D"] * a["beta"]} if a["kind"] == "bd" else {}) for a in config.ASSETS],
        "holdings": [{"symbol": s, "name": h["name"], "w": h["w"]} for s, h in config.HOLDINGS.items()],
        "portfolios": [{"name": p["name"], "tag": p["tag"], "sub": p["sub"], "w": p["w"], "path": paths[i]}
                       for i, p in enumerate(config.PORTFOLIOS)],
        "shocks": shocks,
        "ticker": ticker,
        "stories": top,
        "stories_date": story_date,
        "stories_updated": con.execute("SELECT MAX(ts) FROM runs WHERE job = 'news-top' OR (job = 'news' AND ok = 1)").fetchone()[0],
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=1)
    print(f"Wrote {out_path}: {len(shocks) - 1} movers, {len(xdays)} days, {len(top)} stories.")
    return data


if __name__ == "__main__":
    main()
