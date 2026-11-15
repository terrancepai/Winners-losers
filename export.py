"""Turn the database into site/data/latest.json, the only file the website reads.

The pipeline does the finance math (returns, paths, shocks). The website only multiplies
each portfolio's weights by the asset returns in this file and draws the result.
"""
import json
import os
import sys
from datetime import date as Date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import config
import db

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "site", "data", "latest.json")
SHOCKS_FILE = os.path.join(ROOT, "content", "shocks.json")


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


# ---------- the week ----------
def week_window(trading_days):
    """Base close (last day before this week's Monday) and this week's trading days."""
    latest = trading_days[-1]
    monday = (Date.fromisoformat(latest) - timedelta(days=Date.fromisoformat(latest).weekday())).isoformat()
    week = [d for d in trading_days if d >= monday]
    before = [d for d in trading_days if d < monday]
    base = before[-1] if before else week[0]
    if base == week[0]:
        week = week[1:]
    return base, week


def asset_return(px, a, start, end):
    s = px.get(a["symbol"], {})
    p0, p1 = at_or_before(s, start), at_or_before(s, end)
    return (p1 / p0 - 1) if p0 and p1 else 0.0


def label(day):
    d = Date.fromisoformat(day)
    return d.strftime("%a %b ") + str(d.day)


def short_label(day):
    d = Date.fromisoformat(day)
    return d.strftime("%a ") + str(d.day)


def pct_move(lbl, r, est=False):
    return {"label": lbl, "value": round(r * 100, 2), "unit": "%", "est": est}


def bp_move(lbl, v, est=False):
    return {"label": lbl, "value": round(v, 1), "unit": "bp", "est": est}


def auto_moves(px, yl, start, end):
    """The chips shown under a shock: what the main markets did."""
    by_id = {a["id"]: a for a in config.ASSETS}
    moves = [pct_move("S&P 500", asset_return(px, by_id["sp"], start, end)),
             pct_move("Nasdaq-100", asset_return(px, by_id["ndx"], start, end)),
             pct_move("Intl stocks", asset_return(px, by_id["intl"], start, end)),
             pct_move("U.S. bonds", asset_return(px, by_id["usb"], start, end)),
             pct_move("Bitcoin", asset_return(px, by_id["btc"], start, end))]
    for key, lbl in (("r2", "2-yr yield"), ("r10", "10-yr yield")):
        y0, y1 = at_or_before(yl.get(key), start), at_or_before(yl.get(key), end)
        if y0 is not None and y1 is not None:
            moves.append(bp_move(lbl, (y1 - y0) * 100))
    return moves


# ---------- curated "what if" shocks ----------
def curated_returns(sh):
    m = sh.get("moves", {})
    out = {}
    for a in config.ASSETS:
        if a["kind"] == "bd":
            dy = m.get(a["key"], 0) / 10000 * a["beta"]
            ds = m.get("s", 0) / 10000
            out[a["id"]] = -a["D"] * dy + 0.5 * a["C"] * dy * dy - a["SD"] * ds
        elif sh.get("isolate") == "nvda":
            out[a["id"]] = a.get("nvda_w", 0) * m.get("nvda", 0) / 100
        elif sh.get("isolate") == "rates":
            out[a["id"]] = 0.0
        else:
            out[a["id"]] = m.get(a["factor"], 0) / 100
    return out


CURATED_LABELS = {"nvda": ("Nvidia", "%"), "r2": ("2-yr yield", "bp"), "r10": ("10-yr yield", "bp"), "s": ("Corp. spreads", "bp"),
                  "us": ("U.S. stocks", "%"), "ndx": ("Nasdaq-100", "%"), "intl": ("Intl stocks", "%"), "btc": ("Bitcoin", "%")}


def load_curated(today):
    if not os.path.exists(SHOCKS_FILE):
        return []
    with open(SHOCKS_FILE) as f:
        items = json.load(f)
    out = []
    for sh in items:
        if sh.get("show_until") and sh["show_until"] < today:
            continue  # stale news drops off on its own
        est = set(sh.get("est", []))
        moves = [{"label": CURATED_LABELS[k][0], "value": v, "unit": CURATED_LABELS[k][1], "est": k in est}
                 for k, v in sh.get("moves", {}).items() if k in CURATED_LABELS]
        out.append({"id": sh["id"], "kind": "curated", "name": sh["name"], "date": sh.get("date", ""),
                    "card": sh.get("card", ""), "story": sh.get("story", ""), "moves": moves,
                    "sources": sh.get("sources", []), "returns": curated_returns(sh)})
    return out


# ---------- building the file ----------
def main(con=None, out_path=OUT, demo=False):
    con = con or db.connect()
    px, live = closes(con)
    yl = yields(con)
    anchor = next((a["symbol"] for a in config.ASSETS if a["id"] == "sp"), "VOO")
    trading_days = sorted(px.get(anchor, {}))
    if len(trading_days) < 2:
        print("Not enough price history yet. Run backfill.py or wait for a few price runs.")
        return None

    base, week = week_window(trading_days)
    heads = {r["date"]: r["headline"] for r in con.execute("SELECT date, headline FROM day_headlines")}
    today = trading_days[-1]

    shocks = []
    if week:
        shocks.append({"id": "week", "kind": "week", "name": "How you did this week",
                       "date": f"{label(week[0])} – {label(week[-1])}",
                       "card": "Every market moving at once, from last week's close to the latest price.",
                       "story": "This is the whole week so far, with every market moving together, measured with real fund prices. "
                                "The days and news shocks below are ranked by how much each one moved you.",
                       "moves": auto_moves(px, yl, base, week[-1]),
                       "returns": {a["id"]: asset_return(px, a, base, week[-1]) for a in config.ASSETS}})
        prev = base
        for d in week:
            is_live = (d, anchor) in live and d == today
            shocks.append({"id": f"day-{d}", "kind": "day", "name": heads.get(d, "Market moves"),
                           "date": label(d) + (" · live" if is_live else ""),
                           "card": "What that trading day did, with every market moving.",
                           "story": (heads.get(d, "") + ". " if d in heads else "") +
                                    f"Everything that moved on {label(d)}, measured from the previous close" +
                                    (" to the latest price (the day is still trading)." if is_live else "."),
                           "moves": auto_moves(px, yl, prev, d),
                           "returns": {a["id"]: asset_return(px, a, prev, d) for a in config.ASSETS}})
            prev = d
    shocks += load_curated(today)

    # 5-day race: buy at the base close, hold through the week
    days = [base] + week
    paths = []
    for p in config.PORTFOLIOS:
        path = []
        for d in days:
            v = sum(w / 100 * (1 + asset_return(px, a, base, d)) for a in config.ASSETS for k, w in p["w"].items() if k == a["id"])
            path.append(round(v - sum(p["w"].values()) / 100, 6))
        paths.append(path)

    # ticker strip
    ticker = []
    for lbl, sym, _ in config.TICKER:
        s = px.get(sym, {})
        p0, p1 = at_or_before(s, base), at_or_before(s, today)
        if p0 and p1:
            ticker.append({"name": lbl, "value": p1, "change": round((p1 / p0 - 1) * 100, 2), "unit": "%"})
    y0, y1 = at_or_before(yl.get("r10"), base), at_or_before(yl.get("r10"), today)
    if y0 is not None and y1 is not None:
        ticker.insert(4, {"name": "10-yr yield", "value": y1, "change": round((y1 - y0) * 100, 1), "unit": "bp", "is_rate": True})

    story_date = con.execute("SELECT MAX(date) FROM stories").fetchone()[0]
    stories = [dict(r) for r in con.execute("SELECT kicker, headline, summary, tickers, source, url FROM stories WHERE date = ? ORDER BY rank", (story_date,))] if story_date else []
    last = con.execute("SELECT MAX(ts) FROM quotes").fetchone()[0]

    data = {
        "demo": demo,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_quote": last,
        "week_label": f"Week of {label(week[0]) if week else label(base)}",
        "x_labels": [short_label(d) for d in days],
        "assets": [{k: a[k] for k in ("id", "name", "symbol", "kind", "nvda_w") if k in a} |
                   ({"dv01_years": a["D"] * a["beta"]} if a["kind"] == "bd" else {}) for a in config.ASSETS],
        "portfolios": [{"name": p["name"], "tag": p["tag"], "sub": p["sub"], "w": p["w"], "path": paths[i]}
                       for i, p in enumerate(config.PORTFOLIOS)],
        "shocks": shocks,
        "ticker": ticker,
        "stories": stories,
        "stories_date": story_date,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=1)
    print(f"Wrote {out_path}: {len(shocks)} shocks, {len(days)} days, {len(stories)} stories.")
    return data


if __name__ == "__main__":
    main()
