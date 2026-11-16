"""One-time: load about 100 days of daily closes so the 5-day chart works from day one.

Uses Alpha Vantage (free key, 25 calls per day, enough for our symbols) and Coinbase for bitcoin.
Run it once:  ALPHAVANTAGE_API_KEY=xxx python pipeline/backfill.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config
import db
import export
import sources


def main():
    key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not key:
        sys.exit("Set ALPHAVANTAGE_API_KEY (free at alphavantage.co).")
    con = db.connect()
    symbols = config.all_symbols()
    finnhub_count = sum(1 for _, s in symbols if s == "finnhub")
    if finnhub_count > 25:
        print(f"Note: {finnhub_count} symbols but Alpha Vantage allows 25 calls/day. Run again tomorrow for the rest.")
    done = 0
    for symbol, source in symbols:
        have = con.execute("SELECT COUNT(*) FROM daily_close WHERE symbol = ?", (symbol,)).fetchone()[0]
        if have >= 30:
            continue  # already backfilled
        try:
            rows = sources.coinbase_daily(symbol) if source == "coinbase" else sources.alphavantage_daily(symbol, key)
        except Exception as e:
            print(f"{symbol}: {e}")
            continue
        for date, close in rows[-120:]:
            con.execute("INSERT OR IGNORE INTO daily_close (symbol, date, close, final) VALUES (?, ?, ?, 1)",
                        (symbol, date, close))
        con.commit()
        done += 1
        print(f"{symbol}: {len(rows)} days")
        if source != "coinbase":
            time.sleep(13)  # Alpha Vantage allows 5 calls/minute
    export.main(con)
    print(f"Backfilled {done} symbols.")


if __name__ == "__main__":
    main()
