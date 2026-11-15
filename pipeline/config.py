"""Everything you might want to change lives here: assets, portfolios, ticker strip.

Each asset is tracked with a real ETF (or bitcoin), so weekly and daily returns
come straight from market prices. The bond numbers (duration etc.) are only used
for the "what if" shocks in content/shocks.json and for the DV01 line.
"""

# id: short name used everywhere. symbol: what we price it with.
# source: "finnhub" (stocks/ETFs) or "coinbase" (crypto).
# nvda_w: Nvidia's weight inside the fund (look-through). Update a few times a year.
# D / C / SD: duration, convexity, spread duration (bonds only). key: which yield drives it.
ASSETS = [
    {"id": "ustm",  "name": "U.S. stocks (total market)",  "symbol": "VTI",  "source": "finnhub", "kind": "st", "factor": "us",   "nvda_w": 0.072},
    {"id": "sp",    "name": "S&P 500 (VOO)",               "symbol": "VOO",  "source": "finnhub", "kind": "st", "factor": "us",   "nvda_w": 0.085},
    {"id": "ndx",   "name": "Nasdaq-100 (QQQ)",            "symbol": "QQQ",  "source": "finnhub", "kind": "st", "factor": "ndx",  "nvda_w": 0.081},
    {"id": "intl",  "name": "International stocks",        "symbol": "VXUS", "source": "finnhub", "kind": "st", "factor": "intl", "nvda_w": 0.0},
    {"id": "btc",   "name": "Bitcoin",                     "symbol": "BTC-USD", "source": "coinbase", "kind": "al", "factor": "btc", "nvda_w": 0.0},
    {"id": "short", "name": "Short Treasuries",            "symbol": "SHY",  "source": "finnhub", "kind": "bd", "D": 1.9, "C": 5,  "SD": 0.0, "key": "r2",  "beta": 1.0},
    {"id": "usb",   "name": "U.S. bonds (total market)",   "symbol": "BND",  "source": "finnhub", "kind": "bd", "D": 6.0, "C": 50, "SD": 1.8, "key": "r10", "beta": 1.0},
    {"id": "intlb", "name": "International bonds (hedged)", "symbol": "BNDX", "source": "finnhub", "kind": "bd", "D": 7.0, "C": 60, "SD": 0.0, "key": "r10", "beta": 0.5},
]

# Weights in percent. Order sets each portfolio's chart color, so keep it stable.
PORTFOLIOS = [
    {"name": "VOO and Chill",          "tag": "",     "sub": "One S&P 500 fund, nothing else.",
     "w": {"sp": 100}},
    {"name": "Retirement Fund 2060",   "tag": "td",   "sub": "Retiring in about 35 years.",
     "w": {"ustm": 54.9, "intl": 36.6, "usb": 5.9, "intlb": 2.6}},
    {"name": "Classic 60/40",          "tag": "",     "sub": "S&P 500 and U.S. bonds.",
     "w": {"sp": 60, "usb": 40}},
    {"name": "Retirement Fund Income", "tag": "td",   "sub": "Already retired.",
     "w": {"ustm": 17, "intl": 12, "usb": 37, "intlb": 16, "short": 18}},
    {"name": "Crypto heavy",           "tag": "risk", "sub": "30% bitcoin, 70% S&P 500.",
     "w": {"btc": 30, "sp": 70}},
    {"name": "Tech tilt",              "tag": "tech", "sub": "40% QQQ, 30% S&P 500, 30% U.S. bonds.",
     "w": {"ndx": 40, "sp": 30, "usb": 30}},
]

# Ticker strip at the top of the page: (label, symbol, source)
TICKER = [
    ("S&P 500 (SPY)", "SPY", "finnhub"),
    ("Dow (DIA)", "DIA", "finnhub"),
    ("Nasdaq-100 (QQQ)", "QQQ", "finnhub"),
    ("Russell 2000 (IWM)", "IWM", "finnhub"),
    ("Nvidia", "NVDA", "finnhub"),
    ("Apple", "AAPL", "finnhub"),
    ("Microsoft", "MSFT", "finnhub"),
    ("Gold (GLD)", "GLD", "finnhub"),
    ("Oil (USO)", "USO", "finnhub"),
    ("Bitcoin", "BTC-USD", "coinbase"),
]

# Treasury yields from FRED (daily, official). Shown in the ticker and used for "rates" moves.
FRED_SERIES = {"r2": "DGS2", "r10": "DGS10"}

# Claude model for the daily news summaries.
CLAUDE_MODEL = "claude-haiku-5-5"

TIMEZONE = "America/New_York"


def all_symbols():
    """Every (symbol, source) pair the price job needs, without duplicates."""
    seen, out = set(), []
    for a in ASSETS:
        if a["symbol"] not in seen:
            seen.add(a["symbol"]); out.append((a["symbol"], a["source"]))
    for _, sym, src in TICKER:
        if sym not in seen:
            seen.add(sym); out.append((sym, src))
    return out
