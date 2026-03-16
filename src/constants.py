"""Color tokens, stage definitions, and shared constants."""

# ---------- Graph config (responsive for tab-switch resize fix) ----------
GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}
GRAPH_CONFIG_ZOOM = {"displayModeBar": False, "scrollZoom": True, "responsive": True}

# ---------- Dark theme palette (matches old base.css) ----------
COLORS = {
    "bg": "#0a0e17",
    "surface": "#111827",
    "surface2": "#1a2235",
    "surface3": "#243049",
    "border": "#1e2a3a",
    "border_light": "#2a3a52",
    "text": "#e2e8f0",
    "text_muted": "#8892a4",
    "text_faint": "#4a5568",
    "green_strong": "#166534",
    "green": "#22c55e",
    "green_light": "#4ade80",
    "green_bg": "rgba(34,197,94,0.15)",
    "green_cell": "#1a4d2e",
    "green_cell_strong": "#0d6b2e",
    "red_strong": "#7f1d1d",
    "red": "#ef4444",
    "red_light": "#f87171",
    "red_bg": "rgba(239,68,68,0.15)",
    "red_cell": "#4d1a1a",
    "red_cell_strong": "#6b0d0d",
    "blue_tml": "#1e40af",
    "blue_tml_bg": "rgba(30,64,175,0.3)",
    "accent": "#06b6d4",
    "yellow": "#eab308",
    "yellow_bg": "rgba(234,179,8,0.15)",
    "yellow_cell": "#4d3d0a",
    "orange": "#f97316",
    "orange_bg": "rgba(249,115,22,0.15)",
    "orange_cell": "#4d2a0a",
    "white": "#ffffff",
}

# ---------- Section header backgrounds ----------
HEADER_COLORS = {
    "default": "#1a365d",
    "teal": "#0f4c5c",
    "green": COLORS["green_strong"],
    "red": COLORS["red_strong"],
    "purple": "#4c1d95",
    "orange": "#7c2d12",
}

# ---------- Cell color thresholds ----------
def pct_color(pct):
    """Return (background, text) tuple for a percentage metric cell."""
    if pct is None:
        return COLORS["surface"], COLORS["text_muted"]
    if pct >= 65:
        return COLORS["green_cell_strong"], "#86efac"
    if pct >= 55:
        return COLORS["green_cell"], "#86efac"
    if pct >= 50:
        return "rgba(34,197,94,0.12)", "#86efac"
    if pct >= 45:
        return COLORS["surface"], COLORS["text_muted"]
    if pct >= 35:
        return COLORS["red_cell"], "#fca5a5"
    return COLORS["red_cell_strong"], "#fca5a5"


def chg_color(val):
    """Return text color for a change value."""
    if val is None:
        return COLORS["text_muted"]
    return COLORS["green_light"] if val >= 0 else COLORS["red_light"]


# ---------- Stage analysis ----------
STAGE_LABELS = ["1A", "1B", "2A", "2B", "2C", "3A", "3B", "4A", "4B", "4C"]

STAGE_COLORS = {
    "1A": (COLORS["surface2"], COLORS["text_muted"]),
    "1B": (COLORS["surface2"], COLORS["text_muted"]),
    "2A": (COLORS["green_cell"], COLORS["green_light"]),
    "2B": (COLORS["yellow_cell"], "#fde68a"),
    "2C": (COLORS["orange_cell"], "#fdba74"),
    "3A": (COLORS["red_cell"], COLORS["red_light"]),
    "3B": (COLORS["red_cell"], COLORS["red_light"]),
    "4A": (COLORS["red_cell_strong"], COLORS["red_light"]),
    "4B": (COLORS["red_cell_strong"], COLORS["red_light"]),
    "4C": (COLORS["red_cell_strong"], COLORS["red_light"]),
}

STAGE_BAR_COLORS = {
    "1A": "#4a5568",
    "1B": "#64748b",
    "2A": "#22c55e",
    "2B": "#eab308",
    "2C": "#f97316",
    "3A": "#ef4444",
    "3B": "#ea580c",
    "4A": "#ef4444",
    "4B": "#dc2626",
    "4C": "#7f1d1d",
}

# ---------- Key-metrics row labels ----------
KEY_METRIC_ROWS = [
    "Day Chg",
    "Open Chg",
    "Week",
    "Month",
    "Qtr",
    "Half Year",
    "Year",
    "Price to SMA10",
    "Price to SMA20",
    "Price to SMA50",
    "Price to SMA200",
    "EMA10>SMA20",
    "SMA20<SMA50",
    "SMA50<SMA200",
    "SMA20<SMA50<SMA200",
    "4% Up vs 4% Down",
    "New 20-Day Highs",
    "New 20-Day Lows",
    "Stocks",
]

INDEX_GROUPS = ["NQ100", "SPY500", "DJIA", "RUS2000", "$1B+"]

# Base filter for each index (for building metric-specific screener URLs)
INDEX_BASE_FILTERS = {
    "NQ100": "geo_usa,idx_ndx",
    "SPY500": "geo_usa,idx_sp500",
    "DJIA": "geo_usa,idx_dji",
    "RUS2000": "geo_usa,idx_rut",
    "$1B+": "cap_1to,geo_usa,sh_avgvol_o1000,sh_price_o1",
}

# Metric filters for Key Metrics table row links: (above_filter, below_filter)
# Above = stocks meeting positive condition; Below = stocks meeting negative condition
KEY_METRIC_FILTERS = {
    "Day Chg": ("ta_change_u", "ta_change_d"),
    "Open Chg": ("ta_changeopen_u", "ta_changeopen_d"),
    "Week": ("ta_perf_1wup", "ta_perf_1wdown"),
    "Month": ("ta_perf_4wup", "ta_perf_4wdown"),
    "Qtr": ("ta_perf_13wup", "ta_perf_13wdown"),
    "Half Year": ("ta_perf_26wup", "ta_perf_26wdown"),
    "Year": ("ta_perf_ytdup", "ta_perf_ytddown"),
    "Price to SMA10": ("tad_0_sma:10:sma:d|abv:::1|close::close:d", "tad_0_sma:10:sma:d|blw:::1|close::close:d"),
    "Price to SMA20": ("tad_0_sma:20:sma:d|abv:::1|close::close:d", "tad_0_sma:20:sma:d|blw:::1|close::close:d"),
    "Price to SMA50": ("tad_0_sma:50:sma:d|abv:::1|close::close:d", "tad_0_sma:50:sma:d|blw:::1|close::close:d"),
    "Price to SMA200": ("tad_0_sma:200:sma:d|abv:::1|close::close:d", "tad_0_sma:200:sma:d|blw:::1|close::close:d"),
    # Format from FinViz: tad_0_close::close:d,tad_1_ema:10:ema:d|abv:::|sma:20:sma:d
    "EMA10>SMA20": ("tad_0_close::close:d,tad_1_ema:10:ema:d|abv:::|sma:20:sma:d", "tad_0_close::close:d,tad_1_ema:10:ema:d|blw:::|sma:20:sma:d"),
    # Flipped to show bearish perspective: Above = below SMA, Below = above SMA
    "SMA20<SMA50": ("tad_0_sma:50:sma:d|blw:::1|sma:20:sma:d", "tad_0_sma:50:sma:d|abv:::1|sma:20:sma:d"),
    "SMA50<SMA200": ("tad_0_sma:200:sma:d|blw:::1|sma:50:sma:d", "tad_0_sma:200:sma:d|abv:::1|sma:50:sma:d"),
    "SMA20<SMA50<SMA200": ("tad_0_sma:200:sma:d|blw:::1|sma:50:sma:d,tad_1_sma:20:sma:d|blw:::|sma:50:sma:d", "tad_0_sma:200:sma:d|abv:::1|sma:50:sma:d,tad_1_sma:20:sma:d|abv:::|sma:50:sma:d"),
    "4% Up vs 4% Down": ("ta_change_u4", "ta_change_d4"),
    "New 20-Day Highs": ("ta_highlow20d_nh", None),
    "New 20-Day Lows": ("ta_highlow20d_nl", None),
}


def build_metric_screener_url(index_key: str, metric_label: str, direction: str, for_export: bool = False) -> str | None:
    """Build FinViz URL for a metric row. direction is 'above' or 'below'.
    for_export=True: export.ashx (CSV, for fetch_metric_count). for_export=False: screener.ashx (opens in browser)."""
    from urllib.parse import quote
    base = INDEX_BASE_FILTERS.get(index_key)
    filters = KEY_METRIC_FILTERS.get(metric_label)
    if not base or not filters:
        return None
    up_f, down_f = filters
    if direction == "above" and up_f:
        filter_str = up_f
    elif direction == "below" and down_f:
        filter_str = down_f
    else:
        return None
    encoded = quote(f"{base},{filter_str}", safe="")
    ft = "&ft=3" if ("tad_" in filter_str or filter_str.startswith("ta_")) else ""
    endpoint = "export.ashx" if for_export else "screener.ashx"
    return f"https://elite.finviz.com/{endpoint}?v=111&f={encoded}{ft}"


# ---------- FinViz Elite screener links (open in browser, not CSV download) ----------
FINVIZ_SCREENER_URLS = {
    "NQ100": "https://elite.finviz.com/screener.ashx?v=111&f=geo_usa%2Cidx_ndx",
    "SPY500": "https://elite.finviz.com/screener.ashx?v=111&f=geo_usa%2Cidx_sp500",
    "DJIA": "https://elite.finviz.com/screener.ashx?v=111&f=geo_usa%2Cidx_dji",
    "RUS2000": "https://elite.finviz.com/screener.ashx?v=111&f=geo_usa%2Cidx_rut",
    "$1B+": "https://elite.finviz.com/screener.ashx?v=111&f=cap_1to%2Cgeo_usa%2Csh_avgvol_o1000%2Csh_price_o1",
    "4pct_daily": "https://elite.finviz.com/screener.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_perf_4to-d&o=-change",
    "20pct_weekly_up": "https://elite.finviz.com/screener.ashx?v=111&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_perf_1w20o&o=-change",
    "20pct_weekly_down": "https://elite.finviz.com/screener.ashx?v=111&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_perf_1w20u&o=-change",
    # 9M Movers: $1B+ cap, 9M+ volume, 1.25+ rel vol (screener for link)
    "9m_movers": "https://elite.finviz.com/screener.ashx?v=111&f=cap_1to,geo_usa,sh_curvol_9000tox,sh_price_o1,sh_relvol_1.25to",
    # 97 Club: $1B+ universe (screener for link)
    "club97": "https://elite.finviz.com/screener.ashx?v=111&f=cap_1to,geo_usa,sh_avgvol_o1000,sh_price_o1",
    # O'Neil / CANSLIM: EPS growth, ROE, net margin
    "oneil": "https://elite.finviz.com/screener.ashx?v=161&f=fa_epsyoy_o25%2Cfa_epsyoy1_o25%2Cfa_epsyoyttm_pos%2Cfa_netmargin_pos%2Cfa_roe_pos%2Cgeo_usa",
    # Minervini Trend Template (base filters; full template uses tad_*)
    "minervini": "https://elite.finviz.com/screener.ashx?v=141&f=geo_usa%2Csh_avgvol_o1000%2Csh_price_o1%2Cta_sma200_pa",
    # Qullamaggie Episodic Pivot (gap up 10%+, rel vol 2+)
    "qullamaggie": "https://elite.finviz.com/screener.ashx?v=141&f=geo_usa%2Cta_gap_u10%2Csh_relvol_o2%2Csh_price_o1%2Csh_avgvol_o1000",
    # Breakouts: 52w high 0-25%, perf 30d to -4w, price above SMA20
    "qulla_breakouts": "https://elite.finviz.com/screener.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_highlow52w_0to25-bhx,ta_perf_30to-4w,tad_0_close::close:d|abvpct::10:|sma:20:sma:d&ft=3&o=-change",
    # Parabolic Short: small cap (300–1000% YTD, 100%+ week), large cap (50%+ month)
    "qulla_ps_small": "https://elite.finviz.com/screener.ashx?v=141&f=cap_to9,geo_usa,ta_perf_300to-4w,ta_perf2_100to-1w&ft=4&o=-change",
    "qulla_ps_large": "https://elite.finviz.com/screener.ashx?v=141&f=cap_largeover,geo_usa,ta_perf_50to-4w&o=-change",
    # Leading Industries: $1B+, USA, RSI>60 (top 20% by weekly+monthly RS computed in-app)
    "leading": "https://elite.finviz.com/screener.ashx?v=111&f=cap_1to,geo_usa,sh_avgvol_o1000,sh_price_o1,tad_0_rsi:14:rsi:d|abveq:::|value:::60&o=-change",
    # Earnings Yesterday + Today
    "earnings_yesterday_today": "https://elite.finviz.com/screener.ashx?v=111&f=earningsdate_today|yesterday,geo_usa,sh_avgvol_o1000,sh_price_o1&o=change",
    # Earnings This Week (Market Metrics). Overview (v=111) for mcap; Performance (v=141) for avg vol, rel vol.
    "earnings_this_week": "https://elite.finviz.com/screener.ashx?v=111&f=earningsdate_thisweek,geo_usa,sh_avgvol_o1000,sh_price_o1&ft=4&o=-marketcap",
    "earnings_this_week_perf": "https://elite.finviz.com/screener.ashx?v=141&f=earningsdate_thisweek,geo_usa,sh_avgvol_o1000,sh_price_o1&ft=4&o=-marketcap",
    # Stocks In Play: news yesterday|today, avg vol 1000+, price $1+, rel vol 2+
    "stocks_in_play": "https://elite.finviz.com/screener.ashx?v=141&f=geo_usa,news_date_yesterday|today,sh_avgvol_o1000,sh_price_o1,sh_relvol_o2&o=-change",
    # Pre-market Scanner: USA, avg vol 1000+, price $1+, rel vol 1+, up 3%
    "pre_market_scanner": "https://elite.finviz.com/screener.ashx?v=151&f=geo_usa,sh_avgvol_o1000,sh_price_o1,sh_relvol_o1,ta_change_u3&o=-change",
    # Pre-market Scanner (down 3%)
    "pre_market_scanner_down": "https://elite.finviz.com/screener.ashx?v=151&f=geo_usa,sh_avgvol_o1000,sh_price_o1,sh_relvol_o1,ta_change_d3&o=change",
    # Thematics Tracker
    "thematics": "https://elite.finviz.com/screener.ashx?v=111&f=geo_usa,sh_avgvol_o1000,sh_price_o1",
    # Economic Calendar
    "economic_calendar": "https://elite.finviz.com/calendar/economic",
    # CPI (Consumer Price Index)
    "cpi": "https://elite.finviz.com/calendar/economic/detail/UNITEDSTACONPRIINDCP",
    # Core Inflation Rate MoM / YoY
    "core_inflation_mom": "https://elite.finviz.com/calendar/economic/detail/USACIRM",
    "core_inflation_yoy": "https://elite.finviz.com/calendar/economic/detail/USACORECPIRATE",
}

# Rate Watch — external links per central bank
RATE_WATCH_LINKS = {
    "USD": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
    "EUR": "https://centralbank.watch/european-central-bank",
    "GBP": "https://centralbank.watch/bank-of-england",
    "JPY": "https://centralbank.watch/bank-of-japan",
    "CAD": "https://centralbank.watch/bank-of-canada",
    "CHF": "https://centralbank.watch/swiss-national-bank",
    "AUD": "https://centralbank.watch/reserve-bank-of-australia",
    "NZD": "https://centralbank.watch/reserve-bank-of-new-zealand",
}

# Stockbee (Pradeep Bonde) — external links
STOCKBEE_LINKS = {
    "momentum50": "https://docs.google.com/spreadsheets/d/1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M/",
    "market_monitor": "https://docs.google.com/spreadsheets/d/1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE/",
}

# Export URLs for data fetching (export.ashx returns CSV). v=111 Overview, v=141 Performance (Perf Week), v=171 Technical (ATR).
FINVIZ_EXPORT_URLS = {
    "9m_movers": "https://elite.finviz.com/export.ashx?v=111&f=cap_1to,geo_usa,sh_curvol_9000tox,sh_price_o1,sh_relvol_1.25to",
    "club97": "https://elite.finviz.com/export.ashx?v=111&f=cap_1to,geo_usa,sh_avgvol_o1000,sh_price_o1",
    # 20% weekly: c=1,41,47,61,62,63,64,65 = Ticker,PerfWeek,ATR,AvgVol,RelVol,Price,Change,Volume (single request each)
    "20pct_weekly_up": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_perf_1w20o&o=-change&c=1,41,47,61,62,63,64,65",
    "20pct_weekly_down": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_perf_1w20u&o=-change&c=1,41,47,61,62,63,64,65",
    # 4% daily: c=1,47,61,62,63,64,65 = Ticker,ATR,AvgVol,RelVol,Price,Change,Volume (single request)
    "4pct_daily": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_perf_4to-d&o=-change&c=1,47,61,62,63,64,65",
    "earnings_yesterday_today": "https://elite.finviz.com/export.ashx?v=111&f=earningsdate_today|yesterday,geo_usa,sh_avgvol_o1000,sh_price_o1&o=change",
    "earnings_yesterday_today_perf": "https://elite.finviz.com/export.ashx?v=141&f=earningsdate_today|yesterday,geo_usa,sh_avgvol_o1000,sh_price_o1&o=-change",
    # Earnings This Week: Overview for Market Cap; Performance for Avg Vol, Rel Vol. ft=4 for earnings date filter.
    "earnings_this_week_overview": "https://elite.finviz.com/export.ashx?v=111&f=earningsdate_thisweek,geo_usa,sh_avgvol_o1000,sh_price_o1&ft=4&o=-marketcap",
    "earnings_this_week_perf": "https://elite.finviz.com/export.ashx?v=141&f=earningsdate_thisweek,geo_usa,sh_avgvol_o1000,sh_price_o1&ft=4&o=-marketcap&c=1,47,61,62,63,64,65",
    # Stocks in Play: c=1,137,47,61,62,63,64,65 = Ticker,News/Link,ATR,AvgVol,RelVol,Price,Change,Volume
    "stocks_in_play": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,news_date_yesterday|today,sh_avgvol_o1000,sh_price_o1,sh_relvol_o2&o=-change&c=1,137,47,61,62,63,64,65",
    # Pre-market Scanner: USA, avg vol 1000+, price $1+, rel vol 1+, up 3%. Columns: Ticker, Gap, Avg Volume, Rel Volume, Volume, Price, Change, News Time, News Title, Daily Digest, News URL
    "pre_market_scanner": "https://elite.finviz.com/export.ashx?v=151&f=geo_usa,sh_avgvol_o1000,sh_price_o1,sh_relvol_o1,ta_change_u3&o=-change&c=1,61,62,65,63,64,136,137,138",
    # Pre-market Scanner (down 3%): same columns
    "pre_market_scanner_down": "https://elite.finviz.com/export.ashx?v=151&f=geo_usa,sh_avgvol_o1000,sh_price_o1,sh_relvol_o1,ta_change_d3&o=change&c=1,61,62,65,63,64,136,137,138",
    # Thematics Tracker: USA, avg vol 1K+, price $1+. v=141 + c= for Sector,Industry,PerfWeek,PerfMonth,PerfQtr,PerfYear,Change. Theme = Industry (many themes).
    "thematics": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1&o=-change&c=1,3,4,41,42,43,45,64",
    # Qullamaggie: c=1,47,61,62,63,64,65 = Ticker,ATR,AvgVol,RelVol,Price,Change,Volume (single request per screener)
    "qulla_episodic": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,ta_gap_u10,sh_relvol_o2,sh_price_o1,sh_avgvol_o1000&o=-change&c=1,47,61,62,63,64,65",
    # Parabolic Short: user-configured filters. c=1,47,61,62,63,64,65 = Ticker,ATR,AvgVol,RelVol,Price,Change,Volume
    "qulla_ps_large": "https://elite.finviz.com/export.ashx?v=141&f=cap_largeover,geo_usa,ta_perf_50to-4w&o=-change&c=1,47,61,62,63,64,65",
    "qulla_ps_small": "https://elite.finviz.com/export.ashx?v=141&f=cap_to9,geo_usa,ta_perf_300to-4w,ta_perf2_100to-1w&ft=4&o=-change&c=1,47,61,62,63,64,65",
    "qulla_breakouts": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_highlow52w_0to25-bhx,ta_perf_30to-4w,tad_0_close::close:d|abvpct::10:|sma:20:sma:d&o=-change&c=1,47,61,62,63,64,65",
    # Minervini Trend Template: c=1,47,61,62,63,64,65 = Ticker,ATR,AvgVol,RelVol,Price,Change,Volume (single request)
    # tad_6: close above 30% of 52w low (30% or above), not within 30% of low. abvpct:30 = above by 30% min.
    "minervini": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_avgvol_o1000,sh_price_o1,ta_sma200_pa,tad_0_sma:150:sma:d|abv:::1|close::close:d,tad_1_sma:200:sma:d|abv:::1|close::close:d,tad_2_sma:200:sma:d|abv:::1|sma:150:sma:d,tad_3_sma:50:sma:d|abv:::|sma:150:sma:d,tad_4_sma:50:sma:d|abv:::|sma:200:sma:d,tad_5_sma:50:sma:d|abv:::1|close::close:d,tad_6_close::close:d|abvpct:30::|hilo:52:low:d,tad_7_close::close:d|blwpct::25:|hilo:52:high:d,tad_8_rsi:14:rsi:d|abveq:::|value:::70&o=-change&c=1,47,61,62,63,64,65",
    # O'Neil/CANSLIM: c=1,32,40,47,61,62,63,64,65 = Ticker,ROE,ProfitMargin,ATR,AvgVol,RelVol,Price,Change,Volume. ft=2 for fundamental filters.
    "oneil": "https://elite.finviz.com/export.ashx?v=161&f=fa_epsyoy_o25,fa_epsyoy1_o25,fa_epsyoyttm_pos,fa_netmargin_pos,fa_roe_pos,geo_usa&o=-change&ft=2&c=1,32,40,47,61,62,63,64,65",
    # Group indicators: v=141 Performance view has Perf Week/Month (v=111 Overview ignores c=). c=1,3,4,6,41,42,43,45,47,50,51,52,55,56,61,62,63,64,65
    # ind_1b: $1B+ universe for Leading Industries (needs Industry/Sector, Perf Week/Month).
    "ind_1b": "https://elite.finviz.com/export.ashx?v=141&f=cap_1to,geo_usa,sh_avgvol_o1000,sh_price_o1&o=-change&c=1,3,4,6,41,42,43,45,47,50,51,52,55,56,61,62,63,64,65",
    # ind_1b_km: $1B+ for Key Metrics only (v=152 single-URL, no Industry/Sector).
    "ind_1b_km": "https://elite.finviz.com/export.ashx?v=152&f=cap_1to,geo_usa,sh_avgvol_o1000,sh_price_o1&ft=4&o=-change&c=1,42,43,44,45,47,52,53,54,60,65,66",
    "ind_9m": "https://elite.finviz.com/export.ashx?v=141&f=cap_1to,geo_usa,sh_curvol_9000tox,sh_price_o1,sh_relvol_1.25to&o=-change&c=1,3,4,6,41,42,43,45,47,50,51,52,55,56,61,62,63,64,65",
    # ind_usa: v=141 Performance has Perf Week/Month/Qtr/YTD (Industry/Sector for themes)
    "ind_usa": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_price_o1,sh_avgvol_o1000&o=-change&c=1,3,4,6,41,42,43,44,45,47,50,51,52,55,56,61,62,63,64,65",
    # Thematics RRG: v=141 for reliable Perf Year/Qtr columns (v=152 may have different layout)
    "ind_thematics_rrg": "https://elite.finviz.com/export.ashx?v=141&f=geo_usa,sh_price_o1,sh_avgvol_o1000&o=-change&c=1,3,4,6,41,42,43,45,47,50,51,52,55,56,61,62,63,64,65",
    # Key Metrics base data: v=152 single-URL per index. c=1,42,43,44,45,47,52,53,54,60,65,66 = Ticker,PerfWeek,PerfMonth,PerfQuart,PerfHalf,PerfYTD,SMA20,SMA50,SMA200,ChgFromOpen,Price,Change.
    # Price to SMA10, EMA10>SMA20, SMA20<SMA50, SMA50<SMA200, SMA20<SMA50<SMA200, New 20-Day High/Low: keep URL fetch (unchanged).
    "ind_ndx": "https://elite.finviz.com/export.ashx?v=152&f=geo_usa,idx_ndx&ft=4&o=-change&c=1,42,43,44,45,47,52,53,54,60,65,66",
    "ind_sp500": "https://elite.finviz.com/export.ashx?v=152&f=geo_usa,idx_sp500&ft=4&o=-change&c=1,42,43,44,45,47,52,53,54,60,65,66",
    "ind_dji": "https://elite.finviz.com/export.ashx?v=152&f=geo_usa,idx_dji&ft=4&o=-change&c=1,42,43,44,45,47,52,53,54,60,65,66",
    "ind_rut": "https://elite.finviz.com/export.ashx?v=152&f=geo_usa,idx_rut&ft=4&o=-change&c=1,42,43,44,45,47,52,53,54,60,65,66",
    # Stage analysis: export.ashx, USA universe. v=171 Technical has 20/50/200-Day SMA (Relative), EMA10.
    "ind_stage": "https://elite.finviz.com/export.ashx?v=171&f=geo_usa,sh_avgvol_o1000,sh_price_o1&o=-change&c=1,41,42,47,50,51,52,55,56,61,62,63,64,65",
    # S&P 500 Landscape: Overview (Market Cap, P/E) + Valuation (P/S) for Revenue/Net Income derivation
    "sp500_landscape_overview": "https://elite.finviz.com/export.ashx?v=111&f=geo_usa,idx_sp500&o=-marketcap",
    "sp500_landscape_valuation": "https://elite.finviz.com/export.ashx?v=121&f=geo_usa,idx_sp500&o=-marketcap",
}

# ---------- Sector SPDR tickers ----------
SECTOR_ETFS = [
    "XLK", "XLV", "XLC", "XLY", "XLU", "XLI",
    "XLE", "XLRE", "XLF", "XLB", "XLP",
    "RSP",
]

# RRG sector colors (distinct, dark-theme friendly)
RRG_COLORS = [
    "#06b6d4", "#22c55e", "#eab308", "#f97316", "#a855f7",
    "#ec4899", "#14b8a6", "#3b82f6", "#84cc16", "#f43f5e",
    "#8b5cf6",
]

# Sector SPDRs only (for RRG; excludes RSP)
SECTOR_SPDRS_RRG = [
    "XLK", "XLV", "XLC", "XLY", "XLU", "XLI",
    "XLE", "XLRE", "XLF", "XLB", "XLP",
]
RRG_BENCHMARK = "VTI"

SECTOR_NAMES = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLC": "Communication Svcs",
    "XLY": "Consumer Cyclical",
    "XLU": "Utilities",
    "XLI": "Industrials",
    "XLE": "Energy",
    "XLRE": "Real Estate",
    "XLF": "Financials",
    "XLB": "Basic Materials",
    "XLP": "Consumer Defensive",
    "RSP": "S&P Equal Weight",
}
