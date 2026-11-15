"""Fill a demo database with the week of Nov 9-13, 2026, so you can preview the site with no API keys.

Daily index moves are the reported ones. Fund prices are approximations built from those moves,
and some days are estimates, so the site shows a "demo data" banner. Real runs replace all of it.

    python pipeline/demo_seed.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config
import db
import export

DAYS = ["2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]

# starting price on Nov 6 and daily % moves Mon..Fri
DEMO = {
    "VOO":  (690.0,  [2.35, -0.38, 1.31, -0.35, -0.40]),   # S&P 500 daily moves (AP)
    "SPY":  (754.0,  [2.35, -0.38, 1.31, -0.35, -0.40]),
    "VTI":  (370.0,  [2.40, -0.42, 1.25, -0.45, -0.38]),
    "QQQ":  (680.0,  [3.40, -0.60, 2.30, -0.32, -1.22]),   # Nasdaq-100; Tue/Thu estimated
    "VXUS": (75.0,   [1.41, -0.23, 0.79, -0.21, -0.24]),   # estimated
    "DIA":  (512.9,  [2.15, -0.30, 0.49, -0.36, 0.10]),
    "IWM":  (273.9,  [3.14, -0.68, 0.88, -1.66, -0.31]),   # Russell 2000
    "NVDA": (186.64, [-4.27, -5.47, 2.87, -4.34, -2.01]),
    "AAPL": (350.7,  [0.80, -0.60, 1.10, -0.20, -0.30]),   # estimated
    "MSFT": (530.61, [0.60, -0.50, 0.40, -0.90, -0.87]),   # week -1.27%, days estimated
    "GLD":  (372.0,  [-0.50, -1.60, 0.40, -1.50, -1.50]),  # week about -4.65%, days estimated
    "USO":  (80.0,   [-1.50, 0.80, 1.20, 0.50, -2.10]),    # estimated
    "BTC-USD": (75747.0, [1.0, -3.5, 0.5, -3.8, -4.35]),   # Nov 6 and Nov 13 closes reported
}
YIELDS = {"r2": [4.51, 4.54, 4.73, None, 4.86, 4.89], "r10": [4.859, 4.872, 4.99, None, 5.09, 5.154]}
HEADLINES = {
    "2026-11-09": "Stocks rally as Nvidia board opens CEO probe",
    "2026-11-10": "Hot inflation report sends yields higher",
    "2026-11-11": "AI stocks rebound; bond market closed",
    "2026-11-12": "Jensen Huang resigns as Nvidia CEO",
    "2026-11-13": "Tech slips as 10-year yield tops 5.15%",
}
STORIES = [
    ("Nvidia", "Nvidia's board moved to oust Jensen Huang. A day later, he was gone.",
     "The Journal reported the board was preparing to remove its co-founder after reports of two relationships. Huang resigned Thursday and CFO Colette Kress is interim CEO.",
     "NVDA,AMD", "SEC filing", "https://www.sec.gov/Archives/edgar/data/0001045810/000104581026000082/nvidiaannouncesceotransiti.htm"),
    ("Iran", "Vance weighs face-to-face talks with Iran's security chief",
     "Officials told the Journal the vice president is emerging as the lead negotiator to end the war. Any meeting remains preliminary.",
     "Oil,10-yr yield", "Just Security", "https://justsecurity.org/164226/early-edition-november-12-2026"),
    ("Rates", "Hot inflation data pushes the 10-year yield back above 5%",
     "Core prices rose 0.3% in October, more than expected, lifting bets on another Fed hike.",
     "10-yr yield,TLT", "investingLive", "https://investinglive.com/technical-analysis/us-stocks-slide-yields-jump-usd-higher-after-hotter-than-expected-october-cpi/"),
    ("Chips", "AMD and Broadcom jump as investors rotate within chips",
     "Both rose about 18% on the week while Nvidia fell, so chip funds still finished higher.",
     "AMD,AVGO", "The Glass Desk", "https://theglassdesk.substack.com/p/weekly-market-review-nov-13-2026"),
    ("Crypto", "Bitcoin slides to its lowest level since August",
     "Bitcoin fell about 10% on the week as rate-hike fears hit risky assets.",
     "BTC", "Investrade", "https://investrade.com/market-review-november-13-2026/"),
]
BONDS = {"SHY": (82.0, "r2", 1.9, 1.0), "BND": (72.0, "r10", 6.0, 1.0), "BNDX": (48.0, "r10", 7.0, 0.5)}


def main(path=None):
    path = path or os.path.join(os.path.dirname(db.DB_PATH), "demo.db")
    if os.path.exists(path):
        os.remove(path)
    con = db.connect(path)
    for sym, (p, moves) in DEMO.items():
        prices = [p]
        for m in moves:
            prices.append(prices[-1] * (1 + m / 100))
        for d, v in zip(DAYS, prices):
            con.execute("INSERT INTO daily_close VALUES (?, ?, ?, 1)", (sym, d, round(v, 4)))
    # bond funds priced from the yield moves with the duration model
    for sym, (p, key, dur, beta) in BONDS.items():
        ys = YIELDS[key]
        price, prev_y = p, ys[0]
        con.execute("INSERT INTO daily_close VALUES (?, ?, ?, 1)", (sym, DAYS[0], price))
        for d, y in zip(DAYS[1:], ys[1:]):
            if y is not None:
                price *= 1 - dur * (y - prev_y) / 100 * beta
                prev_y = y
            con.execute("INSERT INTO daily_close VALUES (?, ?, ?, 1)", (sym, d, round(price, 4)))
    for key, ys in YIELDS.items():
        for d, y in zip(DAYS, ys):
            if y is not None:
                con.execute("INSERT INTO yields VALUES (?, ?, ?)", (key, d, y))
    for d, h in HEADLINES.items():
        con.execute("INSERT INTO day_headlines VALUES (?, ?)", (d, h))
    for i, s in enumerate(STORIES, 1):
        con.execute("INSERT INTO stories VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("2026-11-13", i, *s))
    con.execute("INSERT INTO quotes VALUES (?, ?, ?, ?)", ("2026-11-13T21:00:00Z", "VOO", DEMO["VOO"][0], None))
    con.commit()
    missing = [s for s, _ in config.all_symbols() if s not in DEMO and s not in BONDS]
    if missing:
        print("Demo has no data for:", missing)
    return export.main(con, demo=True)


if __name__ == "__main__":
    main()
