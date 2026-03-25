"""Market Metrics Dashboard — Plotly Dash entry point."""

import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env before any imports that use env vars (e.g. FinViz Elite)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from dash import Dash

from src.layout import build_layout
from src.callbacks import register_callbacks
from src.constants import COLORS
from src import cache

# Preload cache from disk so widgets show instantly on restart
cache.warm_from_disk()


def _warm_macro_history_cache_bg() -> None:
    """Warm Macro Monitor history cache in background without delaying startup."""
    try:
        from src.macro_data import warm_macro_series_cache
        warm_macro_series_cache()
    except Exception:
        pass


threading.Thread(target=_warm_macro_history_cache_bg, daemon=True).start()

# Console: warnings and errors only (no DEBUG/INFO noise from app or libraries)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for _log_name in (
    "urllib3",
    "urllib3.connectionpool",
    "requests",
    "yfinance",
    "werkzeug",
    "dash",
    "dash_renderer",
):
    logging.getLogger(_log_name).setLevel(logging.WARNING)

app = Dash(
    __name__,
    title="Pradly Portal",
    update_title="Loading...",
    suppress_callback_exceptions=True,
    serve_locally=True,  # Offline use: serve Plotly.js from local package
)

app.index_string = f"""<!DOCTYPE html>
<html>
<head>
    {{%metas%}}
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>{{%title%}}</title>
    {{%favicon%}}
    {{%css%}}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{
            height: 100%;
            background: {COLORS['bg']};
            color: {COLORS['text']};
            font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
            font-size: 11px;
            line-height: 1.3;
            font-variant-numeric: tabular-nums lining-nums;
            -webkit-font-smoothing: antialiased;
        }}
        ::-webkit-scrollbar {{ width: 12px; height: 12px; }}
        ::-webkit-scrollbar-track {{ background: {COLORS['surface2']}; border-radius: 6px; }}
        ::-webkit-scrollbar-thumb {{ background: {COLORS['text_muted']}; border-radius: 6px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: {COLORS['text']}; }}
        #react-entry-point {{ height: 100%; }}
        ._dash-loading {{ display: none !important; }}

        .tv-ticker {{
            cursor: pointer;
            transition: opacity 0.15s;
        }}
        .tv-ticker:hover {{
            opacity: 0.75;
            text-decoration: underline;
        }}

        /* Should I Trade? — Bloomberg terminal style */
        #should-i-trade-content .sit-mono {{
            font-family: 'JetBrains Mono', 'Consolas', monospace;
        }}

        /* Ticker tape marquee — scroll right to left (duplicate content = seamless loop) */
        #should-i-trade-content .sit-ticker-marquee,
        .sit-ticker-marquee {{
            overflow: hidden;
            white-space: nowrap;
            width: 100%;
            min-width: 0;
        }}
        #should-i-trade-content .sit-ticker-marquee-inner,
        .sit-ticker-marquee-inner {{
            display: inline-flex;
            flex-shrink: 0;
            width: max-content;
            will-change: transform;
            animation: sit-marquee 40s linear infinite;
        }}
        @keyframes sit-marquee {{
            0% {{ transform: translate3d(0, 0, 0); }}
            100% {{ transform: translate3d(-50%, 0, 0); }}
        }}
        /* Slow the scroll instead of killing it — many OSes report "reduce motion" broadly */
        @media (prefers-reduced-motion: reduce) {{
            #should-i-trade-content .sit-ticker-marquee-inner,
            .sit-ticker-marquee-inner {{
                animation-duration: 90s !important;
            }}
        }}

        /* Dropdown dark theme — easier on eyes */
        :root {{
            --Dash-Fill-Inverse-Strong: {COLORS['surface2']};
            --Dash-Stroke-Strong: {COLORS['border']};
            --Dash-Fill-Interactive-Strong: {COLORS['accent']};
            --Dash-Text-Strong: {COLORS['text']};
            --Dash-Text-Weak: {COLORS['text_muted']};
            --Dash-Text-Disabled: {COLORS['text_faint']};
            --Dash-Fill-Interactive-Weak: rgba(6, 182, 212, 0.15);
            --Dash-Fill-Disabled: {COLORS['border']};
            --Dash-Shading-Strong: rgba(0, 0, 0, 0.5);
            --Dash-Shading-Weak: rgba(0, 0, 0, 0.2);
            --Dash-Spacing: 4px;
        }}
        .dash-dropdown,
        .dash-dropdown-content,
        .dash-dropdown-search-container {{
            background: {COLORS['surface2']} !important;
            border-color: {COLORS['border_light']} !important;
            color: {COLORS['text']} !important;
        }}
        .dash-dropdown:focus,
        .dash-dropdown-search-container:focus-within {{
            border-color: {COLORS['accent']} !important;
            outline-color: {COLORS['accent']} !important;
        }}
        .dash-dropdown-placeholder {{
            color: {COLORS['text_faint']} !important;
        }}
        .dash-dropdown-option:hover {{
            background: rgba(6, 182, 212, 0.12) !important;
        }}
        .dash-dropdown-value-count {{
            background: rgba(6, 182, 212, 0.2) !important;
            color: {COLORS['text_muted']} !important;
        }}

        /* TradingView modal — metrics panel (Finviz-style grid) */
        .tv-modal-body {{
            align-items: stretch;
        }}
        @media (max-width: 900px) {{
            .tv-modal-body {{
                flex-direction: column !important;
            }}
            .tv-metrics-panel {{
                flex: 1 1 auto !important;
                max-width: none !important;
                min-width: 0 !important;
                border-left: none !important;
                border-top: 1px solid {COLORS['border']} !important;
                max-height: 42vh;
            }}
            .tv-modal-chart-wrap {{
                flex: 1 1 50% !important;
                min-height: 200px;
            }}
        }}
        .tv-metrics-body-inner {{
            font-size: 11px;
            line-height: 1.4;
            padding: 8px 8px 6px;
            color: {COLORS['text']};
            box-sizing: border-box;
        }}
        .tv-metrics-loading, .tv-metrics-err, .tv-metrics-empty {{
            padding: 12px;
            font-size: 11px;
            color: {COLORS['text_muted']};
        }}
        .tv-metrics-err {{ color: {COLORS['red_light']}; }}
        .tv-metrics-source {{
            flex-shrink: 0;
            font-size: 9px;
            color: {COLORS['accent']};
            margin-bottom: 6px;
            padding-bottom: 6px;
            border-bottom: 1px solid {COLORS['border']};
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .tv-metrics-fit-wrap {{
            flex: 1 1 0;
            min-height: 0;
            overflow-x: hidden;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
            padding-right: 10px;
            box-sizing: border-box;
        }}
        .tv-metrics-fit-wrap::-webkit-scrollbar {{ width: 10px; }}
        .tv-metrics-fit-wrap::-webkit-scrollbar-track {{ background: {COLORS['surface']}; border-radius: 4px; }}
        .tv-metrics-fit-wrap::-webkit-scrollbar-thumb {{ background: {COLORS['border_light']}; border-radius: 4px; }}
        .tv-metrics-scale-inner {{
            box-sizing: border-box;
            width: 100%;
            max-width: 100%;
            overflow-x: hidden;
        }}
        .tv-metrics-grid {{
            display: flex;
            flex-direction: row;
            flex-wrap: nowrap;
            align-items: flex-start;
            gap: 0;
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
        }}
        .tv-metrics-col {{
            flex: 1 1 0;
            min-width: 0;
            box-sizing: border-box;
            border-right: 1px solid {COLORS['border']};
            padding: 0 4px 0 0;
        }}
        .tv-metrics-col:last-child {{ border-right: none; padding-right: 0; }}
        .tv-metrics-row {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            column-gap: 4px;
            align-items: start;
            padding: 2px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .tv-metrics-lbl {{
            color: {COLORS['text_muted']};
            font-size: 10.5px;
            line-height: 1.3;
            min-width: 0;
            word-break: normal;
            overflow-wrap: break-word;
            hyphens: none;
        }}
        .tv-metrics-lbl-line {{
            display: inline;
            white-space: normal;
            word-break: normal;
        }}
        .tv-metrics-lbl-sub {{
            color: {COLORS['text_faint']};
            font-size: 9.5px;
            font-weight: 500;
        }}
        .tv-metrics-val {{
            color: {COLORS['text']};
            font-size: 10.5px;
            line-height: 1.3;
            text-align: right;
            font-variant-numeric: tabular-nums lining-nums;
            min-width: 0;
            overflow-wrap: break-word;
            word-break: normal;
            hyphens: none;
        }}
        .tv-metrics-val.tv-pos {{ color: {COLORS['green_light']}; }}
        .tv-metrics-val.tv-neg {{ color: {COLORS['red_light']}; }}
        a.tv-metrics-val.tv-metrics-link {{
            color: {COLORS['accent']};
            text-decoration: underline;
            text-underline-offset: 2px;
            white-space: nowrap;
        }}
        a.tv-metrics-val.tv-metrics-link:hover {{
            color: {COLORS['text']};
        }}
    </style>
</head>
<body>
    {{%app_entry%}}
    <footer>
        {{%config%}}
        {{%scripts%}}
        {{%renderer%}}
    </footer>
    <script>
        var tvMetricsAbort = null;

        function tvMetricsEscapeHtml(s) {{
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }}

        function tvMetricsEscapeAttr(s) {{
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        function tvMetricsToneValue(label, value) {{
            if (!value || value === '\\u2014' || value === '-') return 'neu';
            var m = String(value).replace(/,/g, '').trim().match(/^([+-]?\\d+\\.?\\d*)\\s*%?$/);
            if (m) {{
                var n = parseFloat(m[1]);
                if (n > 0) return 'pos';
                if (n < 0) return 'neg';
            }}
            return 'neu';
        }}

        function tvMetricsSafeHref(val) {{
            var s = String(val).trim();
            if (/^https?:\\/\\//i.test(s)) return s;
            return null;
        }}

        function tvMetricsIsNewsUrlLabel(label) {{
            return String(label).trim().toLowerCase() === 'news url';
        }}

        /** Split labels at parentheses or Perf … so words are not broken mid-word by CSS. */
        function tvMetricsFormatLabelHtml(label) {{
            var s = String(label).trim();
            var mParen = s.match(/^(.+?)\\s*(\\([^)]+\\))\\s*$/);
            if (mParen && mParen[1].length >= 1) {{
                var head = mParen[1].trim();
                var tail = mParen[2].trim();
                return '<span class="tv-metrics-lbl-line">' + tvMetricsEscapeHtml(head) + '</span><br>'
                    + '<span class="tv-metrics-lbl-line tv-metrics-lbl-sub">' + tvMetricsEscapeHtml(tail) + '</span>';
            }}
            var mPerf = s.match(/^Perf\\s+(.+)$/i);
            if (mPerf) {{
                var rest = mPerf[1].trim();
                return '<span class="tv-metrics-lbl-line">Performance</span><br>'
                    + '<span class="tv-metrics-lbl-line tv-metrics-lbl-sub">(' + tvMetricsEscapeHtml(rest) + ')</span>';
            }}
            var mInsider = s.match(/^Insider\\s+(.+)$/i);
            if (mInsider) {{
                var ir = mInsider[1].trim();
                return '<span class="tv-metrics-lbl-line">Insider</span><br>'
                    + '<span class="tv-metrics-lbl-line tv-metrics-lbl-sub">(' + tvMetricsEscapeHtml(ir) + ')</span>';
            }}
            var mInst = s.match(/^Inst\\s+(.+)$/i);
            if (mInst) {{
                var it = mInst[1].trim();
                return '<span class="tv-metrics-lbl-line">Institutional</span><br>'
                    + '<span class="tv-metrics-lbl-line tv-metrics-lbl-sub">(' + tvMetricsEscapeHtml(it) + ')</span>';
            }}
            return '<span class="tv-metrics-lbl-line">' + tvMetricsEscapeHtml(s) + '</span>';
        }}

        function tvMetricsRenderValueCell(label, value, tone) {{
            var cls = 'tv-metrics-val';
            if (tone === 'pos') cls += ' tv-pos';
            else if (tone === 'neg') cls += ' tv-neg';
            var href = tvMetricsIsNewsUrlLabel(label) ? tvMetricsSafeHref(value) : null;
            if (href) {{
                return '<a class="' + cls + ' tv-metrics-link" href="' + tvMetricsEscapeAttr(href)
                    + '" target="_blank" rel="noopener noreferrer" title="' + tvMetricsEscapeAttr(value)
                    + '" onclick="event.stopPropagation()">Article</a>';
            }}
            return '<span class="' + cls + '" title="' + tvMetricsEscapeAttr(value) + '">'
                + tvMetricsEscapeHtml(value) + '</span>';
        }}

        function tvMetricsRenderPairs(pairs) {{
            if (!pairs || !pairs.length)
                return '<div class="tv-metrics-empty">No metrics.</div>';
            var cols = 6;
            var n = pairs.length;
            var perCol = Math.ceil(n / cols);
            var html = '<div class="tv-metrics-grid">';
            for (var c = 0; c < cols; c++) {{
                html += '<div class="tv-metrics-col">';
                for (var i = c * perCol; i < Math.min((c + 1) * perCol, n); i++) {{
                    var p = pairs[i];
                    var tone = tvMetricsToneValue(p.label, p.value);
                    html += '<div class="tv-metrics-row"><span class="tv-metrics-lbl" title="'
                        + tvMetricsEscapeAttr(p.label)
                        + '">'
                        + tvMetricsFormatLabelHtml(p.label)
                        + '</span>'
                        + tvMetricsRenderValueCell(p.label, p.value, tone)
                        + '</div>';
                }}
                html += '</div>';
            }}
            html += '</div>';
            return html;
        }}

        function tvModalClose() {{
            if (tvMetricsAbort) {{
                try {{ tvMetricsAbort.abort(); }} catch (e) {{}}
                tvMetricsAbort = null;
            }}
            var modal = document.getElementById('tv-modal');
            var iframe = document.getElementById('tv-iframe');
            var panel = document.getElementById('tv-metrics-body');
            if (modal) modal.style.display = 'none';
            if (iframe) iframe.src = '';
            if (panel) panel.innerHTML = '';
        }}

        document.addEventListener('click', function(e) {{
            var el = e.target.closest('.tv-ticker');
            if (!el) return;

            var symbol = el.textContent.trim();
            if (!symbol || symbol === 'x') return;

            var modal = document.getElementById('tv-modal');
            var iframe = document.getElementById('tv-iframe');
            var title = document.getElementById('tv-modal-title');
            var panel = document.getElementById('tv-metrics-body');
            if (!modal || !iframe) return;

            e.preventDefault();
            e.stopPropagation();

            if (tvMetricsAbort) {{
                try {{ tvMetricsAbort.abort(); }} catch (err) {{}}
            }}
            tvMetricsAbort = new AbortController();

            title.textContent = symbol + ' \\u2014 TradingView';
            iframe.src = 'https://s.tradingview.com/widgetembed/?frameElementId=tv-widget'
                + '&symbol=' + encodeURIComponent(symbol)
                + '&interval=D&hidesidetoolbar=0&symboledit=1&saveimage=1'
                + '&toolbarbg=f1f3f6&studies=MASimple%409%2CRSI%40RSI'
                + '&theme=dark&style=1&timezone=America%2FNew_York'
                + '&withdateranges=1&showpopupbutton=1&locale=en';

            if (panel)
                panel.innerHTML = '<div class="tv-metrics-loading">Loading\\u2026</div>';

            fetch('/api/ticker-metrics/' + encodeURIComponent(symbol), {{
                signal: tvMetricsAbort.signal,
            }})
                .then(function (resp) {{
                    return resp.json().then(function (data) {{
                        return {{ okHttp: resp.ok, status: resp.status, data: data }};
                    }});
                }})
                .then(function (result) {{
                    var p = document.getElementById('tv-metrics-body');
                    if (!p) return;
                    if (tvMetricsAbort && tvMetricsAbort.signal.aborted) return;
                    var d = result.data;
                    if (!d || !d.ok) {{
                        var msg = (d && d.message) ? d.message : 'No data for this symbol.';
                        p.innerHTML = '<div class="tv-metrics-err">' + tvMetricsEscapeHtml(msg) + '</div>';
                        return;
                    }}
                    var src = d.source || '';
                    var meta = src === 'quote'
                        ? '<div class="tv-metrics-source">Quote snapshot (not in USA export)</div>'
                        : '';
                    p.innerHTML = meta
                        + '<div class="tv-metrics-fit-wrap"><div class="tv-metrics-scale-inner">'
                        + tvMetricsRenderPairs(d.pairs || [])
                        + '</div></div>';
                }})
                .catch(function (err) {{
                    if (err.name === 'AbortError') return;
                    var p = document.getElementById('tv-metrics-body');
                    if (p)
                        p.innerHTML = '<div class="tv-metrics-err">Failed to load metrics.</div>';
                }});

            modal.style.display = 'flex';
            modal.style.position = 'fixed';
            modal.style.top = '0';
            modal.style.left = '0';
            modal.style.right = '0';
            modal.style.bottom = '0';
            modal.style.zIndex = '99999';
            modal.style.justifyContent = 'center';
            modal.style.alignItems = 'center';
        }}, true);

        document.addEventListener('click', function(e) {{
            var modal = document.getElementById('tv-modal');
            if (!modal) return;
            if (e.target === modal) tvModalClose();
        }});

        document.addEventListener('click', function(e) {{
            var btn = e.target.closest('#btn-tv-close');
            if (btn) tvModalClose();
        }});

        /* Inject dropdown dark theme after Dash components load (overrides async-loaded CSS) */
        function injectDropdownDarkTheme() {{
            var id = 'dropdown-dark-override';
            if (document.getElementById(id)) return;
            var s = document.createElement('style');
            s.id = id;
            s.textContent = `
                button.dash-dropdown, .dash-dropdown-trigger {{
                    background: {COLORS['surface2']} !important;
                    border: 1px solid {COLORS['border_light']} !important;
                    color: {COLORS['text']} !important;
                }}
                button.dash-dropdown:hover, .dash-dropdown-trigger:hover {{
                    background: {COLORS['surface3']} !important;
                }}
                button.dash-dropdown:focus, .dash-dropdown-trigger:focus {{
                    border-color: {COLORS['accent']} !important;
                    outline: 1px solid {COLORS['accent']} !important;
                }}
                .dash-dropdown-content, [data-radix-popper-content-wrapper] {{
                    background: {COLORS['surface2']} !important;
                    border: 1px solid {COLORS['border_light']} !important;
                    color: {COLORS['text']} !important;
                }}
                .dash-dropdown-placeholder {{ color: {COLORS['text_faint']} !important; }}
                .dash-dropdown-value, .dash-dropdown-value-item, .dash-dropdown-option {{ color: {COLORS['text']} !important; }}
                .dash-dropdown-option:hover {{ background: rgba(6,182,212,0.15) !important; }}
                .dash-dropdown-search-container, .dash-dropdown-search {{
                    background: {COLORS['surface2']} !important;
                    border-color: {COLORS['border_light']} !important;
                    color: {COLORS['text']} !important;
                }}
                .dash-dropdown-value-count {{ background: rgba(6,182,212,0.2) !important; color: {COLORS['text_muted']} !important; }}
                .dash-dropdown-trigger-icon {{ color: {COLORS['text_muted']} !important; fill: {COLORS['text_muted']} !important; }}
            `;
            document.head.appendChild(s);
        }}
        injectDropdownDarkTheme();
        setTimeout(injectDropdownDarkTheme, 500);
        setTimeout(injectDropdownDarkTheme, 2000);
    </script>
</body>
</html>"""

app.layout = build_layout()
register_callbacks(app)


@app.server.route("/api/ticker-metrics/<symbol>")
def _api_ticker_metrics(symbol: str):
    from flask import jsonify

    from src.ticker_metrics import get_ticker_metrics_payload, is_valid_symbol_param

    if not is_valid_symbol_param(symbol):
        return jsonify({"ok": False, "message": "Invalid symbol.", "pairs": []}), 400

    payload = get_ticker_metrics_payload(symbol)
    if payload.get("ok"):
        return jsonify(payload)

    msg = (payload.get("message") or "").lower()
    if "not configured" in msg or "finviz elite" in msg:
        return jsonify(payload), 503
    return jsonify(payload), 404


@app.server.after_request
def _disable_browser_cache(response):
    """Prevent browser from caching app responses. Skip Dash/Plotly static assets so they load reliably."""
    try:
        from flask import request
        path = request.path
    except Exception:
        path = ""
    # Let Dash component suites (plotly.js, etc.) use default caching so they load within timeout
    if "/_dash-component-suites/" in path or (path or "").startswith("/assets/"):
        return response
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8050))
    app.run(
        debug=True,
        host="127.0.0.1",
        port=port,
        dev_tools_ui=True,  # Show Dev Tools panel in app (bottom-right) for callback errors
        dev_tools_props_check=False,  # Avoid noisy prop validation errors
    )
