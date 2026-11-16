"""The SQLite database: one file, data/market.db."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "market.db")

SCHEMA = """
-- every price we fetch, every 15 minutes
CREATE TABLE IF NOT EXISTS quotes (
    ts          TEXT NOT NULL,      -- UTC ISO time we fetched it
    symbol      TEXT NOT NULL,
    price       REAL NOT NULL,
    prev_close  REAL,               -- previous trading day's close, if the source gives it
    PRIMARY KEY (ts, symbol)
);

-- one close per symbol per trading day (New York date)
CREATE TABLE IF NOT EXISTS daily_close (
    symbol  TEXT NOT NULL,
    date    TEXT NOT NULL,          -- YYYY-MM-DD
    close   REAL NOT NULL,
    final   INTEGER NOT NULL DEFAULT 0,  -- 1 once confirmed by the next day's prev_close
    PRIMARY KEY (symbol, date)
);

-- Treasury yields from FRED, in percent
CREATE TABLE IF NOT EXISTS yields (
    series  TEXT NOT NULL,          -- r2, r10
    date    TEXT NOT NULL,
    value   REAL NOT NULL,
    PRIMARY KEY (series, date)
);

-- the day's top stories, written by Claude from news headlines
CREATE TABLE IF NOT EXISTS stories (
    date      TEXT NOT NULL,
    rank      INTEGER NOT NULL,
    kicker    TEXT,
    headline  TEXT NOT NULL,
    summary   TEXT,
    tickers   TEXT,                 -- comma separated
    source    TEXT,
    url       TEXT,
    PRIMARY KEY (date, rank)
);

-- why each big mover moved: one short story per mover per day, written by Claude
CREATE TABLE IF NOT EXISTS mover_stories (
    date      TEXT NOT NULL,
    mover_id  TEXT NOT NULL,        -- a ticker like NVDA, or rates / btc / intl / rest
    headline  TEXT NOT NULL,
    story     TEXT,
    source    TEXT,
    url       TEXT,
    PRIMARY KEY (date, mover_id)
);

-- one short label per trading day, used to name that day's shock
CREATE TABLE IF NOT EXISTS day_headlines (
    date      TEXT PRIMARY KEY,
    headline  TEXT NOT NULL
);

-- log of each pipeline run, so the site can say when data last updated
CREATE TABLE IF NOT EXISTS runs (
    ts      TEXT NOT NULL,
    job     TEXT NOT NULL,
    ok      INTEGER NOT NULL,
    note    TEXT
);
"""


def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def log_run(con, ts, job, ok, note=""):
    con.execute("INSERT INTO runs (ts, job, ok, note) VALUES (?, ?, ?, ?)", (ts, job, int(ok), note[:500]))
    con.commit()
