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
    compute_rrg_data,
    compute_97_club,
    compute_9m_movers,
    compute_20pct_weekly,
    compute_4pct_daily,
    compute_earnings_yesterday_today,
    compute_stocks_in_play,
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
    build_rrg_chart,
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
    build_stocks_in_play_table,
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
    return html.Div(f"Error: {e}", style={
        "color": COLORS["red"], "padding": "8px", "fontSize": "10px",
    })


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
        [
            Output("watchlist-content", "children"),
            Output("watchlist-data-store", "data"),
        ],
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
            }), []
        try:
            from src.data_fetcher import fetch_watchlist_quotes
            data = fetch_watchlist_quotes(wl_data)
            if not data:
                # Fallback: show tickers with placeholder when Finviz returns no data
                data = [{"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"} for t in wl_data]
            return build_watchlist_table(data, "watchlist", "change", False), data
        except Exception as e:
            logger.exception("Watchlist fetch failed: %s", e)
            return _err_div(e), []

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
            Output("qulla-data-store", "data"),
            Output("minervini-content", "children"),
            Output("minervini-data-store", "data"),
            Output("oneil-content", "children"),
            Output("oneil-data-store", "data"),
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
            qulla_table = build_qullamaggie_table(qulla_data, "qulla", "change", False)
            minervini_data = minervini_screener()
            minervini_table = build_minervini_table(minervini_data, "minervini", "change", False)
            oneil_data = oneil_screener()
            oneil_table = build_oneil_table(oneil_data, "oneil", "change", False)
            return [qulla_table, qulla_data, minervini_table, minervini_data, oneil_table, oneil_data]
        except Exception as e:
            logger.exception("Group B failed: %s", e)
            return [_err_div(e), [], _disabled_msg, [], _disabled_msg, []]

    @app.callback(
        [
            Output("sector-content", "children"),
            Output("sector-data-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_c(n_intervals, n_clicks):
        try:
            sector_data = compute_sector_data()
            return build_sector_table(sector_data, "sector", "chg", False), sector_data
        except Exception as e:
            logger.exception("Sector data failed: %s", e)
            return _err_div(e), []

    @app.callback(
        [
            Output("stockbee-content", "children"),
            Output("stockbee-data-store", "data"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        State("stockbee-sort-store", "data"),
        prevent_initial_call=False,
    )
    def refresh_stockbee(n_intervals, n_clicks, sort_state):
        try:
            from src.stockbee import fetch_stockbee_momentum50
            from src.data_fetcher import fetch_tickers_bulk_csv
            mom = fetch_stockbee_momentum50()
            dates = mom.get("dates", [])
            tickers = mom.get("tickers", {})
            if not dates or not tickers:
                return html.Div("No Momentum50 data. Check Stockbee sheet.", style={
                    "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                }), {}
            latest_date = dates[0]
            ticker_list = tickers.get(latest_date, [])
            if not ticker_list:
                return html.Div("No tickers for latest date.", style={
                    "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
                }), {}
            cache_key = f"momentum50_quotes_{','.join(sorted(t.strip().upper() for t in ticker_list))}"
            data = fetch_tickers_bulk_csv(ticker_list, cache_key=cache_key)
            if not data:
                data = [{"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"} for t in ticker_list]
            else:
                by_ticker = {r["ticker"]: r for r in data}
                data = [by_ticker.get(t.upper(), {"ticker": t, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"}) for t in ticker_list]
            col = (sort_state or {}).get("col") if sort_state else None
            asc = (sort_state or {}).get("asc", True) if sort_state else True
            return build_stockbee_momentum50_table(data, date_label=latest_date, widget_id="stockbee", sort_col=col, sort_asc=asc), {"data": data, "date_label": latest_date}
        except Exception as e:
            logger.exception("Stockbee Momentum50 failed: %s", e)
            return _err_div(e), []

    @app.callback(
        Output("breadth-content", "children"),
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_breadth(n_intervals, n_clicks):
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
        ],
        prevent_initial_call=False,
    )
    def refresh_breadth_charts(n_intervals, n_clicks):
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
            graph_cfg = {"displayModeBar": False}
            return [
                dcc.Graph(figure=fig1, config=graph_cfg, style={"height": "100%", "width": "100%"}),
                dcc.Graph(figure=fig2, config=graph_cfg, style={"height": "100%", "width": "100%"}),
                dcc.Graph(figure=fig3, config=graph_cfg, style={"height": "100%", "width": "100%"}),
                dcc.Graph(figure=fig4, config=graph_cfg, style={"height": "100%", "width": "100%"}),
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
        ],
        prevent_initial_call=False,
    )
    def refresh_rrg(n_intervals, n_clicks):
        try:
            rrg_data = compute_rrg_data()
            fig = build_rrg_chart(rrg_data)
            graph = dcc.Graph(
                id="rrg-graph",
                figure=fig,
                config={"displayModeBar": False},
                style={"height": "100%", "width": "100%"},
            )
            return fig.to_dict(), graph
        except Exception as e:
            logger.exception("RRG failed: %s", e)
            return None, _err_div(e)

    @app.callback(
        Output("rrg-graph", "figure"),
        Input("rrg-graph", "hoverData"),
        State("rrg-figure-store", "data"),
        prevent_initial_call=True,
    )
    def rrg_hover_dim(hover_data, store_data):
        import copy
        if not store_data:
            return no_update
        # When not hovering (hoverData clears when mouse leaves), restore original
        points = hover_data.get("points") if hover_data else None
        if not points:
            return copy.deepcopy(store_data)
        hovered_idx = points[0].get("curveNumber")
        from src.layout import _hex_to_rgba
        fig = copy.deepcopy(store_data)
        traces = fig.get("data", [])
        if not traces:
            return no_update
        dim_alpha = 0.18
        for i, tr in enumerate(traces):
            color = tr.get("line", {}).get("color", tr.get("marker", {}).get("color", "#888"))
            full = color
            dimmed = _hex_to_rgba(color, dim_alpha) if isinstance(color, str) and color.startswith("#") else f"rgba(136,136,136,{dim_alpha})"
            if hovered_idx is not None and i != hovered_idx:
                if "line" in tr:
                    tr.setdefault("line", {})["color"] = dimmed
                if "marker" in tr:
                    tr.setdefault("marker", {})["opacity"] = dim_alpha
                    tr["marker"]["color"] = dimmed
            else:
                if "line" in tr:
                    tr.setdefault("line", {})["color"] = full
                if "marker" in tr:
                    tr.setdefault("marker", {})["opacity"] = 1.0
                    tr["marker"]["color"] = full
        return fig

    @app.callback(
        [
            Output("club97-content", "children"),
            Output("club97-data-store", "data"),
            Output("movers-content", "children"),
            Output("movers-data-store", "data"),
            Output("weekly-content", "children"),
            Output("weekly-data-store", "data"),
            Output("daily-content", "children"),
            Output("daily-data-store", "data"),
            Output("earnings-content", "children"),
            Output("earnings-data-store", "data"),
            Output("in_play-content", "children"),
            Output("in_play-data-store", "data"),
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
            club97_table = build_97_club_table(club97_data, "club97", "change", False)
            movers_data = compute_9m_movers([])
            movers_table = build_9m_movers_table(movers_data, "movers", "change", False)
            weekly_data = compute_20pct_weekly([])
            weekly_table = build_20pct_weekly_table(weekly_data, "weekly", "week", False)
            daily_data = compute_4pct_daily([])
            daily_table = build_4pct_daily_table(daily_data, "daily", "chg", False)
            earnings_data = compute_earnings_yesterday_today([])
            earnings_table = build_earnings_table(earnings_data, "earnings", "change", False)
            in_play_data = compute_stocks_in_play([])
            in_play_table = build_stocks_in_play_table(in_play_data, "in_play", "change", False)
            return [
                club97_table, club97_data, movers_table, movers_data,
                weekly_table, weekly_data, daily_table, daily_data,
                earnings_table, earnings_data,
                in_play_table, in_play_data,
            ]
        except Exception as e:
            logger.exception("Group D failed: %s", e)
            return [_err_div(e), [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, [], _disabled_msg, []]

    @app.callback(
        [
            Output("leading-content", "children"),
            Output("leading-data-store", "data"),
            Output("stage-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_e(n_intervals, n_clicks):
        try:
            leading_data = compute_leading_industries([], {})
            leading_table = build_leading_industries_table(leading_data, "leading", "top_both", False)
            stage_result = compute_stage_analysis([])
            counts = stage_result.get("counts", {})
            stage_chart = build_stage_chart(counts)
            stage_summary = build_stage_summary(counts)
            stage_content = html.Div([
                stage_summary,
                dcc.Graph(
                    figure=stage_chart,
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                ),
            ], style=CHART_WRAP_STYLE)
            return [leading_table, leading_data, stage_content]
        except Exception as e:
            logger.exception("Group E (Leading/Stage) failed: %s", e)
            return [_err_div(e), [], _disabled_msg]

    # ------------------------------------------------------------------
    # Sortable table: header click -> re-sort and re-render
    # ------------------------------------------------------------------
    SORTABLE_WIDGETS = {
        "qulla": (build_qullamaggie_table, "qulla-content", {}),
        "minervini": (build_minervini_table, "minervini-content", {}),
        "oneil": (build_oneil_table, "oneil-content", {}),
        "watchlist": (build_watchlist_table, "watchlist-content", {}),
        "sector": (build_sector_table, "sector-content", {}),
        "club97": (build_97_club_table, "club97-content", {}),
        "movers": (build_9m_movers_table, "movers-content", {}),
        "weekly": (build_20pct_weekly_table, "weekly-content", {}),
        "daily": (build_4pct_daily_table, "daily-content", {}),
        "earnings": (build_earnings_table, "earnings-content", {}),
        "in_play": (build_stocks_in_play_table, "in_play-content", {}),
        "leading": (build_leading_industries_table, "leading-content", {}),
        "stockbee": (build_stockbee_momentum50_table, "stockbee-content", {}),
    }

    @app.callback(
        [Output(f"{w}-content", "children", allow_duplicate=True) for w in SORTABLE_WIDGETS] +
        [Output(f"{w}-sort-store", "data", allow_duplicate=True) for w in SORTABLE_WIDGETS],
        Input({"type": "sort-header", "widget": ALL, "column": ALL}, "n_clicks"),
        [State(f"{w}-data-store", "data") for w in SORTABLE_WIDGETS] +
        [State(f"{w}-sort-store", "data") for w in SORTABLE_WIDGETS],
        prevent_initial_call=True,
    )
    def sort_table(n_clicks_list, *stores):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            return [no_update] * len(SORTABLE_WIDGETS) * 2
        wid = ctx.triggered_id.get("widget")
        col = ctx.triggered_id.get("column")
        if not wid or wid not in SORTABLE_WIDGETS or not col:
            return [no_update] * len(SORTABLE_WIDGETS) * 2
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
        else:
            builder, _, _ = SORTABLE_WIDGETS[wid]
            table = builder(data, wid, col, new_asc)
        out_content = [no_update] * len(SORTABLE_WIDGETS)
        out_sort = [no_update] * len(SORTABLE_WIDGETS)
        out_content[data_idx] = table
        out_sort[data_idx] = new_sort
        return out_content + out_sort
