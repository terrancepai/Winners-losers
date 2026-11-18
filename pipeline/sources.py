"""Talking to the outside world. Python standard library only, so there is nothing to install."""
import csv
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "portfolio-shock-check/1.0 (educational project)"


def get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def get_json(url, headers=None):
    return json.loads(get(url, headers))


# ---------- Finnhub: stocks and ETFs (free key, 60 calls/minute) ----------
def finnhub_quote(symbol, key):
    """Returns {"price": current, "prev_close": previous close} or None."""
    q = get_json(f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote(symbol)}&token={key}")
    if not q or not q.get("c"):
        return None
    return {"price": float(q["c"]), "prev_close": float(q["pc"]) if q.get("pc") else None, "t": q.get("t")}


def finnhub_news(key, category="general"):
    """Recent market headlines from many outlets: [{headline, summary, source, url, datetime, related}]."""
    return get_json(f"https://finnhub.io/api/v1/news?category={category}&token={key}")


def finnhub_company_news(symbol, start, end, key):
    """Headlines about one company between two dates (YYYY-MM-DD)."""
    return get_json(f"https://finnhub.io/api/v1/company-news?symbol={urllib.parse.quote(symbol)}"
                    f"&from={start}&to={end}&token={key}")


# ---------- News outlets ----------
# Top stories come only from these four. Reuters has no free public feed, so its stories
# arrive through Finnhub's general news feed; the other three also have public RSS feeds.
OUTLETS = ["Reuters", "CNBC", "Yahoo Finance", "Bloomberg"]
RSS_FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
]


def outlet(name):
    """Map a feed's source name to one of OUTLETS, or None. Finnhub writes "Yahoo", RSS writes the full name."""
    n = (name or "").lower()
    for o in OUTLETS:
        if o.lower().split()[0] in n:
            return o
    return None


def rss_news(url, source):
    """Headlines from one RSS feed, in the same shape as Finnhub's: [{headline, summary, source, url, datetime}]."""
    import html
    import re
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    root = ET.fromstring(get(url))
    out = []
    for item in root.iter("item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        desc = re.sub(r"<[^>]+>", "", html.unescape(item.findtext("description") or "")).strip()
        try:
            ts = parsedate_to_datetime(item.findtext("pubDate")).timestamp()
        except Exception:
            ts = 0
        out.append({"headline": title, "summary": desc, "source": source, "url": link, "datetime": ts, "related": ""})
    return out


def outlet_news(finnhub_key):
    """Recent headlines from Reuters, CNBC, Yahoo Finance and Bloomberg, newest first, without duplicates."""
    items = []
    for source, url in RSS_FEEDS:
        try:
            items += rss_news(url, source)
        except Exception as e:
            print(f"{source} feed: {e}")
    try:
        for n in finnhub_news(finnhub_key):
            o = outlet(n.get("source"))
            if o and n.get("headline"):
                items.append(n | {"source": o})
    except Exception as e:
        print(f"Finnhub news: {e}")
    seen, out = set(), []
    for n in sorted(items, key=lambda n: -n.get("datetime", 0)):
        key = n["headline"].lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


# ---------- Coinbase: bitcoin (no key) ----------
def coinbase_spot(pair="BTC-USD"):
    d = get_json(f"https://api.coinbase.com/v2/prices/{pair}/spot")
    return {"price": float(d["data"]["amount"]), "prev_close": None, "t": None}


def coinbase_daily(pair="BTC-USD", days=120):
    """Daily candles for backfill: [(YYYY-MM-DD, close)] oldest first."""
    rows = get_json(f"https://api.exchange.coinbase.com/products/{pair}/candles?granularity=86400")
    out = [(time.strftime("%Y-%m-%d", time.gmtime(r[0])), float(r[4])) for r in rows[:days]]
    return sorted(out)


# ---------- FRED: Treasury yields (no key, daily) ----------
def fred_series(series_id):
    """[(YYYY-MM-DD, value)] for a FRED series, skipping blank days."""
    text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        date = row.get("observation_date") or row.get("DATE")
        val = row.get(series_id)
        if date and val not in (None, "", "."):
            out.append((date, float(val)))
    return out


# ---------- Alpha Vantage: one-time price history backfill (free key, 25 calls/day) ----------
def alphavantage_daily(symbol, key):
    d = get_json(f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={key}")
    series = d.get("Time Series (Daily)")
    if not series:
        raise RuntimeError(f"Alpha Vantage returned no data for {symbol}: {str(d)[:200]}")
    return sorted((date, float(v["4. close"])) for date, v in series.items())


# ---------- Claude: news summaries ----------
def claude(prompt, model, max_tokens=4000):
    """Ask Claude and return its text. Retries once, and prints what came back if there was no text,
    so a failed run's log shows the cause."""
    key = os.environ["ANTHROPIC_API_KEY"]
    body = json.dumps({"model": model, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    for attempt in (1, 2):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Anthropic API error {e.code}: {e.read().decode()[:300]}")
        text = "".join(part.get("text", "") for part in d.get("content", []) if part.get("type") == "text")
        if "{" in text:
            return text
        print(f"Claude reply had no JSON (attempt {attempt}): stop_reason={d.get('stop_reason')}, "
              f"blocks={[p.get('type') for p in d.get('content', [])]}, text={text[:300]!r}")
    raise RuntimeError(f"Claude returned no JSON (stop_reason={d.get('stop_reason')}). See the lines above.")
