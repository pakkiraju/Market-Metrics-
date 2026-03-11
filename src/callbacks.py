"""Dash callbacks: progressive per-widget-group refresh, widget toggles,
TradingView modal, watchlist management.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dash import html, dcc, Input, Output, State, callback, no_update, ctx, ALL
import plotly.graph_objects as go

from src import cache
from src.constants import COLORS
from src.calculations import (
    compute_all_key_metrics,
    compute_sector_data,
    compute_97_club,
    compute_9m_movers,
    compute_20pct_weekly,
    compute_4pct_daily,
    compute_leading_industries,
    compute_stage_analysis,
)
from src.screeners import (
    qullamaggie_screener,
    minervini_screener,
    oneil_screener,
)
from src.layout import (
    build_key_metrics_table,
    build_metrics_bar_chart,
    build_sector_table,
    build_97_club_table,
    build_9m_movers_table,
    build_20pct_weekly_table,
    build_4pct_daily_table,
    build_leading_industries_table,
    build_stage_chart,
    build_stage_summary,
    build_ticker_grid,
    build_minervini_table,
    build_oneil_table,
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
    return html.Div(f"Error: {e}", style={
        "color": COLORS["red"], "padding": "8px", "fontSize": "10px",
    })


def register_callbacks(app):
    """Register all Dash callbacks on the app."""

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
        try:
            idx = current_list.index(ticker)
            if idx >= len(n_clicks_list) or not (n_clicks_list[idx] or 0):
                return no_update
        except (ValueError, IndexError, TypeError):
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
    # 6. Watchlist: fetch Finviz data and render table
    # ------------------------------------------------------------------
    @app.callback(
        Output("watchlist-content", "children"),
        [
            Input("watchlist-store", "data"),
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
    )
    def render_watchlist(wl_data, n_intervals, n_clicks):
        if not wl_data:
            return html.Div("No tickers in watchlist. Add some above.", style={
                "color": COLORS["text_muted"], "fontSize": "9px",
                "padding": "8px",
            })
        try:
            from src.data_fetcher import fetch_watchlist_quotes
            data = fetch_watchlist_quotes(wl_data)
            if not data:
                # Fallback: show tickers with placeholder when Finviz returns no data
                data = [{"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"} for t in wl_data]
            return build_watchlist_table(data)
        except Exception as e:
            logger.exception("Watchlist fetch failed: %s", e)
            return _err_div(e)

    # ==================================================================
    #  PARALLEL WIDGET LOADING
    #  Each group loads independently; widgets appear as soon as ready.
    # ==================================================================

    # Key Metrics: sequential fetch (parallel causes rate limits)
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
        ],
        prevent_initial_call=False,
    )
    def refresh_group_a(n_intervals, n_clicks):
        try:
            metrics = compute_all_key_metrics()
            key_metrics_table = build_key_metrics_table(metrics)
            nq100_data = metrics.get("NQ100", [])
            spy500_data = metrics.get("SPY500", [])
            djia_data = metrics.get("DJIA", [])
            rus_data = metrics.get("RUS2000", [])
            b1_data = metrics.get("$1B+", [])

            # Chart 2: NQ100 vs SPY500 vs DJIA (3-way)
            chart2_fig = build_metrics_bar_chart([
                (nq100_data, "NQ100", "#991b1b", "#dc2626"),
                (spy500_data, "SPY500", "#166534", "#22c55e"),
                (djia_data, "DJIA", "#1e3a5f", "#3b82f6"),
            ])
            chart2 = dcc.Graph(
                figure=chart2_fig,
                config={"displayModeBar": False},
                style={"height": "100%", "width": "100%"},
            )
            # Chart 3: RUS2000 vs $1B+
            chart3_fig = build_metrics_bar_chart([
                (rus_data, "RUS2000", "#7f1d1d", "#ef4444"),
                (b1_data, "$1B+", "#14532d", "#4ade80"),
            ])
            chart3 = dcc.Graph(
                figure=chart3_fig,
                config={"displayModeBar": False},
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

    @app.callback(
        [
            Output("qulla-content", "children"),
            Output("minervini-content", "children"),
            Output("oneil-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_b(n_intervals, n_clicks):
        try:
            qulla_data = qullamaggie_screener()
            qulla_table = build_qullamaggie_table(qulla_data)
            minervini_data = minervini_screener()
            minervini_table = build_minervini_table(minervini_data)
            oneil_data = oneil_screener()
            oneil_table = build_oneil_table(oneil_data)
            return [qulla_table, minervini_table, oneil_table]
        except Exception as e:
            logger.exception("Group B failed: %s", e)
            return [_err_div(e), _disabled_msg, _disabled_msg]

    @app.callback(
        Output("sector-content", "children"),
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_c(n_intervals, n_clicks):
        try:
            sector_data = compute_sector_data()
            return build_sector_table(sector_data)
        except Exception as e:
            logger.exception("Sector data failed: %s", e)
            return _err_div(e)

    @app.callback(
        [
            Output("club97-content", "children"),
            Output("movers-content", "children"),
            Output("weekly-content", "children"),
            Output("daily-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_d(n_intervals, n_clicks):
        try:
            club97_data = compute_97_club([])
            club97_table = build_97_club_table(club97_data)
            movers_data = compute_9m_movers([])
            movers_table = build_9m_movers_table(movers_data)
            weekly_data = compute_20pct_weekly([])
            weekly_table = build_20pct_weekly_table(weekly_data)
            daily_data = compute_4pct_daily([])
            daily_table = build_4pct_daily_table(daily_data)
            return [club97_table, movers_table, weekly_table, daily_table]
        except Exception as e:
            logger.exception("Group D failed: %s", e)
            return [_err_div(e), _disabled_msg, _disabled_msg, _disabled_msg]

    @app.callback(
        [
            Output("leading-content", "children"),
            Output("stage-content", "children"),
        ],
        Input("interval-refresh", "n_intervals"),
        prevent_initial_call=False,
    )
    def refresh_group_e(_):
        return [_disabled_msg, _disabled_msg]
