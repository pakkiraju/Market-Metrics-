"""Dash inline-style helpers for the dark Bloomberg-terminal theme."""

from src.constants import COLORS, HEADER_COLORS

# ---------- Dashboard wrapper (scrollable) ----------
DASHBOARD_STYLE = {
    "display": "flex",
    "flexDirection": "column",
    "minHeight": "100vh",
    "width": "100vw",
    "backgroundColor": COLORS["bg"],
    "color": COLORS["text"],
    "fontFamily": "'Inter', -apple-system, 'Segoe UI', sans-serif",
}

# ---------- Header ----------
HEADER_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "space-between",
    "padding": "0 12px",
    "backgroundColor": COLORS["surface"],
    "borderBottom": f"1px solid {COLORS['border']}",
    "height": "36px",
    "position": "sticky",
    "top": 0,
    "zIndex": 200,
    "flexShrink": 0,
}

HEADER_LOGO_STYLE = {
    "fontSize": "14px",
    "fontWeight": 700,
    "color": COLORS["accent"],
    "letterSpacing": "-0.5px",
}

HEADER_DATE_STYLE = {
    "color": COLORS["text"],
    "fontWeight": 500,
    "fontSize": "11px",
}

MARKET_STATUS_STYLE_CLOSED = {
    "padding": "1px 8px",
    "borderRadius": "3px",
    "fontSize": "10px",
    "fontWeight": 600,
    "textTransform": "uppercase",
    "letterSpacing": "0.5px",
    "backgroundColor": COLORS["red_cell"],
    "color": COLORS["red_light"],
}

MARKET_STATUS_STYLE_OPEN = {
    **MARKET_STATUS_STYLE_CLOSED,
    "backgroundColor": COLORS["green_cell"],
    "color": COLORS["green_light"],
}

REFRESH_BTN_STYLE = {
    "backgroundColor": COLORS["surface2"],
    "border": f"1px solid {COLORS['border']}",
    "color": COLORS["text_muted"],
    "padding": "2px 8px",
    "borderRadius": "3px",
    "cursor": "pointer",
    "fontSize": "10px",
}

SETTINGS_BTN_STYLE = {
    "backgroundColor": COLORS["surface2"],
    "border": f"1px solid {COLORS['border']}",
    "color": COLORS["accent"],
    "padding": "2px 8px",
    "borderRadius": "3px",
    "cursor": "pointer",
    "fontSize": "10px",
    "marginLeft": "4px",
}

# ---------- Scrollable content area ----------
CONTENT_AREA_STYLE = {
    "flex": 1,
    "overflowY": "auto",
    "overflowX": "hidden",
    "padding": "4px",
}

# ---------- Primary row: Key Metrics + 2 bar charts side by side ----------
PRIMARY_ROW_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "auto minmax(420px, 1fr) minmax(420px, 1fr)",
    "gap": "8px",
    "marginBottom": "4px",
    "alignItems": "stretch",
}

# ---------- Flexible grid for secondary widgets ----------
SECONDARY_GRID_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "repeat(auto-fill, minmax(320px, 1fr))",
    "gap": "4px",
    "marginBottom": "4px",
}

WIDE_ROW_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "1fr",
    "gap": "4px",
    "marginBottom": "4px",
}

HALF_ROW_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "1fr 1fr",
    "gap": "4px",
    "marginBottom": "4px",
}

QUARTER_ROW_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "1fr 1fr 1fr 1fr",
    "gap": "4px",
    "marginBottom": "4px",
}

# ---------- Widget card ----------
WIDGET_STYLE = {
    "backgroundColor": COLORS["surface"],
    "borderRadius": "3px",
    "border": f"1px solid {COLORS['border']}",
    "display": "flex",
    "flexDirection": "column",
    "overflow": "hidden",
}

WIDGET_PRIMARY_STYLE = {
    **WIDGET_STYLE,
    "minHeight": "420px",
}

# Key Metrics: width fits table content, no stretch to viewport
WIDGET_KEY_METRICS_STYLE = {
    **WIDGET_PRIMARY_STYLE,
    "width": "fit-content",
    "maxWidth": "100%",
}

WIDGET_SECONDARY_STYLE = {
    **WIDGET_STYLE,
    "maxHeight": "420px",
}

def section_header_style(variant="default"):
    bg = HEADER_COLORS.get(variant, HEADER_COLORS["default"])
    return {
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "space-between",
        "padding": "1px 6px",
        "backgroundColor": bg,
        "color": "#fff",
        "fontSize": "9px",
        "fontWeight": 600,
        "textTransform": "uppercase",
        "letterSpacing": "0.5px",
        "flexShrink": 0,
        "minHeight": "18px",
        "maxHeight": "20px",
        "borderRadius": "3px 3px 0 0",
    }

SECTION_BODY_STYLE = {
    "flex": 1,
    "overflow": "auto",
    "minHeight": 0,
}

# Key Metrics: sized to fit data, no scrollbar
KEY_METRICS_BODY_STYLE = {
    **SECTION_BODY_STYLE,
    "overflow": "hidden",
}

# ---------- Settings drawer (overlay) ----------
SETTINGS_OVERLAY_STYLE_HIDDEN = {
    "display": "none",
}

SETTINGS_OVERLAY_STYLE_VISIBLE = {
    "position": "fixed",
    "top": "36px",
    "right": 0,
    "width": "280px",
    "bottom": 0,
    "backgroundColor": COLORS["surface"],
    "borderLeft": f"1px solid {COLORS['border']}",
    "zIndex": 300,
    "padding": "12px",
    "overflowY": "auto",
    "boxShadow": "-4px 0 16px rgba(0,0,0,0.4)",
}

SETTINGS_TITLE_STYLE = {
    "fontSize": "12px",
    "fontWeight": 700,
    "color": COLORS["accent"],
    "marginBottom": "12px",
    "textTransform": "uppercase",
    "letterSpacing": "0.5px",
}

SETTINGS_ITEM_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "space-between",
    "padding": "6px 0",
    "borderBottom": f"1px solid {COLORS['border']}",
    "fontSize": "10px",
    "color": COLORS["text"],
}

TOGGLE_LABEL_STYLE = {
    "cursor": "pointer",
    "fontSize": "10px",
    "color": COLORS["text"],
}

# ---------- Ticker pill ----------
TICKER_GRID_STYLE = {
    "display": "flex",
    "flexWrap": "wrap",
    "gap": "2px",
    "padding": "3px",
}

def ticker_pill_style(variant="green"):
    bg_map = {
        "green": (COLORS["green_cell"], COLORS["green_light"]),
        "yellow": (COLORS["yellow_cell"], "#fde68a"),
        "red": (COLORS["red_cell"], COLORS["red_light"]),
        "blue": (COLORS["blue_tml_bg"], "#93c5fd"),
        "orange": (COLORS["orange_cell"], "#fdba74"),
        "neutral": (COLORS["surface2"], COLORS["text_muted"]),
    }
    bg, fg = bg_map.get(variant, bg_map["green"])
    return {
        "padding": "1px 4px",
        "borderRadius": "2px",
        "fontSize": "9px",
        "fontWeight": 600,
        "cursor": "default",
        "lineHeight": "1.4",
        "backgroundColor": bg,
        "color": fg,
        "display": "inline-block",
    }

# ---------- Dense table ----------
TABLE_STYLE = {
    "width": "100%",
    "borderCollapse": "collapse",
    "fontSize": "10px",
    "tableLayout": "fixed",
}

TABLE_HEADER_STYLE = {
    "position": "sticky",
    "top": 0,
    "zIndex": 2,
    "backgroundColor": COLORS["surface2"],
    "color": COLORS["text_muted"],
    "fontWeight": 600,
    "fontSize": "8px",
    "textTransform": "uppercase",
    "letterSpacing": "0.3px",
    "padding": "1px 3px",
    "border": f"1px solid {COLORS['border']}",
    "whiteSpace": "nowrap",
    "textAlign": "center",
}

TABLE_CELL_STYLE = {
    "padding": "1px 3px",
    "border": f"1px solid {COLORS['border']}",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "textAlign": "center",
    "fontSize": "9px",
    "lineHeight": "1.4",
    "color": COLORS["text"],
}

# ---------- Stage badge ----------
def stage_badge_style(stage):
    from src.constants import STAGE_COLORS
    bg, fg = STAGE_COLORS.get(stage, STAGE_COLORS["1"])
    return {
        "display": "inline-block",
        "padding": "0 3px",
        "borderRadius": "2px",
        "fontSize": "9px",
        "fontWeight": 600,
        "lineHeight": "1.4",
        "backgroundColor": bg,
        "color": fg,
    }

# ---------- Chart wrapper ----------
CHART_WRAP_STYLE = {
    "flex": 1,
    "padding": "2px",
    "minHeight": 0,
    "position": "relative",
}

# ---------- Loading spinner ----------
LOADING_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "height": "100%",
    "color": COLORS["text_muted"],
    "fontSize": "12px",
    "minHeight": "80px",
}
