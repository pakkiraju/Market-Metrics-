"""Dash callbacks: progressive per-widget-group refresh, widget toggles,
TradingView modal, watchlist management.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dash import html, dcc, Input, Output, State, callback, no_update, ctx, ALL
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from src import cache
from src.constants import COLORS, GRAPH_CONFIG, GRAPH_CONFIG_ZOOM
from src.calculations import (
    compute_all_key_metrics,
    compute_sector_data,
    compute_rrg_data,
    compute_97_club,
    compute_9m_movers,
    compute_20pct_weekly,
    compute_4pct_daily,
    compute_earnings_yesterday_today,
    compute_stocks_in_play,
    compute_pre_market_scanner,
    compute_leading_industries,
    compute_thematics,
    compute_thematics_sector_data,
    compute_thematics_rrg_data,
    compute_top_gainers_losers,
    compute_stage_analysis,
)
from src.screeners import (
    qullamaggie_screener,
    minervini_screener,
    oneil_screener,
    jeff_sun_canslim_screener,
    jeff_sun_high_adr_screener,
    jeff_sun_extended_bases_screener,
    jeff_sun_1w20_screener,
    jeff_sun_4w30_screener,
    jeff_sun_4w50_screener,
    jeff_sun_13w50_screener,
    jeff_sun_26w100_screener,
    jeff_sun_ipo_thisweek_screener,
    jeff_sun_high_short_float_screener,
    jeff_sun_liquid_etfs_screener,
    julian_komar_strongest_screener,
)
from src.layout import (
    build_cnbc_premarket_watchlist_table,
    build_should_i_trade_content,
    build_key_metrics_table,
    build_live_index_snapshot,
    build_metrics_bar_chart,
    build_sector_table,
    build_rrg_chart,
    build_sp500_landscape_chart,
    build_stockbee_momentum50_table,
    build_stockbee_breadth,
    build_primary_breadth_chart,
    build_breadth_ratios_chart,
    build_secondary_breadth_chart,
    build_sp500_chart,
    build_97_club_table,
    build_9m_movers_table,
    build_20pct_weekly_table,
    build_4pct_daily_table,
    build_earnings_table,
    build_earnings_calendar_table,
    build_stocks_in_play_table,
    build_pre_market_scanner_table,
    build_leading_industries_table,
    build_thematics_table,
    build_thematics_sector_table,
    build_top_gainers_table,
    build_top_losers_table,
    build_stage_chart,
    build_stage_summary,
    build_ticker_grid,
    build_minervini_table,
    build_oneil_table,
    build_jeff_sun_canslim_table,
    build_jeff_sun_high_adr_table,
    build_jeff_sun_extended_bases_table,
    build_jeff_sun_1w20_table,
    build_jeff_sun_4w30_table,
    build_jeff_sun_4w50_table,
    build_jeff_sun_13w50_table,
    build_jeff_sun_26w100_table,
    build_jeff_sun_ipo_thisweek_table,
    build_jeff_sun_high_short_float_table,
    build_jeff_sun_liquid_etfs_table,
    build_julian_komar_strongest_table,
    build_qullamaggie_table,
    build_watchlist_table,
    WIDGETS, ALL_WIDGET_IDS,
    CHART_WRAP_STYLE,
)
from src.styles import (
    LOADING_STYLE,
    SETTINGS_OVERLAY_STYLE_HIDDEN,
    SETTINGS_OVERLAY_STYLE_VISIBLE,
    WIDGET_PRIMARY_STYLE,
    WIDGET_SECONDARY_STYLE,
)

logger = logging.getLogger(__name__)

ET = timezone(timedelta(hours=-5))

# Per-widget refresh: cache keys to invalidate when btn-refresh-{widget_id} is clicked
WIDGET_CACHE_KEYS = {
    "should-i-trade": ["should_i_trade_aggregate"],
    "key-metrics": ["all_key_metrics"],
    "chart2": ["all_key_metrics"],
    "chart3": ["all_key_metrics"],
    "club97": ["97_club"],
    "movers": ["9m_movers"],
    "weekly": ["20pct_weekly"],
    "daily": ["4pct_daily"],
    "in_play": ["stocks_in_play"],
    "intraday-earnings": ["earnings_yesterday_today"],
    "pre_market": ["pre_market_scanner"],
    "cnbc_premarket": ["cnbc_premarket_watchlist"],
    "live_index": ["live_index_quotes"],
    "leading": ["leading_industries"],
    "thematics": ["thematics", "thematics_data"],
    "thematics-sector": ["thematics_sector_data"],
    "top_gainers": ["thematics_data"],
    "top_losers": ["thematics_data"],
    "stage": ["stage_analysis"],
    "thematics-rrg": ["thematics_rrg_data"],
    "macro-monitor": ["macro_fred_bundle"],
    "qulla": ["qulla_episodic_v2", "qulla_parabolic_v2", "qulla_breakouts_v2"],
    "minervini": ["minervini_table"],
    "oneil": ["oneil_table"],
    "jeff_sun_canslim": ["jeff_sun_canslim"],
    "jeff_sun_high_adr": ["jeff_sun_high_adr"],
    "jeff_sun_extended_bases": ["jeff_sun_extended_bases"],
    "jeff_sun_1w20": ["jeff_sun_1w20"],
    "jeff_sun_4w30": ["jeff_sun_4w30"],
    "jeff_sun_4w50": ["jeff_sun_4w50"],
    "jeff_sun_13w50": ["jeff_sun_13w50"],
    "jeff_sun_26w100": ["jeff_sun_26w100"],
    "jeff_sun_ipo_thisweek": ["jeff_sun_ipo_thisweek"],
    "jeff_sun_high_short_float": ["jeff_sun_high_short_float"],
    "jeff_sun_liquid_etfs": ["jeff_sun_liquid_etfs"],
    "julian_komar_strongest": ["julian_komar_strongest"],
    "sector": ["sector_data"],
    "stockbee": ["stockbee_momentum50"],
    "breadth": ["stockbee_breadth"],
    "breadth-primary": ["stockbee_breadth_history"],
    "breadth-ratios": ["stockbee_breadth_history"],
    "breadth-secondary": ["stockbee_breadth_history"],
    "breadth-sp500": ["stockbee_breadth_history"],
    "rrg": ["rrg_data"],
    "sp500-landscape": ["sp500_landscape"],
    "earnings-calendar-week": ["earnings_this_week"],
}


def _invalidate_widget_cache(widget_id: str):
    """Invalidate cache keys for a widget so next fetch gets fresh data."""
    for key in WIDGET_CACHE_KEYS.get(widget_id, []):
        cache.invalidate(key)

# Refresh: 1 hr when market open; 24 hr when closed (after 4:30 PM EST or weekend)
REFRESH_INTERVAL_OPEN = 3600_000   # 1 hr
REFRESH_INTERVAL_CLOSED = 86400_000  # 24 hr


def _is_market_closed() -> bool:
    """True if market closed: after 4:30 PM EST or weekend."""
    now = datetime.now(ET)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    return now.hour > 16 or (now.hour == 16 and now.minute >= 30)


WATCHLIST_FILE = Path(__file__).resolve().parent.parent / "watchlist.csv"


def _load_watchlist_from_file() -> list[str]:
    if not WATCHLIST_FILE.exists():
        return []
    lines = WATCHLIST_FILE.read_text().strip().splitlines()
    tickers = []
    for line in lines[1:]:
        t = line.strip()
        if t:
            tickers.append(t.upper())
    return tickers


def _save_watchlist_to_file(tickers: list[str]):
    WATCHLIST_FILE.write_text("ticker\n" + "\n".join(tickers) + "\n")


def _now_str():
    return datetime.now(ET).strftime("Updated %I:%M %p")


def _err_div(e):
    import traceback
    msg = str(e) if e else "Unknown error"
    children = [html.Div(f"Error: {msg}", style={"fontWeight": 600})]
    if logger.isEnabledFor(logging.DEBUG):
        tb = traceback.format_exc()
        if tb:
            children.append(html.Pre(
                tb[:1500] + ("..." if len(tb) > 1500 else ""),
                style={"fontSize": "9px", "overflow": "auto", "maxHeight": "120px", "marginTop": "4px", "whiteSpace": "pre-wrap"},
            ))
    return html.Div(children, style={"color": COLORS["red"], "padding": "8px", "fontSize": "10px"})


def register_callbacks(app):
    """Register all Dash callbacks on the app."""

    # ------------------------------------------------------------------
    # 0. Market hours: slow refresh when closed (after 4:30 PM EST or weekend)
    # ------------------------------------------------------------------
    @app.callback(
        Output("interval-refresh", "interval"),
        Input("market-hours-check", "n_intervals"),
        prevent_initial_call=False,
    )
    def set_refresh_interval(n):
        return REFRESH_INTERVAL_CLOSED if _is_market_closed() else REFRESH_INTERVAL_OPEN

    # ------------------------------------------------------------------
    # 0b. Header date/time: update NY time every minute
    # ------------------------------------------------------------------
    @app.callback(
        Output("header-date", "children"),
        Input("interval-header-clock", "n_intervals"),
        prevent_initial_call=False,
    )
    def update_header_datetime(n):
        now = datetime.now(ZoneInfo("America/New_York"))
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M:%S %p")
        return f"{date_str} · {time_str}"

    # ------------------------------------------------------------------
    # 0b2. Should I Trade? — aggregate data, score, build content (45s refresh)
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("should-i-trade-content", "children"),
            Output("sit-status", "children"),
            Output("sit-last-updated", "children"),
        ],
        [
            Input("sit-interval", "n_intervals"),
            Input("btn-refresh-should-i-trade", "n_clicks"),
            Input("sit-mode-toggle", "value"),
        ],
        prevent_initial_call=False,
    )
    def refresh_should_i_trade(n_interval, n_refresh, mode):
        if ctx.triggered_id == "btn-refresh-should-i-trade":
            _invalidate_widget_cache("should-i-trade")
        try:
            from src.should_i_trade_data import fetch_should_i_trade_data
            from src.should_i_trade_scoring import compute_scores, generate_terminal_analysis

            data = fetch_should_i_trade_data()
            mode = mode or "swing"
            scores = compute_scores(data, mode=mode)
            summary = generate_terminal_analysis(data, scores)
            content = build_should_i_trade_content(data, scores, summary)

            ts = data.get("timestamp", "")
            if ts:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    updated = dt.strftime("Updated %I:%M:%S %p")
                except Exception:
                    updated = "Updated —"
            else:
                updated = "Updated —"

            return content, "LIVE", updated
        except Exception as e:
            logger.exception("Should I Trade refresh failed: %s", e)
            err = html.Div([
                html.Div("Error loading data", style={"fontSize": "14px", "color": COLORS["red"], "marginBottom": "8px"}),
                html.Div(str(e), style={"fontSize": "11px", "color": COLORS["text_muted"]}),
            ], style={"padding": "24px"})
            return err, "ERROR", "—"

    # ------------------------------------------------------------------
    # 0c. Chart resize on tab switch / initial load (fixes zoomed-in charts)
    # ------------------------------------------------------------------
    app.clientside_callback(
        """
        function(tabValue, nResize, settingsDisplay) {
            function doResize() {
                var graphs = document.querySelectorAll('.js-plotly-plot');
                if (window.Plotly && window.Plotly.Plots) {
                    for (var i = 0; i < graphs.length; i++) {
                        try {
                            window.Plotly.Plots.resize(graphs[i]);
                        } catch (e) {}
                    }
                }
                window.dispatchEvent(new Event('resize'));
            }
            setTimeout(doResize, 400);
            setTimeout(doResize, 900);
            setTimeout(doResize, 1500);
            return Date.now();
        }
        """,
        Output("chart-resize-trigger", "data"),
        [
            Input("main-tabs", "data"),
            Input("interval-chart-resize", "n_intervals"),
            Input("settings-drawer", "style"),
        ],
    )

    # ------------------------------------------------------------------
    # 0d. Tab switch — server callback (Dash 4 clientside inline hash can fail to register →
    #     undefined.apply in dash_renderer). Keeps main-tabs in sync for other callbacks.
    # ------------------------------------------------------------------
    _TAB_PANE_HIDE = {"display": "none"}
    _TAB_PANE_SHOW = {
        "display": "flex",
        "flexDirection": "column",
        "flex": "1",
        "minHeight": "0",
        "minWidth": "0",
        "overflow": "auto",
        "backgroundColor": COLORS["bg"],
    }
    _TAB_ORDER = (
        "should-i-trade",
        "macro-monitor",
        "market-metrics",
        "super-scanners",
        "intraday",
    )
    _NAV_TO_TAB = {
        "nav-tab-should-i-trade": "should-i-trade",
        "nav-tab-macro-monitor": "macro-monitor",
        "nav-tab-market-metrics": "market-metrics",
        "nav-tab-super-scanners": "super-scanners",
        "nav-tab-intraday": "intraday",
    }

    @app.callback(
        [
            Output("main-tabs", "data"),
            Output("tab-pane-should-i-trade", "style"),
            Output("tab-pane-macro-monitor", "style"),
            Output("tab-pane-market-metrics", "style"),
            Output("tab-pane-super-scanners", "style"),
            Output("tab-pane-intraday", "style"),
            Output("nav-tab-should-i-trade", "className"),
            Output("nav-tab-macro-monitor", "className"),
            Output("nav-tab-market-metrics", "className"),
            Output("nav-tab-super-scanners", "className"),
            Output("nav-tab-intraday", "className"),
        ],
        [
            Input("nav-tab-should-i-trade", "n_clicks"),
            Input("nav-tab-macro-monitor", "n_clicks"),
            Input("nav-tab-market-metrics", "n_clicks"),
            Input("nav-tab-super-scanners", "n_clicks"),
            Input("nav-tab-intraday", "n_clicks"),
        ],
        prevent_initial_call=True,
    )
    def switch_main_tab(_n1, _n2, _n3, _n4, _n5):
        tid = ctx.triggered_id
        if tid not in _NAV_TO_TAB:
            return [no_update] * 11
        tab = _NAV_TO_TAB[tid]
        pane_styles = [{**_TAB_PANE_SHOW} if tab == t else {**_TAB_PANE_HIDE} for t in _TAB_ORDER]
        nav_classes = [
            "nav-tab-btn nav-tab-active" if tab == t else "nav-tab-btn" for t in _TAB_ORDER
        ]
        return [tab, *pane_styles, *nav_classes]

    @app.callback(
        Output("nav-sidebar", "className"),
        Input("nav-sidebar-toggle", "n_clicks"),
        State("nav-sidebar", "className"),
        prevent_initial_call=True,
    )
    def nav_sidebar_toggle(_n, cls):
        base = "nav-sidebar"
        cur = cls or base
        if "nav-sidebar-collapsed" in cur:
            return base
        return f"{base} nav-sidebar-collapsed"

    # ------------------------------------------------------------------
    # 1. Settings drawer toggle
    # ------------------------------------------------------------------
    @app.callback(
        Output("settings-drawer", "style"),
        Input("btn-settings", "n_clicks"),
        State("settings-drawer", "style"),
        prevent_initial_call=True,
    )
    def toggle_settings(n_clicks, current_style):
        if current_style and current_style.get("display") != "none":
            return SETTINGS_OVERLAY_STYLE_HIDDEN
        return SETTINGS_OVERLAY_STYLE_VISIBLE

    # ------------------------------------------------------------------
    # 1b. Settings drawer: show tab-specific widget toggles
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("settings-macro-monitor", "style"),
            Output("settings-market-metrics", "style"),
            Output("settings-super-scanners", "style"),
            Output("settings-intraday", "style"),
        ],
        Input("main-tabs", "data"),
        prevent_initial_call=False,
    )
    def settings_tab_content(active_tab):
        hide = {"display": "none"}
        show = {"display": "block"}
        if active_tab == "should-i-trade":
            return hide, hide, hide, hide
        if active_tab == "macro-monitor":
            return show, hide, hide, hide
        if active_tab == "market-metrics":
            return hide, show, hide, hide
        if active_tab == "super-scanners":
            return hide, hide, show, hide
        if active_tab == "intraday":
            return hide, hide, hide, show
        return hide, show, hide, hide

    # ------------------------------------------------------------------
    # 2. Widget visibility: ALL widgets toggleable
    # ------------------------------------------------------------------
    toggle_inputs = [Input(f"toggle-{wid}", "value") for wid in ALL_WIDGET_IDS]
    widget_outputs = [Output(f"widget-{wid}", "style") for wid in ALL_WIDGET_IDS]

    is_primary_map = {w[0]: w[2] for w in WIDGETS}

    @app.callback(
        widget_outputs,
        toggle_inputs,
        prevent_initial_call=True,
    )
    def update_widget_visibility(*toggle_values):
        results = []
        for wid, val in zip(ALL_WIDGET_IDS, toggle_values):
            if val and "on" in val:
                results.append(
                    WIDGET_PRIMARY_STYLE if is_primary_map[wid]
                    else WIDGET_SECONDARY_STYLE
                )
            else:
                results.append({"display": "none"})
        return results

    # ------------------------------------------------------------------
    # 3. TradingView modal: close via clientside callback
    # ------------------------------------------------------------------
    app.clientside_callback(
        """
        function(n_clicks) {
            return {display: 'none'};
        }
        """,
        Output("tv-modal", "style", allow_duplicate=True),
        Input("btn-tv-close", "n_clicks"),
        prevent_initial_call=True,
    )

    # ------------------------------------------------------------------
    # 4. Watchlist: add ticker
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("watchlist-store", "data"),
            Output("watchlist-input", "value"),
        ],
        [
            Input("btn-watchlist-add", "n_clicks"),
            Input("watchlist-input", "n_submit"),
        ],
        [
            State("watchlist-input", "value"),
            State("watchlist-store", "data"),
        ],
        prevent_initial_call=True,
    )
    def add_to_watchlist(n_clicks, n_submit, ticker_input, store_data):
        if not ticker_input or not ticker_input.strip():
            return no_update, no_update
        # Parse comma-separated tickers (e.g. "AMD, aapl, GOOGL")
        raw_tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
        if not raw_tickers:
            return no_update, ""
        # Use file as source of truth; fallback to store if file empty (e.g. first add)
        current = _load_watchlist_from_file()
        if not current and store_data:
            current = list(store_data)
        added = False
        for ticker in raw_tickers:
            if ticker and ticker not in current:
                current.append(ticker)
                added = True
        if added:
            _save_watchlist_to_file(current)
        return (current if added else no_update), ""

    # ------------------------------------------------------------------
    # 5. Watchlist: remove ticker (pattern-matching callback)
    # ------------------------------------------------------------------
    @app.callback(
        Output("watchlist-store", "data", allow_duplicate=True),
        Input({"type": "wl-remove", "ticker": ALL}, "n_clicks"),
        State("watchlist-store", "data"),
        prevent_initial_call=True,
    )
    def remove_from_watchlist(n_clicks_list, current_list):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            return no_update
        ticker = ctx.triggered_id.get("ticker")
        if not ticker or not current_list or ticker not in current_list:
            return no_update
        # Only remove on actual click (n_clicks > 0). Prevents false triggers when
        # table re-renders and component count changes (add/remove rows).
        triggered = ctx.triggered[0] if ctx.triggered else {}
        if not triggered.get("value") or (isinstance(triggered.get("value"), (int, float)) and triggered["value"] < 1):
            return no_update
        # Use file as source, return new list (never mutate)
        current = _load_watchlist_from_file()
        if ticker not in current:
            return no_update
        new_list = [t for t in current if t != ticker]
        _save_watchlist_to_file(new_list)
        # Invalidate old cache so deleted ticker is not shown from stale cache
        old_key = f"watchlist_quotes_{','.join(sorted(current))}"
        cache.invalidate(old_key)
        return new_list

    # ------------------------------------------------------------------
    # 5b. Watchlist: populate sector dropdown options
    # ------------------------------------------------------------------
    @app.callback(
        Output("watchlist-sector-dropdown", "options"),
        [
            Input("interval-refresh", "n_intervals"),
            Input("main-tabs", "data"),
        ],
        prevent_initial_call=False,
    )
    def update_watchlist_sector_options(n_intervals, tab_value):
        if tab_value != "market-metrics":
            return no_update
        try:
            from src.data_fetcher import fetch_watchlist_sector_options
            return fetch_watchlist_sector_options()
        except Exception:
            return no_update

    # ------------------------------------------------------------------
    # 5c. Watchlist: hide add-ticker row when viewing a sector
    # ------------------------------------------------------------------
    @app.callback(
        Output("watchlist-add-row", "style"),
        Input("watchlist-sector-dropdown", "value"),
        prevent_initial_call=False,
    )
    def toggle_watchlist_add_row(sector_value):
        is_sector = sector_value and str(sector_value).strip() != "watchlist"
        base = {"gap": "4px", "padding": "4px 4px 2px 4px", "alignItems": "center"}
        if is_sector:
            return {**base, "display": "none"}
        return {**base, "display": "flex"}

    # ------------------------------------------------------------------
    # 6. Watchlist: fetch Finviz data and render table (custom watchlist or sector)
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("watchlist-content", "children"),
            Output("watchlist-data-store", "data"),
            Output("watchlist-view-store", "data"),
        ],
        [
            Input("watchlist-store", "data"),
            Input("watchlist-sector-dropdown", "value"),
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-watchlist", "n_clicks"),
        ],
    )
    def render_watchlist(wl_data, sector_value, n_intervals, n_clicks, btn_w):
        is_sector_view = sector_value and str(sector_value).strip() != "watchlist"
        view_store = sector_value if sector_value else "watchlist"
        if is_sector_view:
            if btn_w:
                cache.invalidate(f"watchlist_sector_{sector_value.replace(' ', '_').replace('/', '_')}")
            try:
                from src.data_fetcher import fetch_stocks_by_sector
                data = fetch_stocks_by_sector(sector_value)
                if not data:
                    return html.Div(f"No stocks found for {sector_value}.", style={
                        "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                    }), [], view_store
                return build_watchlist_table(data, "watchlist", "change", False, show_remove=False), data, view_store
            except Exception as e:
                logger.exception("Watchlist sector fetch failed: %s", e)
                return _err_div(e), [], view_store
        # Custom watchlist view
        if btn_w and wl_data:
            cache.invalidate(f"watchlist_quotes_{','.join(sorted(wl_data))}")
        if not wl_data:
            return html.Div("No tickers in watchlist. Add some above.", style={
                "color": COLORS["text_muted"], "fontSize": "9px",
                "padding": "8px",
            }), [], view_store
        try:
            from src.data_fetcher import fetch_tickers_bulk_csv
            cache_key = f"watchlist_quotes_{','.join(sorted(wl_data))}"
            data = fetch_tickers_bulk_csv(wl_data, cache_key=cache_key)
            if not data:
                # Fallback: show tickers with placeholder when Finviz returns no data
                data = [{"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"} for t in wl_data]
            else:
                # Preserve watchlist order; bulk may return different order
                by_ticker = {r["ticker"]: r for r in data}
                data = [by_ticker.get(t.upper(), {"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"}) for t in wl_data]
            return build_watchlist_table(data, "watchlist", "change", False, show_remove=True), data, view_store
        except Exception as e:
            logger.exception("Watchlist fetch failed: %s", e)
            return _err_div(e), [], view_store

    # ==================================================================
    #  PARALLEL WIDGET LOADING
    #  Each group loads independently; widgets appear as soon as ready.
    # ==================================================================

    # Key Metrics: fetch all URLs, cache full result, display when done. Loading spinner until complete.
    @app.callback(
        [
            Output("key-metrics-content", "children"),
            Output("chart2-content", "children"),
            Output("chart3-content", "children"),
            Output("last-update", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-key-metrics", "n_clicks"),
            Input("btn-refresh-chart2", "n_clicks"),
            Input("btn-refresh-chart3", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_a(n_intervals, n_clicks, btn_km, btn_c2, btn_c3):
        if btn_km or btn_c2 or btn_c3:
            _invalidate_widget_cache("key-metrics")
        try:
            metrics = compute_all_key_metrics()
            key_metrics_table = build_key_metrics_table(metrics)
            nq100_data = metrics.get("NQ100", [])
            spy500_data = metrics.get("SPY500", [])
            djia_data = metrics.get("DJIA", [])
            rus_data = metrics.get("RUS2000", [])
            b1_data = metrics.get("$1B+", [])

            chart2_fig = build_metrics_bar_chart([
                (nq100_data, "NQ100", "#991b1b", "#dc2626"),
                (spy500_data, "SPY500", "#166534", "#22c55e"),
                (djia_data, "DJIA", "#1e3a5f", "#3b82f6"),
            ])
            chart2 = dcc.Graph(
                figure=chart2_fig,
                config=GRAPH_CONFIG,
                style={"height": "100%", "width": "100%"},
            )
            chart3_fig = build_metrics_bar_chart([
                (rus_data, "RUS2000", "#7f1d1d", "#ef4444"),
                (b1_data, "$1B+", "#14532d", "#4ade80"),
            ])
            chart3 = dcc.Graph(
                figure=chart3_fig,
                config=GRAPH_CONFIG,
                style={"height": "100%", "width": "100%"},
            )
            return [key_metrics_table, chart2, chart3, _now_str()]
        except Exception as e:
            logger.exception("Group A failed: %s", e)
            err = _err_div(e)
            return [err, err, err, f"Error at {_now_str()}"]

    # Qullamaggie: enabled
    _disabled_msg = html.Div("Widget disabled", style={
        "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
    })

    _GROUP_B_WIDGETS = ["qulla", "minervini", "oneil", "jeff_sun_canslim", "jeff_sun_high_adr", "jeff_sun_extended_bases", "jeff_sun_1w20", "jeff_sun_4w30", "jeff_sun_4w50", "jeff_sun_13w50", "jeff_sun_26w100", "jeff_sun_ipo_thisweek", "jeff_sun_high_short_float"]

    @app.callback(
        [
            Output("qulla-content", "children"),
            Output("qulla-data-store", "data"),
            Output("minervini-content", "children"),
            Output("minervini-data-store", "data"),
            Output("oneil-content", "children"),
            Output("oneil-data-store", "data"),
            Output("jeff_sun_canslim-content", "children"),
            Output("jeff_sun_canslim-data-store", "data"),
            Output("jeff_sun_high_adr-content", "children"),
            Output("jeff_sun_high_adr-data-store", "data"),
            Output("jeff_sun_extended_bases-content", "children"),
            Output("jeff_sun_extended_bases-data-store", "data"),
            Output("jeff_sun_1w20-content", "children"),
            Output("jeff_sun_1w20-data-store", "data"),
            Output("jeff_sun_4w30-content", "children"),
            Output("jeff_sun_4w30-data-store", "data"),
            Output("jeff_sun_4w50-content", "children"),
            Output("jeff_sun_4w50-data-store", "data"),
            Output("jeff_sun_13w50-content", "children"),
            Output("jeff_sun_13w50-data-store", "data"),
            Output("jeff_sun_26w100-content", "children"),
            Output("jeff_sun_26w100-data-store", "data"),
            Output("jeff_sun_ipo_thisweek-content", "children"),
            Output("jeff_sun_ipo_thisweek-data-store", "data"),
            Output("jeff_sun_high_short_float-content", "children"),
            Output("jeff_sun_high_short_float-data-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ]
        + [Input(f"btn-refresh-{w}", "n_clicks") for w in _GROUP_B_WIDGETS],
        prevent_initial_call=False,
    )
    def refresh_group_b(n_intervals, n_clicks, *btn_clicks):
        tid = ctx.triggered_id if ctx.triggered else None
        single = None
        if tid and isinstance(tid, str) and tid.startswith("btn-refresh-"):
            single = tid.replace("btn-refresh-", "")
            if single in _GROUP_B_WIDGETS:
                _invalidate_widget_cache(single)

        try:
            if single == "qulla":
                d = qullamaggie_screener()
                return build_qullamaggie_table(d, "qulla", "change", False), d, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
            if single == "minervini":
                d = minervini_screener()
                return no_update, no_update, build_minervini_table(d, "minervini", "change", False), d, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
            if single == "oneil":
                d = oneil_screener()
                return no_update, no_update, no_update, no_update, build_oneil_table(d, "oneil", "change", False), d, no_update, no_update, no_update, no_update, no_update, no_update
            if single == "jeff_sun_canslim":
                d = jeff_sun_canslim_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_canslim_table(d, "jeff_sun_canslim", "change", False), d, no_update, no_update, no_update, no_update
            if single == "jeff_sun_high_adr":
                d = jeff_sun_high_adr_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_high_adr_table(d, "jeff_sun_high_adr", "change", False), d, no_update, no_update
            if single == "jeff_sun_extended_bases":
                d = jeff_sun_extended_bases_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_extended_bases_table(d, "jeff_sun_extended_bases", "change", False), d, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
            if single == "jeff_sun_1w20":
                d = jeff_sun_1w20_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_1w20_table(d, "jeff_sun_1w20", "change", False), d, no_update, no_update, no_update, no_update, no_update, no_update
            if single == "jeff_sun_4w30":
                d = jeff_sun_4w30_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_4w30_table(d, "jeff_sun_4w30", "change", False), d, no_update, no_update, no_update, no_update
            if single == "jeff_sun_4w50":
                d = jeff_sun_4w50_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_4w50_table(d, "jeff_sun_4w50", "change", False), d, no_update, no_update
            if single == "jeff_sun_13w50":
                d = jeff_sun_13w50_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_13w50_table(d, "jeff_sun_13w50", "change", False), d, no_update
            if single == "jeff_sun_26w100":
                d = jeff_sun_26w100_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_26w100_table(d, "jeff_sun_26w100", "change", False), d, no_update, no_update, no_update, no_update
            if single == "jeff_sun_ipo_thisweek":
                d = jeff_sun_ipo_thisweek_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_ipo_thisweek_table(d, "jeff_sun_ipo_thisweek", "change", False), d, no_update, no_update
            if single == "jeff_sun_high_short_float":
                d = jeff_sun_high_short_float_screener()
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, build_jeff_sun_high_short_float_table(d, "jeff_sun_high_short_float", "change", False), d

            qulla_data = qullamaggie_screener()
            qulla_table = build_qullamaggie_table(qulla_data, "qulla", "change", False)
            minervini_data = minervini_screener()
            minervini_table = build_minervini_table(minervini_data, "minervini", "change", False)
            oneil_data = oneil_screener()
            oneil_table = build_oneil_table(oneil_data, "oneil", "change", False)
            jeff_sun_data = jeff_sun_canslim_screener()
            jeff_sun_table = build_jeff_sun_canslim_table(jeff_sun_data, "jeff_sun_canslim", "change", False)
            jeff_sun_adr_data = jeff_sun_high_adr_screener()
            jeff_sun_adr_table = build_jeff_sun_high_adr_table(jeff_sun_adr_data, "jeff_sun_high_adr", "change", False)
            jeff_sun_bases_data = jeff_sun_extended_bases_screener()
            jeff_sun_bases_table = build_jeff_sun_extended_bases_table(jeff_sun_bases_data, "jeff_sun_extended_bases", "change", False)
            jeff_sun_1w20_data = jeff_sun_1w20_screener()
            jeff_sun_1w20_table = build_jeff_sun_1w20_table(jeff_sun_1w20_data, "jeff_sun_1w20", "change", False)
            jeff_sun_4w30_data = jeff_sun_4w30_screener()
            jeff_sun_4w30_table = build_jeff_sun_4w30_table(jeff_sun_4w30_data, "jeff_sun_4w30", "change", False)
            jeff_sun_4w50_data = jeff_sun_4w50_screener()
            jeff_sun_4w50_table = build_jeff_sun_4w50_table(jeff_sun_4w50_data, "jeff_sun_4w50", "change", False)
            jeff_sun_13w50_data = jeff_sun_13w50_screener()
            jeff_sun_13w50_table = build_jeff_sun_13w50_table(jeff_sun_13w50_data, "jeff_sun_13w50", "change", False)
            jeff_sun_26w100_data = jeff_sun_26w100_screener()
            jeff_sun_26w100_table = build_jeff_sun_26w100_table(jeff_sun_26w100_data, "jeff_sun_26w100", "change", False)
            jeff_sun_ipo_data = jeff_sun_ipo_thisweek_screener()
            jeff_sun_ipo_table = build_jeff_sun_ipo_thisweek_table(jeff_sun_ipo_data, "jeff_sun_ipo_thisweek", "change", False)
            jeff_sun_short_data = jeff_sun_high_short_float_screener()
            jeff_sun_short_table = build_jeff_sun_high_short_float_table(jeff_sun_short_data, "jeff_sun_high_short_float", "change", False)
            return [qulla_table, qulla_data, minervini_table, minervini_data, oneil_table, oneil_data, jeff_sun_table, jeff_sun_data, jeff_sun_adr_table, jeff_sun_adr_data, jeff_sun_bases_table, jeff_sun_bases_data, jeff_sun_1w20_table, jeff_sun_1w20_data, jeff_sun_4w30_table, jeff_sun_4w30_data, jeff_sun_4w50_table, jeff_sun_4w50_data, jeff_sun_13w50_table, jeff_sun_13w50_data, jeff_sun_26w100_table, jeff_sun_26w100_data, jeff_sun_ipo_table, jeff_sun_ipo_data, jeff_sun_short_table, jeff_sun_short_data]
        except Exception as e:
            logger.exception("Group B failed: %s", e)
            return [_err_div(e), [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, []]

    _GROUP_B_EXTRA = ["jeff_sun_liquid_etfs", "julian_komar_strongest"]

    @app.callback(
        [
            Output("jeff_sun_liquid_etfs-content", "children"),
            Output("jeff_sun_liquid_etfs-data-store", "data"),
            Output("julian_komar_strongest-content", "children"),
            Output("julian_komar_strongest-data-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-jeff_sun_liquid_etfs", "n_clicks"),
            Input("btn-refresh-julian_komar_strongest", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_b_extra(n_intervals, n_clicks, btn_liq, btn_julian):
        tid = ctx.triggered_id if ctx.triggered else None
        single = None
        if tid and isinstance(tid, str) and tid.startswith("btn-refresh-"):
            single = tid.replace("btn-refresh-", "")
            if single in _GROUP_B_EXTRA:
                _invalidate_widget_cache(single)
        try:
            if single == "jeff_sun_liquid_etfs":
                d = jeff_sun_liquid_etfs_screener()
                return build_jeff_sun_liquid_etfs_table(d, "jeff_sun_liquid_etfs", "change", False), d, no_update, no_update
            if single == "julian_komar_strongest":
                d = julian_komar_strongest_screener()
                return no_update, no_update, build_julian_komar_strongest_table(d, "julian_komar_strongest", "change", False), d
            d1 = jeff_sun_liquid_etfs_screener()
            d2 = julian_komar_strongest_screener()
            return (
                build_jeff_sun_liquid_etfs_table(d1, "jeff_sun_liquid_etfs", "change", False), d1,
                build_julian_komar_strongest_table(d2, "julian_komar_strongest", "change", False), d2,
            )
        except Exception as e:
            logger.exception("Group B extra failed: %s", e)
            return [_disabled_msg, [], _disabled_msg, []]

    @app.callback(
        [
            Output("sector-content", "children"),
            Output("sector-data-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-sector", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_c(n_intervals, n_clicks, btn_w):
        if btn_w:
            _invalidate_widget_cache("sector")
        try:
            sector_data = compute_sector_data()
            return build_sector_table(sector_data, "sector", "chg", False), sector_data
        except Exception as e:
            logger.exception("Sector data failed: %s", e)
            return _err_div(e), []

    @app.callback(
        [
            Output("earnings-calendar-week-content", "children"),
            Output("earnings-calendar-week-data-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-earnings-calendar-week", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_earnings_calendar_week(n_intervals, n_clicks, btn_w):
        if btn_w:
            _invalidate_widget_cache("earnings-calendar-week")
        try:
            from src.data_fetcher import fetch_earnings_this_week
            data = fetch_earnings_this_week()
            return build_earnings_calendar_table(data, "earnings-calendar-week", "market_cap", False), data
        except Exception as e:
            logger.exception("Earnings Calendar Week failed: %s", e)
            return _err_div(e), []

    @app.callback(
        [
            Output("stockbee-content", "children"),
            Output("stockbee-data-store", "data"),
            Output("stockbee-sort-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-stockbee", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_stockbee(n_intervals, n_clicks, btn_w):
        if btn_w:
            _invalidate_widget_cache("stockbee")
        try:
            from src.stockbee import fetch_stockbee_momentum50
            from src.data_fetcher import fetch_tickers_bulk_csv
            mom = fetch_stockbee_momentum50()
            dates = mom.get("dates", [])
            tickers = mom.get("tickers", {})
            if not dates or not tickers:
                return html.Div("No Momentum50 data. Check Stockbee sheet.", style={
                    "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                }), {}, no_update
            latest_date = dates[0]
            ticker_list = tickers.get(latest_date, [])
            if not ticker_list:
                return html.Div("No tickers for latest date.", style={
                    "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                }), {}, no_update
            cache_key = f"momentum50_quotes_{','.join(sorted(t.strip().upper() for t in ticker_list))}"
            data = fetch_tickers_bulk_csv(ticker_list, cache_key=cache_key)
            if not data:
                data = [{"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"} for t in ticker_list]
            else:
                by_ticker = {r["ticker"]: r for r in data}
                data = [by_ticker.get(t.upper(), {"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"}) for t in ticker_list]
            # Always show spreadsheet order (no sort) on refresh; user can click headers to sort
            return build_stockbee_momentum50_table(data, date_label=latest_date, widget_id="stockbee", sort_col=None, sort_asc=True), {"data": data, "date_label": latest_date}, {"col": None, "asc": True}
        except Exception as e:
            logger.exception("Stockbee Momentum50 failed: %s", e)
            return _err_div(e), [], no_update

    @app.callback(
        Output("breadth-content", "children"),
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-breadth", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_breadth(n_intervals, n_clicks, btn_w):
        if btn_w:
            _invalidate_widget_cache("breadth")
        try:
            from src.stockbee import fetch_stockbee_breadth
            breadth = fetch_stockbee_breadth()
            return build_stockbee_breadth(breadth)
        except Exception as e:
            logger.exception("Stock Market Breadth failed: %s", e)
            return _err_div(e)

    @app.callback(
        [
            Output("breadth-primary-content", "children"),
            Output("breadth-ratios-content", "children"),
            Output("breadth-secondary-content", "children"),
            Output("breadth-sp500-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ]
        + [Input(f"btn-refresh-{w}", "n_clicks") for w in ["breadth-primary", "breadth-ratios", "breadth-secondary", "breadth-sp500"]],
        prevent_initial_call=False,
    )
    def refresh_breadth_charts(n_intervals, n_clicks, *btn_clicks):
        if any(btn_clicks):
            _invalidate_widget_cache("breadth-primary")
        try:
            from src.stockbee import fetch_stockbee_breadth_history
            history = fetch_stockbee_breadth_history(days=60)
            if not history:
                empty = html.Div("No breadth history. Start Stockbee API or check Sheets.", style={
                    "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                })
                return [empty, empty, empty, empty]
            fig1 = build_primary_breadth_chart(history)
            fig2 = build_breadth_ratios_chart(history)
            fig3 = build_secondary_breadth_chart(history)
            fig4 = build_sp500_chart(history)
            chart_style = {"height": "200px", "width": "100%", "minWidth": 0, "overflow": "hidden"}
            return [
                dcc.Graph(figure=fig1, config=GRAPH_CONFIG_ZOOM, style=chart_style),
                dcc.Graph(figure=fig2, config=GRAPH_CONFIG_ZOOM, style=chart_style),
                dcc.Graph(figure=fig3, config=GRAPH_CONFIG_ZOOM, style=chart_style),
                dcc.Graph(figure=fig4, config=GRAPH_CONFIG_ZOOM, style=chart_style),
            ]
        except Exception as e:
            logger.exception("Breadth charts failed: %s", e)
            err = _err_div(e)
            return [err, err, err, err]

    @app.callback(
        [
            Output("rrg-figure-store", "data"),
            Output("rrg-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-rrg", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_rrg(n_intervals, n_clicks, btn_w):
        if btn_w:
            _invalidate_widget_cache("rrg")
        try:
            rrg_data = compute_rrg_data()
            fig = build_rrg_chart(rrg_data)
            graph = dcc.Graph(
                id="rrg-graph",
                figure=fig,
                config=GRAPH_CONFIG,
                style={"height": "100%", "width": "100%"},
            )
            return fig.to_dict(), graph
        except Exception as e:
            logger.exception("RRG failed: %s", e)
            return None, _err_div(e)

    @app.callback(
        [
            Output("sp500-landscape-data-store", "data"),
            Output("sp500-landscape-sector-filter", "options"),
            Output("sp500-landscape-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-sp500-landscape", "n_clicks"),
            Input("sp500-landscape-sector-filter", "value"),
        ],
        State("sp500-landscape-data-store", "data"),
        prevent_initial_call=False,
    )
    def refresh_sp500_landscape(n_intervals, n_clicks, btn_w, sector_filter, stored_data):
        from src.data_fetcher import fetch_sp500_landscape_data

        triggered = ctx.triggered_id if ctx.triggered else None
        is_filter_change = triggered == "sp500-landscape-sector-filter"

        if is_filter_change:
            data = stored_data or []
            if not data:
                return no_update, no_update, html.Div("No data. Refresh to load.", style={
                    "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                })
            fig = build_sp500_landscape_chart(data, sector_filter=sector_filter)
            return no_update, no_update, dcc.Graph(
                figure=fig,
                config=GRAPH_CONFIG_ZOOM,
                style={"height": "100%", "width": "100%"},
            )

        if btn_w:
            _invalidate_widget_cache("sp500-landscape")
        try:
            data = fetch_sp500_landscape_data()
            if not data:
                return [], [], html.Div("No S&P 500 data. FinViz Elite required.", style={
                    "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                })
            sectors = sorted(set((str(r.get("sector", "") or "Unknown").strip() or "Unknown") for r in data))
            options = [{"label": s, "value": s} for s in sectors]
            fig = build_sp500_landscape_chart(data, sector_filter=sector_filter)
            return data, options, dcc.Graph(
                figure=fig,
                config=GRAPH_CONFIG_ZOOM,
                style={"height": "100%", "width": "100%"},
            )
        except Exception as e:
            logger.exception("S&P 500 Landscape failed: %s", e)
            return no_update, no_update, _err_div(e)

    _GROUP_D_WIDGETS = ["club97", "movers", "weekly", "daily", "in_play", "intraday-earnings", "pre_market"]

    @app.callback(
        [
            Output("club97-content", "children"),
            Output("club97-data-store", "data"),
            Output("club97-sort-store", "data"),
            Output("movers-content", "children"),
            Output("movers-data-store", "data"),
            Output("weekly-content", "children"),
            Output("weekly-data-store", "data"),
            Output("daily-content", "children"),
            Output("daily-data-store", "data"),
            Output("in_play-content", "children"),
            Output("in_play-data-store", "data"),
            Output("intraday-earnings-content", "children"),
            Output("intraday-earnings-data-store", "data"),
            Output("pre_market-content", "children"),
            Output("pre_market-data-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ]
        + [Input(f"btn-refresh-{w}", "n_clicks") for w in _GROUP_D_WIDGETS],
        prevent_initial_call=False,
    )
    def refresh_group_d(n_intervals, n_clicks, *btn_clicks):
        tid = ctx.triggered_id if ctx.triggered else None
        single_widget = None
        if tid and isinstance(tid, str) and tid.startswith("btn-refresh-"):
            single_widget = tid.replace("btn-refresh-", "")
            if single_widget in _GROUP_D_WIDGETS:
                _invalidate_widget_cache(single_widget)

        def _out(*vals):
            """Build output list; use no_update for widgets we didn't refresh when single_widget is set."""
            if not single_widget:
                return list(vals)
            out = [no_update] * 15
            idx = _GROUP_D_WIDGETS.index(single_widget) if single_widget in _GROUP_D_WIDGETS else -1
            if idx == 0:
                out[0], out[1], out[2] = vals[0], vals[1], vals[2]
            elif idx == 1:
                out[3], out[4] = vals[3], vals[4]
            elif idx == 2:
                out[5], out[6] = vals[5], vals[6]
            elif idx == 3:
                out[7], out[8] = vals[7], vals[8]
            elif idx == 4:
                out[9], out[10] = vals[9], vals[10]
            elif idx == 5:
                out[11], out[12] = vals[11], vals[12]
            elif idx == 6:
                out[13], out[14] = vals[13], vals[14]
            else:
                return list(vals)
            return out

        try:
            if single_widget == "club97":
                d = compute_97_club([])
                return _out(build_97_club_table(d, "club97", "change", False), d, {"col": "change", "asc": False},
                    no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update)
            if single_widget == "movers":
                d = compute_9m_movers([])
                return _out(no_update, no_update, no_update, build_9m_movers_table(d, "movers", "change", False), d,
                    no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update)
            if single_widget == "weekly":
                d = compute_20pct_weekly([])
                return _out(no_update, no_update, no_update, no_update, no_update, build_20pct_weekly_table(d, "weekly", "week", False), d,
                    no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update)
            if single_widget == "daily":
                d = compute_4pct_daily([])
                return _out(no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    build_4pct_daily_table(d, "daily", "chg", False), d, no_update, no_update, no_update, no_update,
                    no_update, no_update)
            if single_widget == "intraday-earnings":
                d = compute_earnings_yesterday_today([])
                et = build_earnings_table(d, "intraday-earnings", "change", False)
                # Outputs 0–10 = club97…in_play (11 slots); 11–12 = intraday earnings; 13–14 = pre_market
                return _out(
                    no_update, no_update, no_update,
                    no_update, no_update,
                    no_update, no_update,
                    no_update, no_update,
                    no_update, no_update,
                    et, d,
                    no_update, no_update,
                )
            if single_widget == "in_play":
                d = compute_stocks_in_play([])
                return _out(no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    build_stocks_in_play_table(d, "in_play", "change", False), d,
                    no_update, no_update, no_update, no_update)
            if single_widget == "pre_market":
                d = compute_pre_market_scanner([])
                gap = next((c for c in (d[0].keys() if d else []) if "gap" in c.lower() and "url" not in c.lower()), "Gap")
                return _out(no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update,
                    build_pre_market_scanner_table(d, "pre_market", gap, False), d)

            # Full refresh
            club97_data = compute_97_club([])
            club97_table = build_97_club_table(club97_data, "club97", "change", False)
            movers_data = compute_9m_movers([])
            movers_table = build_9m_movers_table(movers_data, "movers", "change", False)
            weekly_data = compute_20pct_weekly([])
            weekly_table = build_20pct_weekly_table(weekly_data, "weekly", "week", False)
            daily_data = compute_4pct_daily([])
            daily_table = build_4pct_daily_table(daily_data, "daily", "chg", False)
            earnings_data = compute_earnings_yesterday_today([])
            earnings_table = build_earnings_table(earnings_data, "intraday-earnings", "change", False)
            in_play_data = compute_stocks_in_play([])
            in_play_table = build_stocks_in_play_table(in_play_data, "in_play", "change", False)
            pre_market_data = compute_pre_market_scanner([])
            gap_col = next((c for c in (pre_market_data[0].keys() if pre_market_data else []) if "gap" in c.lower() and "url" not in c.lower()), "Gap")
            pre_market_table = build_pre_market_scanner_table(pre_market_data, "pre_market", gap_col, False)
            return [
                club97_table, club97_data, {"col": "change", "asc": False},
                movers_table, movers_data,
                weekly_table, weekly_data, daily_table, daily_data,
                in_play_table, in_play_data,
                earnings_table, earnings_data,
                pre_market_table, pre_market_data,
            ]
        except Exception as e:
            logger.exception("Group D failed: %s", e)
            return [_err_div(e), [], no_update, _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, []]

    # ------------------------------------------------------------------
    # Macro Monitor — FRED-backed panel + history modal
    # ------------------------------------------------------------------
    @app.callback(
        Output("macro-monitor-content", "children"),
        [
            Input("interval-macro", "n_intervals"),
            Input("main-tabs", "data"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_macro_monitor(n_interval, tab, n_refresh):
        if tab != "macro-monitor":
            return no_update
        force = ctx.triggered_id == "btn-refresh" and n_refresh
        if force:
            from src.macro_data import invalidate_macro_cache

            invalidate_macro_cache()
        try:
            from src.macro_data import fetch_macro_bundle
            from src.macro_monitor_layout import build_macro_monitor_content

            return build_macro_monitor_content(fetch_macro_bundle(force=bool(force)))
        except Exception as e:
            logger.exception("Macro Monitor failed: %s", e)
            return html.Div(str(e), style={"color": COLORS["red"], "padding": "16px", "fontSize": "11px"})

    @app.callback(
        Output("macro-selected-metric", "data"),
        Input({"type": "macro-kpi", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def macro_kpi_clicked(_clicks):
        trig = ctx.triggered_id
        if isinstance(trig, dict) and trig.get("type") == "macro-kpi":
            return trig["index"]
        return no_update

    @app.callback(
        Output("macro-selected-metric", "data", allow_duplicate=True),
        Input("macro-history-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def macro_history_close(_n):
        return None

    @app.callback(
        Output("macro-selected-metric", "data", allow_duplicate=True),
        Input("main-tabs", "data"),
        prevent_initial_call=True,
    )
    def clear_macro_metric_when_leaving_macro_tab(tab):
        if tab != "macro-monitor":
            return None
        return no_update

    @app.callback(
        Output("macro-history-panel", "style"),
        Input("macro-selected-metric", "data"),
        prevent_initial_call=False,
    )
    def macro_history_panel_visibility(sel):
        if sel is None:
            return {"display": "none"}
        return {
            "display": "block",
            "marginTop": "14px",
        }

    @app.callback(
        [
            Output("macro-history-graph", "figure"),
            Output("macro-history-title", "children"),
        ],
        [
            Input("macro-selected-metric", "data"),
            Input("macro-lookback", "value"),
        ],
        prevent_initial_call=False,
    )
    def macro_history_chart(metric_id, lookback):
        def _empty_fig(msg: str):
            fig = go.Figure()
            fig.update_layout(
                paper_bgcolor=COLORS["surface"],
                plot_bgcolor=COLORS["surface"],
                margin=dict(l=40, r=20, t=40, b=40),
                annotations=[
                    dict(
                        text=msg,
                        xref="paper",
                        yref="paper",
                        x=0.5,
                        y=0.5,
                        showarrow=False,
                        font=dict(size=12, color=COLORS["text_muted"]),
                    )
                ],
                height=400,
                autosize=True,
            )
            return fig

        if not metric_id:
            return _empty_fig("Select a KPI card to view history"), "History"
        try:
            from src.macro_data import get_series_for_chart
            from src.macro_monitor_layout import build_macro_history_figure

            yrs = int(lookback or 10)
            chart = get_series_for_chart(metric_id, yrs)
            if chart.get("error"):
                return _empty_fig(str(chart.get("error", "No data"))), chart.get("title", metric_id)
            return build_macro_history_figure(chart), chart.get("title", metric_id)
        except Exception as e:
            logger.exception("Macro history chart: %s", e)
            return _empty_fig(str(e)), "Error"

    @app.callback(
        Output("cnbc_premarket-content", "children"),
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-cnbc_premarket", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_cnbc_premarket(n_intervals, n_clicks, btn_widget):
        if btn_widget:
            _invalidate_widget_cache("cnbc_premarket")
        try:
            from src.cnbc_premarket import fetch_cnbc_premarket_watchlist
            data = fetch_cnbc_premarket_watchlist()
            article_url = data[0].get("url", "") if data else ""
            return build_cnbc_premarket_watchlist_table(data, article_url)
        except Exception as e:
            logger.exception("CNBC Pre-Market Watchlist failed: %s", e)
            return _err_div(e)

    @app.callback(
        Output("live_index-content", "children"),
        [
            Input("interval-live-snapshot", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-live_index", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_live_index(n_intervals, n_clicks, btn_widget):
        if btn_widget:
            _invalidate_widget_cache("live_index")
        try:
            from src.data_fetcher import fetch_live_index_quotes
            data = fetch_live_index_quotes()
            return build_live_index_snapshot(data)
        except Exception as e:
            logger.exception("Market Snapshot failed: %s", e)
            return _err_div(e)

    _GROUP_E_WIDGETS = ["leading", "thematics", "thematics-sector", "top_gainers", "top_losers", "stage"]

    @app.callback(
        [
            Output("leading-content", "children"),
            Output("leading-data-store", "data"),
            Output("thematics-content", "children"),
            Output("thematics-data-store", "data"),
            Output("thematics-sector-content", "children"),
            Output("thematics-sector-data-store", "data"),
            Output("top_gainers-content", "children"),
            Output("top_losers-content", "children"),
            Output("stage-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ]
        + [Input(f"btn-refresh-{w}", "n_clicks") for w in _GROUP_E_WIDGETS],
        prevent_initial_call=False,
    )
    def refresh_group_e(n_intervals, n_clicks, *btn_clicks):
        tid = ctx.triggered_id if ctx.triggered else None
        single_widget = None
        if tid and isinstance(tid, str) and tid.startswith("btn-refresh-"):
            single_widget = tid.replace("btn-refresh-", "")
            if single_widget in _GROUP_E_WIDGETS:
                _invalidate_widget_cache(single_widget)
                if single_widget in ("top_gainers", "top_losers"):
                    _invalidate_widget_cache("thematics")  # share thematics_data

        def _out(*vals):
            if not single_widget:
                return list(vals)
            out = [no_update] * 9
            idx = _GROUP_E_WIDGETS.index(single_widget) if single_widget in _GROUP_E_WIDGETS else -1
            if idx == 0:
                out[0], out[1] = vals[0], vals[1]
            elif idx == 1:
                out[2], out[3] = vals[2], vals[3]
            elif idx == 2:
                out[4], out[5] = vals[4], vals[5]
            elif idx == 3:
                out[6] = vals[6]
            elif idx == 4:
                out[7] = vals[7]
            elif idx == 5:
                out[8] = vals[8]
            else:
                return list(vals)
            return out

        try:
            if single_widget == "leading":
                d = compute_leading_industries([], {})
                return _out(build_leading_industries_table(d, "leading", "top_both", False), d,
                    no_update, no_update, no_update, no_update, no_update, no_update, no_update)
            if single_widget == "thematics":
                d = compute_thematics([])
                return _out(no_update, no_update, build_thematics_table(d, "thematics", "top_both", False), d,
                    no_update, no_update, no_update, no_update, no_update)
            if single_widget == "thematics-sector":
                d = compute_thematics_sector_data()
                return _out(no_update, no_update, no_update, no_update, build_thematics_sector_table(d, "thematics-sector", "year", False), d,
                    no_update, no_update, no_update)
            if single_widget == "top_gainers":
                g, l = compute_top_gainers_losers(12)
                return _out(no_update, no_update, no_update, no_update, no_update, no_update,
                    build_top_gainers_table(g), no_update, no_update)
            if single_widget == "top_losers":
                g, l = compute_top_gainers_losers(12)
                return _out(no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, build_top_losers_table(l), no_update)
            if single_widget == "stage":
                r = compute_stage_analysis([])
                c = r.get("counts", {})
                sc = html.Div([
                    build_stage_summary(c),
                    html.Div([
                        dcc.Graph(figure=build_stage_chart(c), config=GRAPH_CONFIG, style={"height": "100%", "width": "100%"}),
                    ], style={**CHART_WRAP_STYLE, "flex": 1, "minHeight": 0, "display": "flex", "flexDirection": "column"}),
                ], style={**CHART_WRAP_STYLE, "display": "flex", "flexDirection": "column", "height": "100%"})
                return _out(no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, sc)

            leading_data = compute_leading_industries([], {})
            leading_table = build_leading_industries_table(leading_data, "leading", "top_both", False)
            thematics_data = compute_thematics([])
            thematics_table = build_thematics_table(thematics_data, "thematics", "top_both", False)
            thematics_sector_data = compute_thematics_sector_data()
            thematics_sector_table = build_thematics_sector_table(thematics_sector_data, "thematics-sector", "year", False)
            gainers_data, losers_data = compute_top_gainers_losers(12)
            top_gainers_table = build_top_gainers_table(gainers_data)
            top_losers_table = build_top_losers_table(losers_data)
            stage_result = compute_stage_analysis([])
            counts = stage_result.get("counts", {})
            stage_content = html.Div([
                build_stage_summary(counts),
                html.Div([
                    dcc.Graph(figure=build_stage_chart(counts), config=GRAPH_CONFIG, style={"height": "100%", "width": "100%"}),
                ], style={**CHART_WRAP_STYLE, "flex": 1, "minHeight": 0, "display": "flex", "flexDirection": "column"}),
            ], style={**CHART_WRAP_STYLE, "display": "flex", "flexDirection": "column", "height": "100%"})
            return [leading_table, leading_data, thematics_table, thematics_data, thematics_sector_table, thematics_sector_data, top_gainers_table, top_losers_table, stage_content]
        except Exception as e:
            logger.exception("Group E (Leading/Thematics/Stage) failed: %s", e)
            return [_err_div(e), [], _disabled_msg, [], _err_div(e), [], _err_div(e), _err_div(e), _disabled_msg]

    @app.callback(
        [
            Output("thematics-rrg-figure-store", "data"),
            Output("thematics-rrg-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
            Input("btn-refresh-thematics-rrg", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_thematics_rrg(n_intervals, n_clicks, btn_widget):
        if btn_widget:
            _invalidate_widget_cache("thematics-rrg")
        try:
            rrg_data = compute_thematics_rrg_data()
            fig = build_rrg_chart(rrg_data)
            graph = dcc.Graph(
                id="thematics-rrg-graph",
                figure=fig,
                config=GRAPH_CONFIG,
                style={"height": "100%", "width": "100%"},
            )
            return fig.to_dict(), graph
        except Exception as e:
            logger.exception("Thematics RRG failed: %s", e)
            return None, _err_div(e)

    # ------------------------------------------------------------------
    # Sortable table: header click -> re-sort and re-render
    # ------------------------------------------------------------------
    SORTABLE_WIDGETS = {
        "qulla": (build_qullamaggie_table, "qulla-content", {}),
        "minervini": (build_minervini_table, "minervini-content", {}),
        "oneil": (build_oneil_table, "oneil-content", {}),
        "jeff_sun_canslim": (build_jeff_sun_canslim_table, "jeff_sun_canslim-content", {}),
        "jeff_sun_high_adr": (build_jeff_sun_high_adr_table, "jeff_sun_high_adr-content", {}),
        "jeff_sun_extended_bases": (build_jeff_sun_extended_bases_table, "jeff_sun_extended_bases-content", {}),
        "jeff_sun_1w20": (build_jeff_sun_1w20_table, "jeff_sun_1w20-content", {}),
        "jeff_sun_4w30": (build_jeff_sun_4w30_table, "jeff_sun_4w30-content", {}),
        "jeff_sun_4w50": (build_jeff_sun_4w50_table, "jeff_sun_4w50-content", {}),
        "jeff_sun_13w50": (build_jeff_sun_13w50_table, "jeff_sun_13w50-content", {}),
        "jeff_sun_26w100": (build_jeff_sun_26w100_table, "jeff_sun_26w100-content", {}),
        "jeff_sun_ipo_thisweek": (build_jeff_sun_ipo_thisweek_table, "jeff_sun_ipo_thisweek-content", {}),
        "jeff_sun_high_short_float": (build_jeff_sun_high_short_float_table, "jeff_sun_high_short_float-content", {}),
        "jeff_sun_liquid_etfs": (build_jeff_sun_liquid_etfs_table, "jeff_sun_liquid_etfs-content", {}),
        "julian_komar_strongest": (build_julian_komar_strongest_table, "julian_komar_strongest-content", {}),
        "watchlist": (build_watchlist_table, "watchlist-content", {}),
        "sector": (build_sector_table, "sector-content", {}),
        "club97": (build_97_club_table, "club97-content", {}),
        "movers": (build_9m_movers_table, "movers-content", {}),
        "weekly": (build_20pct_weekly_table, "weekly-content", {}),
        "daily": (build_4pct_daily_table, "daily-content", {}),
        "in_play": (build_stocks_in_play_table, "in_play-content", {}),
        "intraday-earnings": (build_earnings_table, "intraday-earnings-content", {}),
        "earnings-calendar-week": (build_earnings_calendar_table, "earnings-calendar-week-content", {}),
        "pre_market": (build_pre_market_scanner_table, "pre_market-content", {}),
        "leading": (build_leading_industries_table, "leading-content", {}),
        "thematics": (build_thematics_table, "thematics-content", {}),
        "thematics-sector": (build_thematics_sector_table, "thematics-sector-content", {}),
        "stockbee": (build_stockbee_momentum50_table, "stockbee-content", {}),
    }

    @app.callback(
        [Output(f"{w}-content", "children", allow_duplicate=True) for w in SORTABLE_WIDGETS] +
        [Output(f"{w}-sort-store", "data", allow_duplicate=True) for w in SORTABLE_WIDGETS],
        Input({"type": "sort-header", "widget": ALL, "column": ALL}, "n_clicks"),
        [State(f"{w}-data-store", "data") for w in SORTABLE_WIDGETS] +
        [State(f"{w}-sort-store", "data") for w in SORTABLE_WIDGETS] +
        [State("watchlist-view-store", "data")],
        prevent_initial_call=True,
    )
    def sort_table(n_clicks_list, *stores):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            return [no_update] * len(SORTABLE_WIDGETS) * 2
        # Ignore spurious triggers (e.g. pattern-match firing before user click)
        triggered = ctx.triggered[0] if ctx.triggered else {}
        if triggered.get("value") is None or (isinstance(triggered.get("value"), (int, float)) and triggered.get("value", 0) < 1):
            return [no_update] * len(SORTABLE_WIDGETS) * 2
        wid = ctx.triggered_id.get("widget")
        col = ctx.triggered_id.get("column")
        if not wid or wid not in SORTABLE_WIDGETS or not col:
            return [no_update] * len(SORTABLE_WIDGETS) * 2
        watchlist_view = stores[-1] if len(stores) > len(SORTABLE_WIDGETS) * 2 else "watchlist"
        builder, content_id, extra = SORTABLE_WIDGETS[wid]
        data_idx = list(SORTABLE_WIDGETS.keys()).index(wid)
        sort_idx = len(SORTABLE_WIDGETS) + data_idx
        data = stores[data_idx] if data_idx < len(stores) else []
        sort_state = stores[sort_idx] if sort_idx < len(stores) else {}
        raw = stores[data_idx]
        if wid == "stockbee" and isinstance(raw, dict):
            data = raw.get("data", [])
            date_label = raw.get("date_label", "")
        else:
            data = raw or []
            date_label = ""
        if not data:
            return [no_update] * len(SORTABLE_WIDGETS) * 2
        cur_col = sort_state.get("col", "change")
        cur_asc = sort_state.get("asc", True)
        new_asc = not cur_asc if col == cur_col else True
        new_sort = {"col": col, "asc": new_asc}
        if wid == "stockbee":
            raw = stores[data_idx]
            date_label = raw.get("date_label", "") if isinstance(raw, dict) else ""
            table = build_stockbee_momentum50_table(data, date_label=date_label, widget_id=wid, sort_col=col, sort_asc=new_asc)
        elif wid == "watchlist":
            show_remove = not watchlist_view or str(watchlist_view).strip() == "watchlist"
            table = build_watchlist_table(data, wid, col, new_asc, show_remove=show_remove)
        else:
            builder, _, _ = SORTABLE_WIDGETS[wid]
            table = builder(data, wid, col, new_asc)
        out_content = [no_update] * len(SORTABLE_WIDGETS)
        out_sort = [no_update] * len(SORTABLE_WIDGETS)
        out_content[data_idx] = table
        out_sort[data_idx] = new_sort
        return out_content + out_sort

    # ------------------------------------------------------------------
    # Export watchlist: TradingView-friendly .txt (one symbol per line)
    # ------------------------------------------------------------------
    from src.watchlist_export import (
        WIDGET_DATA_STORE_IDS,
        extract_tickers_from_rows,
        build_tradingview_file_body,
        tickers_from_fallback,
    )

    @app.callback(
        Output("download-watchlist-tv", "data"),
        Input({"type": "export-watchlist", "widget": ALL}, "n_clicks"),
        [State(f"{w}-data-store", "data") for w in WIDGET_DATA_STORE_IDS],
        prevent_initial_call=True,
    )
    def export_watchlist_tradingview(n_clicks, *store_values):
        triggered = ctx.triggered[0] if ctx.triggered else {}
        if triggered.get("value") is None or (
            isinstance(triggered.get("value"), (int, float)) and triggered.get("value", 0) < 1
        ):
            raise PreventUpdate
        wid_info = ctx.triggered_id
        if not isinstance(wid_info, dict) or wid_info.get("type") != "export-watchlist":
            raise PreventUpdate
        widget_id = wid_info.get("widget")
        if not widget_id:
            raise PreventUpdate

        symbols: list[str] = []
        if widget_id in WIDGET_DATA_STORE_IDS:
            idx = WIDGET_DATA_STORE_IDS.index(widget_id)
            rows = store_values[idx] if idx < len(store_values) else None
            symbols = extract_tickers_from_rows(rows)
        if not symbols:
            symbols = tickers_from_fallback(widget_id)

        body = build_tradingview_file_body(symbols)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(widget_id))[:80]
        fname = f"{safe_name}_tradingview_watchlist.txt"
        return dcc.send_string(body, filename=fname, type="text/plain")
