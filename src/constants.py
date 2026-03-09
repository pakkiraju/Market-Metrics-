"""Color tokens, stage definitions, and shared constants."""

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
STAGE_LABELS = ["1", "2A", "2B", "2C", "3", "4"]

STAGE_COLORS = {
    "1":  (COLORS["surface2"], COLORS["text_muted"]),
    "2A": (COLORS["green_cell"], COLORS["green_light"]),
    "2B": (COLORS["yellow_cell"], "#fde68a"),
    "2C": (COLORS["orange_cell"], "#fdba74"),
    "3":  (COLORS["red_cell"], COLORS["red_light"]),
    "4":  (COLORS["red_cell_strong"], COLORS["red_light"]),
}

STAGE_BAR_COLORS = {
    "1": "#4a5568",
    "2A": "#22c55e",
    "2B": "#eab308",
    "2C": "#f97316",
    "3": "#ef4444",
    "4": "#7f1d1d",
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
    "SMA20>SMA50",
    "SMA50>SMA200",
    "SMA20>SMA50>SMA200",
    "4% Up vs 4% Down",
    "New 20-Day Highs",
    "New 20-Day Lows",
    "Price-to 20 Day Range",
    "Stocks",
]

INDEX_GROUPS = ["QQQE", "RSP", "Composite", "$1B+"]

# ---------- Sector SPDR tickers ----------
SECTOR_ETFS = [
    "XLK", "XLV", "XLC", "XLY", "XLU", "XLI",
    "XLE", "XLRE", "XLF", "XLB", "XLP",
    "RSP", "QQQE",
]

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
    "QQQE": "Nasdaq100 EW",
}
