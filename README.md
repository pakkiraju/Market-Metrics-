# Market Metrics Dashboard

A Bloomberg-terminal-style dashboard for stock market analysis, built with Plotly Dash. Aggregates data from FinViz Elite, Stockbee (Pradeep Bonde), CNBC Market Insider, Yahoo Finance, Forex Factory, and rateprobability.com into a single dark-themed interface.

## Requirements

- **Python 3.10+**
- **FinViz Elite API** — Set `FINVIZ_API_KEY` in `.env` for most widgets

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

The dashboard has three tabs: **Macro Monitor**, **Market Metrics** (swing/position), and **Intraday** (day trading). Each widget can be toggled on/off via the Settings gear icon.

---

### Macro Monitor Tab

Central bank rates, inflation data, and economic calendar.

---

#### Rate Watch — Probabilities

Stacked bar chart of **Cut** (red), **Hold** (yellow), and **Hike** (green) probabilities for the next 6 central bank meetings. Currency dropdown supports USD, EUR, GBP, JPY, CAD, CHF, AUD, NZD. Data from rateprobability.com and CentralBank.watch.

---

#### Rate Watch — Rate Path

Line chart of **Expected Rate** vs **Current** rate for the next 8 meetings. Shows projected policy rate path per central bank.

---

#### Rate Watch — Distribution

Table of meeting dates, days until, expected rate, and Cut/Hold/Hike probabilities. Same currency selector as above.

---

#### Rate Watch — Rate Ranges

Fed-specific rate range probabilities (e.g., 4.25–4.50%, 4.50–4.75%). USD only.

---

#### Economic Calendar — Today

Today’s economic events from **Forex Factory** (nfs.faireconomy.media). Columns: time, country, impact, title, forecast, actual, previous. No API key required.

---

#### Consumer Price Index CPI

Bar chart of **Expected vs Actual** CPI YTD. Scraped from FinViz Elite economic calendar detail. Links to FinViz Elite.

---

#### Core Inflation Rate MoM

Bar chart of **Expected vs Actual** Core Inflation Rate (month-over-month) YTD. FinViz Elite.

---

#### Core Inflation Rate YoY

Bar chart of **Expected vs Actual** Core Inflation Rate (year-over-year) YTD. FinViz Elite.

---

### Market Metrics Tab

#### Key Metrics

Aggregates breadth statistics across five index groups: **NQ100** (NASDAQ 100), **SPY500** (S&P 500), **DJIA** (Dow Jones), **RUS2000** (Russell 2000), and **$1B+** (US stocks with market cap ≥ $1B and avg volume ≥ 1K).

For each group, the table shows:
- **Above / Below** — Count of stocks meeting a positive vs negative condition
- **%** — Percentage of stocks in the “above” condition

Rows include: Day Chg, Open Chg, Week, Month, Qtr, Half Year, Year (performance), Price vs SMA10/20/50/200, EMA10>SMA20, SMA20<SMA50, SMA50<SMA200, SMA20>SMA50>SMA200 (trend alignment), 4% Up vs 4% Down (daily breadth), New 20-Day Highs, New 20-Day Lows, and total stock count.

---

#### NQ100, SPY500 & DJIA Metrics

Bar charts of the Key Metrics **%** values for NASDAQ 100, S&P 500, and Dow Jones. Green bars = bullish breadth (e.g., >50% of stocks above SMA20); red = bearish. Lets you compare breadth across the three major indices.

---

#### RUS2000 & $1B+ Stocks

Same bar chart layout for Russell 2000 and the $1B+ universe. Used to compare small-cap and broad-market breadth.

---

#### StockBee Market Breadth Monitor

Summary cards for Stockbee-style breadth:
- **S&P 500** — Index level and daily change
- **T2108** — % of S&P 500 stocks above 200-day SMA (0–100)
- **5-Day Ratio** — Up 4%+ vs Down 4%+ over 5 days
- **10-Day Ratio** — Same over 10 days
- **Up 4%+ / Down 4%+** — Today’s counts

---

#### StockBee - Primary Breadth — Up/Down 4%+ Today

Line chart of daily **Up 4%+** and **Down 4%+** counts over time. Shows short-term breadth shifts.

---

#### StockBee - Breadth Ratios — 5-Day & 10-Day

Line chart of **5-Day** and **10-Day** breadth ratios (Up 4%+ / Down 4%+). Ratio > 1 = more gainers than losers; < 1 = more losers.

---

#### StockBee - Secondary Breadth — Up/Down 25%+ Qtr

Line chart of **Up 25%+** and **Down 25%+** counts over the quarter. Captures larger moves and longer-term breadth.

---

#### StockBee - S&P 500 — Last 60 Days

Line chart of S&P 500 index level over the last 60 days.

---

#### Qullamaggie

Stocks matching Kris Kullamägi’s **Episodic Pivot** setup:
- USA, avg volume ≥ 1K, price ≥ $1
- Gap up ≥ 10%
- Relative volume ≥ 2x

---

#### Minervini

Stocks matching Mark Minervini’s **Trend Template**:
- USA, avg vol 1K+, price $1+
- Price above SMA200, SMA150, SMA50
- SMA50 above SMA150 and SMA200
- Price within 25% of 52-week high
- Price within 25% of 52-week low (pullback)
- RSI(14) ≥ 70

---

#### O'Neil

Stocks matching William O’Neil’s **CANSLIM** criteria:
- USA
- ROE + Net Profit Margin ≥ 25%
- EPS growth filters (YOY, forward, TTM positive)
- Net margin positive

---

#### Watchlist

User-defined tickers from `watchlist.csv` in the project root. Shows price, change, volume, avg vol, rel vol, and ATR% for each ticker.

---

#### Sector SPDR ETFs

Table of sector ETFs (XLK, XLV, XLC, etc.) with gap, day change, week/month/qtr/half-year/year performance, last price, EMAs/SMAs, 52-week range, and ATR%. Sorted by ATR% and change.

---

#### RRG Sector Rotation

**Relative Rotation Graph** of 11 Sector SPDRs vs **VTI**:
- **X-axis (RS-Ratio):** 1-year performance vs VTI (normalized)
- **Y-axis (RS-Momentum):** Quarter performance vs VTI (normalized)

Quadrants: Improving (top-right), Leading (bottom-right), Weakening (bottom-left), Lagging (top-left). Each dot is a sector; hover for details.

---

#### S&P 500 Landscape Bubble Chart

Bubble chart of S&P 500 constituents by sector. Bubble size = market cap; color = valuation. Sector filter to focus on specific industries. Data from FinViz Elite export.

---

#### 97 Club

Stocks in the **$1B+ USA** universe with avg vol 1K+ and price $1+. Simple broad screener.

---

#### StockBee - 9 Million Movers

Stocks with **current volume ≥ 9M** and relative volume ≥ 1.25x. Highlights unusually active names.

---

#### StockBee - 20% Weekly Movers

Stocks up or down **≥ 20%** in the past week. Merges +20% and -20% lists, sorted by absolute move.

---

#### StockBee - 4% Daily Gainers

Stocks up **≥ 4%** today.

---

#### Earnings Yesterday + Today

Stocks that reported earnings yesterday or today. USA, avg vol 1K+, price $1+.

---

#### Leading Industries

Industries (or sectors) in the **top 20%** by combined weekly + monthly relative strength. Uses $1B+ USA universe, RSI > 60. Shows theme name and top 4 tickers by day change.

---

#### Thematics Tracker

Themes (industries) with top 20% weekly and monthly performance. Each row: theme name, top 4 tickers by day change. “Top both” = in top 20% for both week and month.

---

#### Thematics by Sector

Top 30 themes by YTD (year) change, aggregated like Sector SPDRs: Chg, O Chg, Week, Month, Qtr, H.Year, Year. Themes with ≥ 3 stocks only.

---

#### Thematics RRG (vs VTI)

RRG for **themes** vs VTI. Same logic as Sector RRG: RS-Ratio = year vs VTI, RS-Momentum = quarter vs VTI. Themes from Thematics by Sector.

---

#### Stockbee Momentum50

Stocks from Pradeep Bonde’s **Momentum50** list. Columns = dates; rows = tickers. Shows which names are in the list for each date.

---

#### Stage Analysis

Classifies stocks into **Stage 1A–4C** based on price vs EMA10, SMA20, SMA50:
- **1A/1B:** Downtrend/basing
- **2A–2C:** Uptrend (early to late)
- **3A/3B:** Topping
- **4A–4C:** Downtrend

---

### Intraday Tab

#### Market Snapshot

Live snapshot of **QQQ, SPY, DIA, IWM, VIX** with price and % change. Refreshes every 5 minutes.

---

#### Stocks In Play

Stocks with **news yesterday or today**, avg vol 1K+, price $1+, relative volume ≥ 2x. Highlights names with recent catalysts.

---

#### Earnings Yesterday + Today

Same as the Market Metrics version: earnings reporters from yesterday or today.

---

#### Top Gainers

Top 12 gainers by day change from the $1B+ USA universe (thematics data). Sorted by % change.

---

#### Top Losers

Top 12 losers by day change from the $1B+ USA universe (thematics data). Sorted by % change.

---

#### Pre-market Scanner

Pre-market movers **up 3%** or **down 3%**. USA, avg vol 1K+, price $1+, rel vol ≥ 1x. Merges +3% and -3% lists.

---

#### CNBC Pre-Market Watchlist

Stocks from the latest **CNBC Market Insider** premarket article. Scrapes the Market Insider page, finds the most recent premarket report, and parses tickers with headlines. Links to the CNBC article.

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
    ├── rate_watch_data.py # Central bank rate probabilities (rateprobability.com)
    ├── cpi_data.py      # CPI, Core Inflation (FinViz Elite)
    ├── economic_calendar.py # Forex Factory calendar
    ├── cache.py         # Cache layer
    └── sortable_table.py # Sortable table component
```

---

## Changelog

### [Unreleased]

- **Macro Monitor tab** — New tab for central bank rates, inflation, and economic calendar
- **Rate Watch** — Four widgets: Probabilities (stacked bar), Rate Path (line), Distribution (table), Rate Ranges (Fed-only). Supports USD, EUR, GBP, JPY, CAD, CHF, AUD, NZD. Data from rateprobability.com and CentralBank.watch
- **Economic Calendar** — Today’s events from Forex Factory (no API key)
- **CPI** — Consumer Price Index Expected vs Actual YTD bar chart (FinViz Elite)
- **Core Inflation MoM / YoY** — Core Inflation Rate Expected vs Actual YTD bar charts (FinViz Elite)
- **S&P 500 Landscape** — Bubble chart of S&P 500 constituents by sector and valuation
- **Top Gainers / Top Losers** — Intraday tab widgets showing top 12 gainers and losers
