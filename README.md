# Market Metrics Dashboard

A Bloomberg-terminal-style dashboard for stock market analysis, built with Plotly Dash. Aggregates data from FinViz Elite, Stockbee (Pradeep Bonde), CNBC Market Insider, and Yahoo Finance into a single dark-themed interface.

## Requirements

- **Python 3.10+**
- **FinViz Elite API** — Set `FINVIZ_API_KEY` in `.env` for most widgets
- **Stockbee API** (optional) — Set `STOCKBEE_API_URL` for breadth data; falls back to Google Sheets if not running

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
FINVIZ_API_KEY=your_api_key
```

Run the app:

```bash
python app.py
```

---

## Widget Reference

The dashboard has two tabs: **Market Metrics** (swing/position) and **Intraday** (day trading). Each widget can be toggled on/off via the Settings gear icon.

---

### Market Metrics Tab

#### Key Metrics

Aggregates breadth statistics across five index groups: **NQ100** (NASDAQ 100), **SPY500** (S&P 500), **DJIA** (Dow Jones), **RUS2000** (Russell 2000), and **$1B+** (US stocks with market cap ≥ $1B and avg volume ≥ 1K).

For each group, the table shows:
- **Above / Below** — Count of stocks meeting a positive vs negative condition
- **%** — Percentage of stocks in the “above” condition

Rows include: Day Chg, Open Chg, Week, Month, Qtr, Half Year, Year (performance), Price vs SMA10/20/50/200, EMA10>SMA20, SMA20<SMA50, SMA50<SMA200, SMA20>SMA50>SMA200 (trend alignment), 4% Up vs 4% Down (daily breadth), New 20-Day Highs, New 20-Day Lows, and total stock count.

**Data source:** FinViz Elite `export.ashx` and screener URLs. Row labels link to FinViz screeners filtered by that metric.

---

#### NQ100, SPY500 & DJIA Metrics

Bar charts of the Key Metrics **%** values for NASDAQ 100, S&P 500, and Dow Jones. Green bars = bullish breadth (e.g., >50% of stocks above SMA20); red = bearish. Lets you compare breadth across the three major indices.

**Data source:** Same as Key Metrics (`compute_all_key_metrics`).

---

#### RUS2000 & $1B+ Stocks

Same bar chart layout for Russell 2000 and the $1B+ universe. Used to compare small-cap and broad-market breadth.

**Data source:** Same as Key Metrics.

---

#### StockBee Market Breadth Monitor

Summary cards for Stockbee-style breadth:
- **S&P 500** — Index level and daily change
- **T2108** — % of S&P 500 stocks above 200-day SMA (0–100)
- **5-Day Ratio** — Up 4%+ vs Down 4%+ over 5 days
- **10-Day Ratio** — Same over 10 days
- **Up 4%+ / Down 4%+** — Today’s counts

**Data source:** Stockbee API (`/api/pplx-market-data`) or Google Sheets Market Monitor. Links to Stockbee Monitor sheet.

---

#### StockBee - Primary Breadth — Up/Down 4%+ Today

Line chart of daily **Up 4%+** and **Down 4%+** counts over time. Shows short-term breadth shifts.

**Data source:** Stockbee breadth history (API or Sheets).

---

#### StockBee - Breadth Ratios — 5-Day & 10-Day

Line chart of **5-Day** and **10-Day** breadth ratios (Up 4%+ / Down 4%+). Ratio > 1 = more gainers than losers; < 1 = more losers.

**Data source:** Stockbee breadth history.

---

#### StockBee - Secondary Breadth — Up/Down 25%+ Qtr

Line chart of **Up 25%+** and **Down 25%+** counts over the quarter. Captures larger moves and longer-term breadth.

**Data source:** Stockbee breadth history.

---

#### StockBee - S&P 500 — Last 60 Days

Line chart of S&P 500 index level over the last 60 days.

**Data source:** Stockbee breadth history (S&P 500 column).

---

#### Qullamaggie

Stocks matching Kris Kullamägi’s **Episodic Pivot** setup:
- USA, avg volume ≥ 1K, price ≥ $1
- Gap up ≥ 10%
- Relative volume ≥ 2x

**Data source:** FinViz Elite `qulla_episodic` export URL.

---

#### Minervini

Stocks matching Mark Minervini’s **Trend Template**:
- USA, avg vol 1K+, price $1+
- Price above SMA200, SMA150, SMA50
- SMA50 above SMA150 and SMA200
- Price within 25% of 52-week high
- Price within 25% of 52-week low (pullback)
- RSI(14) ≥ 70

**Data source:** FinViz Elite `minervini` export URL.

---

#### O'Neil

Stocks matching William O’Neil’s **CANSLIM** criteria:
- USA
- ROE + Net Profit Margin ≥ 25%
- EPS growth filters (YOY, forward, TTM positive)
- Net margin positive

**Data source:** FinViz Elite `oneil` export URL (fundamental view v=161).

---

#### Watchlist

User-defined tickers from `watchlist.csv` in the project root. Shows price, change, volume, avg vol, rel vol, and ATR% for each ticker.

**Data source:** FinViz Elite `quote.ashx` per ticker. Add tickers in `watchlist.csv` (one per line, header optional).

---

#### Sector SPDR ETFs

Table of sector ETFs (XLK, XLV, XLC, etc.) with gap, day change, week/month/qtr/half-year/year performance, last price, EMAs/SMAs, 52-week range, and ATR%. Sorted by ATR% and change.

**Data source:** FinViz Elite `quote.ashx` for each sector ETF.

---

#### RRG Sector Rotation

**Relative Rotation Graph** of 11 Sector SPDRs vs **VTI**:
- **X-axis (RS-Ratio):** 1-year performance vs VTI (normalized)
- **Y-axis (RS-Momentum):** Quarter performance vs VTI (normalized)

Quadrants: Improving (top-right), Leading (bottom-right), Weakening (bottom-left), Lagging (top-left). Each dot is a sector; hover for details.

**Data source:** Sector ETF performance from FinViz; VTI from FinViz for benchmark.

---

#### 97 Club

Stocks in the **$1B+ USA** universe with avg vol 1K+ and price $1+. Simple broad screener.

**Data source:** FinViz Elite `club97` export URL.

---

#### StockBee - 9 Million Movers

Stocks with **current volume ≥ 9M** and relative volume ≥ 1.25x. Highlights unusually active names.

**Data source:** FinViz Elite `9m_movers` export URL.

---

#### StockBee - 20% Weekly Movers

Stocks up or down **≥ 20%** in the past week. Merges +20% and -20% lists, sorted by absolute move.

**Data source:** FinViz Elite `20pct_weekly_up` and `20pct_weekly_down` export URLs.

---

#### StockBee - 4% Daily Gainers

Stocks up **≥ 4%** today.

**Data source:** FinViz Elite `4pct_daily` export URL.

---

#### Earnings Yesterday + Today

Stocks that reported earnings yesterday or today. USA, avg vol 1K+, price $1+.

**Data source:** FinViz Elite `earnings_yesterday_today_perf` export URL.

---

#### Leading Industries

Industries (or sectors) in the **top 20%** by combined weekly + monthly relative strength. Uses $1B+ USA universe, RSI > 60. Shows theme name and top 4 tickers by day change.

**Data source:** FinViz Elite `ind_1b` export; RS computed in-app.

---

#### Thematics Tracker

Themes (industries) with top 20% weekly and monthly performance. Each row: theme name, top 4 tickers by day change. “Top both” = in top 20% for both week and month.

**Data source:** FinViz Elite `ind_USA` export; themes grouped by industry.

---

#### Thematics by Sector

Top 30 themes by YTD (year) change, aggregated like Sector SPDRs: Chg, O Chg, Week, Month, Qtr, H.Year, Year. Themes with ≥ 3 stocks only.

**Data source:** FinViz Elite `ind_USA` export.

---

#### Thematics RRG (vs VTI)

RRG for **themes** vs VTI. Same logic as Sector RRG: RS-Ratio = year vs VTI, RS-Momentum = quarter vs VTI. Themes from Thematics by Sector.

**Data source:** Same as Thematics by Sector; VTI from FinViz.

---

#### Stockbee Momentum50

Stocks from Pradeep Bonde’s **Momentum50** list. Columns = dates; rows = tickers. Shows which names are in the list for each date.

**Data source:** Stockbee Momentum50 Google Sheet (public).

---

#### Stage Analysis

Classifies stocks into **Stage 1A–4C** based on price vs EMA10, SMA20, SMA50:
- **1A/1B:** Downtrend/basing
- **2A–2C:** Uptrend (early to late)
- **3A/3B:** Topping
- **4A–4C:** Downtrend

**Data source:** FinViz Elite `ind_stage` export (Technical view).

---

### Intraday Tab

#### Market Snapshot

Live snapshot of **QQQ, SPY, DIA, IWM, VIX** with price and % change. Refreshes every 5 minutes.

**Data source:** FinViz Elite `quote.ashx` for ETFs; **yfinance** for VIX (FinViz returns 404 for VIX).

---

#### Stocks In Play

Stocks with **news yesterday or today**, avg vol 1K+, price $1+, relative volume ≥ 2x. Highlights names with recent catalysts.

**Data source:** FinViz Elite `stocks_in_play` export URL.

---

#### Earnings Yesterday + Today

Same as the Market Metrics version: earnings reporters from yesterday or today.

**Data source:** FinViz Elite `earnings_yesterday_today_perf` export URL.

---

#### Pre-market Scanner

Pre-market movers **up 3%** or **down 3%**. USA, avg vol 1K+, price $1+, rel vol ≥ 1x. Merges +3% and -3% lists.

**Data source:** FinViz Elite `pre_market_scanner` and `pre_market_scanner_down` export URLs.

---

#### CNBC Pre-Market Watchlist

Stocks from the latest **CNBC Market Insider** premarket article. Scrapes the Market Insider page, finds the most recent premarket report, and parses tickers with headlines. Links to the CNBC article.

**Data source:** Web scrape of CNBC Market Insider; company names mapped to tickers via `COMPANY_TO_TICKER`, with fallback regex in article text.

---

## Ticker Links

Clicking any ticker opens a **TradingView** chart modal with the symbol embedded.

---

## Caching

Data is cached in `.cache/` for faster loads. Cache TTLs vary by widget (e.g., 5 min for live snapshot, 1 hr for screeners). Restarting the app warms cache from disk.

---

## Project Structure

```
Market Metrics Dashboard/
├── app.py              # Dash entry point
├── .env                 # API keys (FINVIZ_API_KEY, etc.)
├── watchlist.csv        # Optional user watchlist
├── requirements.txt
├── .cache/              # JSON cache files
└── src/
    ├── layout.py        # Widget layout and UI
    ├── callbacks.py     # Dash callbacks
    ├── data_fetcher.py  # FinViz, yfinance fetchers
    ├── calculations.py  # Key metrics, RRG, stage, thematics
    ├── constants.py     # Colors, URLs, filters
    ├── stockbee.py      # Stockbee API / Sheets
    ├── cnbc_premarket.py # CNBC premarket scraper
    ├── finviz_elite.py   # FinViz Elite API
    ├── cache.py         # Cache layer
    └── sortable_table.py # Sortable table component
```
