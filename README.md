# Portfolio Shock Check

This week's market news, translated into what it did to six common portfolios, from "VOO and Chill" to a target-date retirement fund. The site updates itself every 15 minutes while the market is open.

**What it shows that a brokerage app doesn't:**
- How every portfolio did this week, side by side (5-day race chart, winner and loser)
- Which days and news events moved your kind of portfolio most, ranked
- What's hiding inside your funds: how much Nvidia you own through an index fund, and how much a 0.01% rise in yields costs you
- The day's top market stories, summarized

## How it works

```
 every 15 min (weekdays)              once a day after the close
 ───────────────────────              ──────────────────────────
 Finnhub ─ fund & stock prices        Finnhub ─ news headlines
 Coinbase ─ bitcoin                          │
 FRED ─ Treasury yields                Claude ─ picks 5, writes summaries
        │                                    │
        └────────────►  SQLite database  ◄───┘
                        (data/market.db)
                              │
                        pipeline/export.py ─ returns, 5-day paths, shocks
                              │
                        site/data/latest.json
                              │
                        site/index.html  (GitHub Pages)
```

Everything runs free on GitHub Actions. No server to keep running. The database lives on its own `data` branch so the main branch stays clean.

| Folder | What's in it |
|---|---|
| `pipeline/config.py` | Assets, portfolios, ticker strip. **Edit this to change portfolios.** |
| `pipeline/update_prices.py` | The 15-minute job |
| `pipeline/update_news.py` | The daily news job |
| `pipeline/backfill.py` | One-time load of ~100 days of history |
| `pipeline/export.py` | Turns the database into the JSON the site reads |
| `content/shocks.json` | Hand-written "news shocks" (e.g. "Huang out as Nvidia CEO"). Each has a `show_until` date and disappears after it. |
| `site/` | The website |
| `.github/workflows/` | The schedules |

All Python uses the standard library only, so there is nothing to `pip install`.

## Set it up (about 20 minutes)

### 1. Put the code on GitHub
1. Create a free account at github.com if you don't have one.
2. Click **New repository**, name it (e.g. `portfolio-shock-check`), make it **Public**, and create it.
3. Upload this whole folder. The easiest way is [GitHub Desktop](https://desktop.github.com): add this folder as a repository, then **Publish**. Dragging files into the browser also works, but the `.github` folder is hidden on Mac (press Cmd+Shift+. in Finder to show it).

### 2. Get your API keys
| Key | Where | Cost |
|---|---|---|
| `FINNHUB_API_KEY` | finnhub.io → sign up → dashboard | Free (60 calls/minute) |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys. Add a few dollars of credit and set a monthly spend limit. | A few cents a day |
| `ALPHAVANTAGE_API_KEY` | alphavantage.co → get free key | Free, only used once for history |

### 3. Add the keys to GitHub
In your repository: **Settings → Secrets and variables → Actions → New repository secret**. Add each key with exactly the names above.

### 4. Turn on the website
**Settings → Pages → Build and deployment → Source: GitHub Actions.**

### 5. Load history, then start
1. Go to the **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**.
2. Click **Backfill history (run once)** → **Run workflow**. Wait for the green check (a few minutes).
3. Click **Update prices** → **Run workflow**. When it finishes, your site is live at
   `https://YOUR-USERNAME.github.io/portfolio-shock-check/`
4. Optional: click **Update news** → **Run workflow** to get today's stories right away.

From then on it runs on its own.

## Preview it on your computer (no keys needed)

```bash
python pipeline/demo_seed.py      # fills a demo database with the week of Nov 9-13, 2026
cd site
python -m http.server 8000        # then open http://localhost:8000
```

Opening `site/index.html` by double-clicking won't work: browsers block it from reading the data file. Use the server command above.

## Everyday changes

- **Change a portfolio:** edit `PORTFOLIOS` in `pipeline/config.py`. Weights are percentages and should add to 100.
- **Add a news shock:** copy an entry in `content/shocks.json`. `moves` uses `nvda`, `us`, `ndx`, `intl`, `btc` (percent) and `r2`, `r10`, `s` (basis points). Set `"isolate": "nvda"` or `"rates"` to move only that. Set `show_until` so it drops off.
- **Update Nvidia look-through weights:** `nvda_w` in `config.py`, from each fund's holdings page. Worth doing every few months.

## Things to know

- **GitHub's schedule isn't exact.** Scheduled runs can be a few minutes late when GitHub is busy, so "every 15 minutes" is really "roughly every 15 minutes."
- **GitHub pauses schedules after 60 days with no commits.** Edit any file (even the README) at least every two months, or re-enable the workflows from the Actions tab.
- **Yields update daily, not every 15 minutes.** FRED publishes official Treasury yields once a day, a day late.
- **Data terms.** Finnhub's free tier is for personal, non-commercial use. A public portfolio project should be fine, but read their terms before doing anything commercial, and keep the source credits on the site.
- **The news summaries are AI-written.** Claude may only pick from that day's feed and every link comes from the feed, not from the model, but read them before relying on them.
- **Not investment advice.** Model portfolios mirror published allocations; they are not the funds themselves.

## Explaining it in an interview

- *Portfolio review:* look-through exposure. A plain S&P 500 fund is about 8.5% Nvidia, and "tech heavy" QQQ isn't much more.
- *Fixed income:* DV01 per $100,000, and why a bond-heavy retirement portfolio lost money in a week stocks rallied.
- *Risk:* scenario analysis. Isolating one shock (a CEO exit, a rate jump) versus the whole week, and ranking what drove the result.
- *Engineering:* a scheduled data pipeline, a SQL database, and a static front end, all free to run.
