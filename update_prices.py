"""Runs every 15 minutes on weekdays: fetch prices and yields, save them, rebuild the site data.

Run it yourself with:  FINNHUB_API_KEY=xxx python pipeline/update_prices.py
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
import config
import db
import export
import sources


def fetch_quote(symbol, source, finnhub_key):
    if source == "coinbase":
        return sources.coinbase_spot(symbol)
    return sources.finnhub_quote(symbol, finnhub_key)


def save_quote(con, ts, today, market_open, symbol, q):
    con.execute("INSERT OR REPLACE INTO quotes (ts, symbol, price, prev_close) VALUES (?, ?, ?, ?)",
                (ts, symbol, q["price"], q["prev_close"]))
    # Which day was the last trade? On weekends and holidays it is an earlier day.
    trade_day = today if q.get("t") is None else \
        datetime.fromtimestamp(q["t"], ZoneInfo(config.TIMEZONE)).date().isoformat()
    if trade_day != today:
        # Market didn't trade today: the "current" price is that day's official close.
        con.execute("""INSERT INTO daily_close (symbol, date, close, final) VALUES (?, ?, ?, 1)
                       ON CONFLICT(symbol, date) DO UPDATE SET close = excluded.close, final = 1""",
                    (symbol, trade_day, q["price"]))
        return
    # The previous close is official: lock in the last trading day before today.
    if q["prev_close"]:
        row = con.execute("SELECT date FROM daily_close WHERE symbol = ? AND date < ? ORDER BY date DESC LIMIT 1",
                          (symbol, today)).fetchone()
        if row:
            con.execute("UPDATE daily_close SET close = ?, final = 1 WHERE symbol = ? AND date = ?",
                        (q["prev_close"], symbol, row["date"]))
    # Today's close is provisional until tomorrow confirms it. Skip before the 9:30 open,
    # when the "current" price is really yesterday's close.
    if market_open:
        con.execute("""INSERT INTO daily_close (symbol, date, close, final) VALUES (?, ?, ?, 0)
                       ON CONFLICT(symbol, date) DO UPDATE SET close = excluded.close WHERE final = 0""",
                    (symbol, today, q["price"]))


def update_yields(con):
    for series, fred_id in config.FRED_SERIES.items():
        for date, value in sources.fred_series(fred_id)[-400:]:
            con.execute("INSERT OR REPLACE INTO yields (series, date, value) VALUES (?, ?, ?)", (series, date, value))


def main():
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        sys.exit("Set FINNHUB_API_KEY (free at finnhub.io).")
    now = datetime.now(timezone.utc)
    ny = now.astimezone(ZoneInfo(config.TIMEZONE))
    ts, today = now.strftime("%Y-%m-%dT%H:%M:%SZ"), ny.date().isoformat()
    if ny.weekday() >= 5:
        print("Weekend: markets closed, nothing to fetch.")
        return
    market_open = ny.time() >= datetime.strptime("09:30", "%H:%M").time()

    con = db.connect()
    errors = []
    for symbol, source in config.all_symbols():
        try:
            q = fetch_quote(symbol, source, key)
            if q:
                save_quote(con, ts, today, market_open, symbol, q)
            else:
                errors.append(f"{symbol}: empty quote")
        except Exception as e:  # keep going if one symbol fails
            errors.append(f"{symbol}: {e}")
        if source == "finnhub":
            time.sleep(1.1)  # stay under 60 calls/minute
    try:
        update_yields(con)
    except Exception as e:
        errors.append(f"FRED: {e}")
    con.commit()
    db.log_run(con, ts, "prices", ok=not errors, note="; ".join(errors))
    export.main(con)
    print(f"Saved quotes at {ts}. {len(errors)} problem(s).", *errors, sep="\n")


if __name__ == "__main__":
    main()
