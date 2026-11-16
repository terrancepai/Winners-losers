"""Everything you might want to change lives here: assets, portfolios, ticker strip.

Each asset is tracked with a real ETF (or bitcoin), so returns come straight from
market prices. The bond durations are only used for the DV01 line.
"""

# id: short name used everywhere. symbol: what we price it with.
# source: "finnhub" (stocks/ETFs) or "coinbase" (crypto).
# D / C / SD: duration, convexity, spread duration (bonds only). key: which yield drives it.
ASSETS = [
    {"id": "ustm",  "name": "U.S. stocks (total market)",  "symbol": "VTI",  "source": "finnhub", "kind": "st", "factor": "us"},
    {"id": "sp",    "name": "S&P 500 (VOO)",               "symbol": "VOO",  "source": "finnhub", "kind": "st", "factor": "us"},
    {"id": "ndx",   "name": "Nasdaq-100 (QQQ)",            "symbol": "QQQ",  "source": "finnhub", "kind": "st", "factor": "ndx"},
    {"id": "intl",  "name": "International stocks",        "symbol": "VXUS", "source": "finnhub", "kind": "st", "factor": "intl"},
    {"id": "btc",   "name": "Bitcoin",                     "symbol": "BTC-USD", "source": "coinbase", "kind": "al", "factor": "btc"},
    {"id": "short", "name": "Short Treasuries",            "symbol": "SHY",  "source": "finnhub", "kind": "bd", "D": 1.9, "C": 5,  "SD": 0.0, "key": "r2",  "beta": 1.0},
    {"id": "usb",   "name": "U.S. bonds (total market)",   "symbol": "BND",  "source": "finnhub", "kind": "bd", "D": 6.0, "C": 50, "SD": 1.8, "key": "r10", "beta": 1.0},
    {"id": "intlb", "name": "International bonds (hedged)", "symbol": "BNDX", "source": "finnhub", "kind": "bd", "D": 7.0, "C": 60, "SD": 0.0, "key": "r10", "beta": 0.5},
]

# What's inside the stock funds: each company's weight in each fund (percent).
# Used to find which companies moved each portfolio most, and for "hidden stakes".
# Sources: S&P 500 (sp) = SPDR S&P 500 holdings, Nov 9, 2026 (Trefis) for the top 7;
# Micron and Tesla from the Oct 2, 2026 holdings. Nasdaq-100 (ndx) = Invesco QQQ SEC filing,
# June 30, 2026; Meta is an estimate. Total market (ustm) = S&P weight x 0.85 (estimate).
# Weights drift with prices: refresh them every few months from each fund's holdings page.
HOLDINGS = {
    "NVDA":  {"name": "Nvidia",    "w": {"sp": 6.6,  "ndx": 7.60}},
    "AAPL":  {"name": "Apple",     "w": {"sp": 7.9,  "ndx": 6.67}},
    "MSFT":  {"name": "Microsoft", "w": {"sp": 6.2,  "ndx": 4.35}},
    "GOOGL": {"name": "Alphabet",  "w": {"sp": 4.7,  "ndx": 6.29}},
    "AMZN":  {"name": "Amazon",    "w": {"sp": 4.0,  "ndx": 4.02}},
    "AVGO":  {"name": "Broadcom",  "w": {"sp": 2.3,  "ndx": 2.81}},
    "META":  {"name": "Meta",      "w": {"sp": 2.2,  "ndx": 2.5}},
    "MU":    {"name": "Micron",    "w": {"sp": 1.82, "ndx": 5.64}},
    "TSLA":  {"name": "Tesla",     "w": {"sp": 1.57, "ndx": 3.30}},
    "AMD":   {"name": "AMD",       "w": {"ndx": 4.10}},
}
for _h in HOLDINGS.values():
    if "sp" in _h["w"]:
        _h["w"].setdefault("ustm", round(_h["w"]["sp"] * 0.85, 2))

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
    for sym in HOLDINGS:
        if sym not in seen:
            seen.add(sym); out.append((sym, "finnhub"))
    for _, sym, src in TICKER:
        if sym not in seen:
            seen.add(sym); out.append((sym, src))
    return out
