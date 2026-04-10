# Market Metrics Dashboard

Bloomberg-style market terminal built with **Plotly Dash**. The app is organized into five main areas: **Should I Trade?**, **Macro Monitor**, **Market Metrics**, **Super Scanners**, and **Intraday**. Use the sidebar to switch views. **Market Metrics**, **Super Scanners**, and **Intraday** support per-widget visibility via the **Settings** (gear) icon. **Macro Monitor** is one full-page layout.

---

## API integrations

| Priority | Service | Purpose | Configuration |
|----------|---------|---------|---------------|
| **1 — Primary** | **FinViz Elite** | Screeners, exports, most tables, key metrics, sector data, live ETF quotes (non-VIX) | `FINVIZ_API_KEY` in `.env` |
| **2 — Secondary** | **FRED** (Federal Reserve Economic Data, St. Louis Fed) | Macro Monitor KPIs, fiscal block, historical charts | `FRED_API_KEY` — free at [FRED API keys](https://fred.stlouisfed.org/docs/api/api_key.html) |

**Other data sources (no dedicated “API key” row in `.env` unless noted):**

- **Yahoo Finance** (`yfinance`) — SPY/QQQ history, VIX/VVIX, `^TNX`, `DX-Y.NYB` for Should I Trade? and related logic.
- **Stockbee** — optional local API (`STOCKBEE_API_URL`, default `http://localhost:8000`) or **public Google Sheets** (Momentum50 + Market Breadth Monitor).
- **CNBC Market Insider** — HTML scrape for the pre-market watchlist widget.

---

## Requirements & setup

- **Python 3.10+**
- **FinViz Elite** subscription and API key for most equity widgets.
- **FRED API key** for Macro Monitor (recommended).

```bash
pip install -r requirements.txt
```

Create `.env` in the project root:

```
FINVIZ_API_KEY=your_finviz_elite_key
FRED_API_KEY=your_fred_key
```

Optional:

```
STOCKBEE_API_URL=http://localhost:8000
```

Run:

```bash
python app.py
```

---

## 1. Should I Trade? (“Market Quality Terminal”)

**Role:** Aggregates volatility, trend, breadth, momentum, and macro risk into scores and a **YES / CAUTION / NO** decision. Refreshes on an interval (~45s) and manual refresh.

**Data sources (by layer):**

| Layer | Main sources |
|-------|----------------|
| Volatility | `yfinance`: `^VIX` (level, 5d linear slope, 1y percentile), `^VVIX`; put/call is a **VIX-regime estimate**, not exchange OI. |
| Trend | `yfinance`: SPY (close vs SMA20/50/200, RSI(14) on ~1 month of closes), QQQ vs 50-day SMA; **regime** = uptrend if all three SPY MAs bullish, downtrend if all bearish, else chop. |
| Breadth | Cached **Key Metrics** for SPY500 (`all_key_metrics`): % above SMA20/50/200, 4% up/down counts, new 20d highs/lows; **Stockbee** sheet/API for **ratio5** / **ratio10** when available. **$1B+** row extracts participation and NH/NL for execution logic. |
| Momentum | `fetch_sector_data` (FinViz): 11 sector SPDRs; **spread** = avg day % of top 3 sectors minus bottom 3; **% higher highs** = (new 20d highs count / SPY500 stock count) × 100. |
| Macro | **`yfinance`** in `_fetch_macro`: **`^TNX`** (10Y yield) and **`DX-Y.NYB`** (dollar); **`score_macro`** penalizes large 5d yield moves. |

### Math: category scores (0–100)

Default **weights** (overridable via `src/should_i_trade_config.json`): volatility 25%, momentum 25%, trend 20%, breadth 20%, macro 10%.

- **Volatility:** Base score from VIX buckets (e.g. &lt;12 → 95, 12–15 → 88, …, ≥30 → 25). **5d slope** penalty: +15 if slope &gt;1, +8 if &gt;0.5; **−5** bonus if slope &lt;−0.5. Clamped to [0,100].
- **Trend:** Base from regime (uptrend 85, downtrend 25, chop 55); ± for QQQ vs 50d; RSI(14) adds if 40–70, subtracts if &gt;75 or &lt;30.
- **Breadth:** Starts at 50; maps **% above 200d** to tiers (e.g. ≥60 → 85); adjusts for **ratio5** (&gt;1.2 +10, &lt;0.8 −15); small bonus if new highs &gt; new lows.
- **Momentum:** From **sector spread** and optional **pct_higher_highs** bonus.
- **Macro:** **`score_macro`** starts at **70**; **−5** if the absolute **10Y** (`^TNX`) 5d change exceeds **0.15**. Inputs are only **`^TNX`** and **`DX-Y.NYB`** from `_fetch_macro`.

**Market Quality Score (MQS)** = weighted sum of the five category scores.

**Decision thresholds:** Swing default — YES if MQS ≥ 80, CAUTION if ≥ 60, else NO. Day mode tightens (85 / 65). Editable in config.

### Math: Execution Window Score (EWS)

Separate blended score for “can I execute?” Uses **breakout health**: weighted combination of **$1B+** average % above SMA20/50/200, **new 20d highs %** (capped contribution), **NH/(NH+NL)**, and **StockBee 5d ratio** (mapped to 0–100 via `(ratio5 − 0.5) × 80`). Subcomponents feed YES/NO/Mixed labels for breakouts, leaders, pullbacks, follow-through. See `src/should_i_trade_scoring.py` for exact weights and gates.

---

## 2. Macro Monitor (“Macro Intelligence”)

**Role:** Read-only macro dashboard: KPI strip, signal donut, narrative, fiscal snapshot, click-any-KPI for long history charts.

**Data source:** **100% FRED API** (`api.stlouisfed.org`), parallel series fetch, cached. Original agency labels are preserved in the UI (BLS, BEA, EIA, Treasury, Michigan Survey) as *via FRED*.

### KPI transforms (math)

| Metric | FRED series (ids) | Transform |
|--------|-------------------|-----------|
| Fed funds | `DFEDTARL`, `DFEDTARU`, `DFF` | **Target range** from lower/upper; subtitle shows **effective** `DFF`; 30d sparkline on `DFF`. |
| CPI / Core CPI / PPI / PCE / Core PCE | `CPIAUCSL`, `CPILFESL`, `PPIACO`, `PCEPI`, `PCEPILFE` | **YoY %** on monthly index: \((V_t / V_{t-12} - 1) \times 100\). Sparkline = last 24 **monthly YoY** values. |
| Unemployment | `UNRATE` | Latest **level** (%). |
| NFP (m/m) | `PAYEMS` | **Month-over-month change** in **thousands**: last − previous; spark = series of first differences. |
| Brent | `DCOILBRENTEU` | Latest **$/bbl** level. |
| S&P 500 | `SP500` | Latest **index level**; trend vs ~21 sessions ago. |
| Michigan sentiment | `UMCSENT` | Latest **index** (%). |
| Deficit | `FYFSD` | **FY** surplus/deficit; millions USD; negative = deficit in FRED convention; display scales to trillions. |

### Fiscal block

Rows use: `GFDEBTN`, `FYFSD`, `GFDEGDQ188S`, `FGRECPT`, `FGEXPND`, `FYOINT` with documented USD units (millions vs billions) per series.

### Signal donut & narrative

`src/macro_signals.py` maps each KPI to **hawkish / dovish / neutral / mixed / tightening** (threshold-based, e.g. CPI YoY &gt;3 → hawkish, &lt;2 → dovish; unemployment &gt;5 → dovish, &lt;4 → hawkish; fed funds midpoint &gt;4 → tightening; deficit → tightening). Counts drive the donut; **dominant label** picks the headline bias. **Bottom line** text stitches headline CPI, core, labor, energy, policy context.

Optional copy overrides: `config/macro_cbo.yaml`.

---

## 3. Market Metrics tab

Widgets are toggled in Settings. Below: **widget → data source → math / behavior**.

### Key Metrics

- **Source:** One FinViz Elite **export.ashx** call for the full **v=152** column set (`FINVIZ_USA_FULL_V152_EXPORT`, no country filter), then in-app filtering per index (NQ100, SPY500, DJIA, RUS2000, **$1B+**). Optional extra **export.ashx** counts only for **New 20-Day Highs/Lows** if the bulk CSV lacks usable 20-day high/low columns. **`FINVIZ_USA_FULL_V152_SCREENER`** is the same query on **screener.ashx** for browser cross-checks.
- **Universe:** NQ100, SPY500, DJIA, RUS2000, **$1B+** (USA, cap ≥ $1B, avg vol ≥ 1K, price ≥ $1).
- **Math:** For each row, **above** = count meeting “bullish” condition, **below** = opposite where applicable, **%** = above / group size × 100 (except **4% row** uses up-count / N for the % column display; new highs/lows use count / N).
- **Returns** in `calculations.compute_indicators`: day % from last vs prior close; **week/month/qtr/half/year** = \((C_t - C_{t-k}) / C_{t-k} \times 100\) with **k = 5, 21, 63, 126, 252** trading days.
- **SMA/EMA, ATR(14), 20d range position, 52w hi/lo, new 20d hi/lo** per ticker; aggregation as in `compute_key_metrics_for_group`.

### NQ100, SPY500 & DJIA Metrics (chart2)

- **Source:** Same as Key Metrics.
- **Math:** Horizontal bar chart of the **%** column for selected rows (breadth %) for NQ100, SPY500, DJIA. Green/red styling by row semantics.

### RUS2000 & $1B+ Stocks (chart3)

- **Source / math:** Same pattern for Russell 2000 and $1B+ universes.

### Watchlist

- **Source:** `watchlist.csv` + FinViz bulk/API style data for listed symbols (and optional sector dropdown flows in UI).
- **Math:** Standard quote change, volume, ATR%, etc., from same indicator pipeline as other tables.

### Sector SPDR ETFs

- **Source:** FinViz sector export.
- **Math:** Sort by **ATR%** and day change (see `compute_sector_data`). Columns mirror FinViz: gap, multi-horizon performance, MAs, 52w range, ATR%.

### RRG Sector Rotation

- **Source:** Sector ETF performance + **VTI** benchmark (`fetch_benchmark_performance`).
- **Math:** For each sector, **raw RS-Ratio** = sector **YTD or year** % minus VTI **year** %; **raw RS-Momentum** = sector **quarter** % minus VTI **quarter** %. Vectors are **cross-sectionally normalized** to mean 100, spread scaled by std×10 so the cloud is comparable (see `_normalize_rrg_rows`). Quadrants: Leading / Improving / Weakening / Lagging.

### S&P 500 Landscape Bubble Chart

- **Source:** FinViz `export.ashx` **v=111** overview + **v=121** valuation for **S&P 500** constituents (`constants.FINVIZ_EXPORT_URLS` `sp500_landscape_*`).
- **Math:** **X** = revenue (billions), **Y** = net income (billions), **size** = sqrt-scaled **market cap** between min/max log-mapped to marker size, **color** = 12-month % change (piecewise red–green). Labels on largest bubbles by mcap threshold.

### Leading Industries

- **Source:** `$1B+` universe (`ind_$1B+`), industry names from export or overview map.
- **Math:** Per industry, mean **week** and **month** % change across members; **percentile rank** each horizon; keep industries in **top 20%** on week **or** month (union). Flag **top_both** if in top 20% on **both**. Show top **4** tickers by **day** %.

### Thematics Tracker

- **Source:** `fetch_thematics_data` (USA, price/vol filters) — **theme** column from industry/sector.
- **Math:** Same **top 20% week/month** union and **top_both** as Leading Industries, but keyed by **theme**.

### Thematics by Sector (Top YTD)

- **Source:** `ind_USA` export.
- **Math:** Theme = industry, else sector; aggregate **mean** day/open/week/month/qtr/half/year changes by theme; keep themes with **≥3** stocks; **top 30** by **year** %.

### Thematics RRG (vs VTI)

- **Source:** Same aggregated theme rows + VTI benchmark.
- **Math:** Same as sector RRG but **RS-Ratio** / **RS-Momentum** use theme **year** and **quarter** mean performance vs VTI; labels truncated for dots.

### Stockbee Momentum50

- **Source:** Google Sheet (gviz) or cached; public sheet ID in `stockbee.py`.
- **Math:** Matrix of dates × tickers present on each published list.

### StockBee Market Breadth Monitor

- **Source:** Stockbee API `/api/pplx-market-data` if up; else **Market Breadth** Google Sheet.
- **Math:** Reads latest row: **up4**, **down4**, **ratio5**, **ratio10**, **T2108** (% S&P names above 200d), **S&P 500** level and day change, universe count — column indices fixed in parser.

### StockBee — Primary Breadth (Up/Down 4%+ today)

- **Source:** Breadth **history** (API or sheet-derived).
- **Math:** Time series of **up4** and **down4** by date.

### StockBee — Breadth Ratios (5d & 10d)

- **Source:** History; if sheet-only, **ratio5/ratio10** recomputed over rolling 5/10 rows as sum(up)/sum(down) per window.
- **Math:** Plotted ratios; **&gt;1** means more advancing than declining volume on that definition.

### StockBee — Secondary Breadth (Up/Down 25%+ Qtr)

- **Source:** Sheet columns **up25q** / **down25q** (quarterly movers).
- **Math:** Dual line chart over history.

### StockBee — S&P 500 Last 60 Days

- **Source:** Same history stream, **S&P 500** column.
- **Math:** Line = index level over time (60 points max in fetch).

### Stage Analysis

- **Source:** FinViz export for broad US liquid universe (`fetch_stage_indicators`).
- **Math:** `classify_stage`: compares **close** to **EMA10**, **SMA20**, **SMA50** and distance **close/SMA50** to assign **1A–4C** (trend / extension buckets per code; e.g. above all MAs and ext ≥1.07 → **2C**). Histogram = count per stage.

---

## 4. Super Scanners tab

Each table is a **FinViz Elite screener/export** (see `FINVIZ_SCREENER_URLS` / `FINVIZ_EXPORT_URLS` in `src/constants.py`). Below is intent-level description; exact filters are in the URL definitions.

| Widget | Data | Idea |
|--------|------|------|
| **Qullamaggie** | `qulla_episodic` export | USA, gap up ≥10%, rel vol ≥2×, price ≥$1, avg vol ≥1K (Episodic Pivot style). |
| **Minervini** | `minervini` export | Trend Template–style stacked filters: price above SMA150/200, ordered MAs, 52w proximity, RSI(14) ≥ 70, etc. |
| **O’Neil** | CANSLIM-style fundamentals | EPS/ROE/margin filters per URL. |
| **Jeff Sun —** (CANSLIM, High ADR%, Extended Bases, 1w/4w/13w/26w movers, IPO, High Short Float, Liquid ETFs) | Per-key exports | Momentum, volatility, liquidity, and fundamental filters as named. |
| **Julian Komar — Strongest** | `julian_komar_strongest` | Small-cap, stocks only, 52w high proximity, SMA50 posture, weekly sort. |
| **97 Club** | `ind_97_club` / `$1B+` data | **Top 3%** day/week/month **percentile ranks** simultaneously; top 35 by day change, enriched with ATR if needed. |
| **9 Million Movers** | `ind_9m_movers` | Volume ≥9M, rel vol ≥1.25×; top movers by day %. |
| **20% Weekly Movers** | FinViz **up** and **down** 20% weekly URLs | Merged list, sorted by magnitude. |
| **4% Daily Gainers** | `ta_perf_4to-d` export | Day **up ≥4%** broad market. |
| **Earnings Calendar — This Week** | `earnings_this_week_*` exports | **Earnings date this week**, USA, liquidity filters; merges overview/financial/performance columns. |

---

## 5. Intraday tab

| Widget | Data | Math / notes |
|--------|------|----------------|
| **Market Snapshot** | FinViz Elite quotes for QQQ, SPY, DIA, IWM; **VIX** via `yfinance` | Cached ~5 min. |
| **Stocks In Play** | FinViz export `stocks_in_play` | News yesterday/today, rel vol ≥2×, etc. |
| **Earnings Yesterday + Today** | FinViz earnings filter | Merged with performance columns. |
| **Top Gainers / Losers** | Same universe as **Thematics** (`fetch_thematics_data`) | **Top 12** by **day_chg** (nlargest / nsmallest). |
| **Pre-market Scanner** | FinViz premarket export | **±3%** movers, liquidity filters. |
| **CNBC Pre-Market Watchlist** | Scrape latest CNBC premarket article | Parsed tickers + headlines + link. |

---

## Quick reference: where data comes from

- **FinViz Elite:** Key Metrics, charts, sectors, RRG inputs, Super Scanners, most Intraday tables, earnings calendar, stage, landscape, live ETFs.
- **FRED:** Macro Monitor only (KPIs + fiscal + history charts).
- **Yahoo Finance:** Should I Trade? (indices, VIX, rates, FX), VIX in Market Snapshot.
- **Stockbee (Sheets/API):** Breadth widgets, Momentum50, optional ratio lines in Should I Trade?.
- **CNBC:** Pre-market watchlist widget only.

---

## Ticker clicks (chart + fundamentals)

Clicking any **`.tv-ticker`** symbol (tables, grids, watchlist, etc.) opens a modal with:

1. **TradingView** embedded chart (same behavior as before; client-side iframe URL).
2. **Fundamentals panel** to the right (desktop) or below (narrow widths): a dense, Finviz-style grid of **all columns** from the cached FinViz Elite **USA full export** (v=152) for that symbol when it appears in `usa_full_v152`. If the symbol is not in that export, the app falls back to **`quote.ashx`** (single-ticker snapshot) when Elite is configured.

**Implementation notes:**

| Piece | Role |
|-------|------|
| `GET /api/ticker-metrics/<symbol>` | Flask route on `app.server`; returns JSON `{ ok, symbol, source, pairs }`. `source` is `usa_v152`, `quote`, or unavailable. |
| `src/ticker_metrics.py` | Looks up the raw CSV row, ordered field list, large-number formatting (commas + K/M/B for Market Cap, Enterprise Value, Volume, Avg Volume, Income, Sales, etc.), quote fallback. |
| `app.py` (inline script + CSS) | Opens modal, fetches `/api/ticker-metrics/...`, renders six columns of label/value rows; **News URL** shows as **Article** (hyperlink); labels split sensibly (e.g. parentheses, `Perf …`, `Inst …`, `Insider …`). Metrics area scrolls **vertically** only; no horizontal scroll. |

**Formatting:** Selected numeric fields (market cap, volume, enterprise value, average volume, and similar) are normalized for display with commas and **K / M / B** suffixes. **Duplicate CSV headers** (e.g. FinViz `Dividend` twice) may still collapse to one value in the parsed row—same limitation as the bulk CSV import.

---

## Caching

JSON cache under `.cache/`; TTLs vary (e.g. fast for live snapshot, longer for screeners). Per-widget refresh buttons invalidate that widget’s cache keys only.

---

## Project structure (abbrev.)

```
Market Metrics Dashboard/
├── app.py                  # Dash app + `/api/ticker-metrics/<symbol>` route
├── .env                    # FINVIZ_API_KEY, FRED_API_KEY, …
├── watchlist.csv
├── config/macro_cbo.yaml   # Optional Macro Monitor labels
├── src/
│   ├── layout.py           # Tabs + widget registry
│   ├── callbacks.py
│   ├── data_fetcher.py     # FinViz + helpers
│   ├── ticker_metrics.py   # USA v152 row lookup + modal metrics payload
│   ├── finviz_elite.py
│   ├── calculations.py     # Key metrics, RRG, stage, thematics
│   ├── macro_fred_client.py
│   ├── macro_fred_series.py  # FRED ids + transforms
│   ├── macro_data.py
│   ├── macro_signals.py
│   ├── macro_monitor_layout.py
│   ├── should_i_trade_data.py
│   ├── should_i_trade_scoring.py
│   ├── stockbee.py
│   ├── cnbc_premarket.py
│   └── cache.py
└── assets/macro_terminal.css   # Scoped Macro Monitor styling
```

---

## Other folders in this workspace

- **`Rebalances Dashboard/`** — Static HTML + SheetJS: MSCI / S&P rebalance **Excel** parsing in the browser. See that folder’s README.
- **`TradeAlerts/`** — Expo + Supabase social trading app; separate stack. See that folder’s README.
