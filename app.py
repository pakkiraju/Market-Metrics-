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
        document.addEventListener('click', function(e) {{
            var el = e.target.closest('.tv-ticker');
            if (!el) return;

            var symbol = el.textContent.trim();
            if (!symbol || symbol === 'x') return;

            var modal = document.getElementById('tv-modal');
            var iframe = document.getElementById('tv-iframe');
            var title = document.getElementById('tv-modal-title');
            if (!modal || !iframe) return;

            e.preventDefault();
            e.stopPropagation();

            title.textContent = symbol + ' \u2014 TradingView';
            iframe.src = 'https://s.tradingview.com/widgetembed/?frameElementId=tv-widget'
                + '&symbol=' + encodeURIComponent(symbol)
                + '&interval=D&hidesidetoolbar=0&symboledit=1&saveimage=1'
                + '&toolbarbg=f1f3f6&studies=MASimple%409%2CRSI%40RSI'
                + '&theme=dark&style=1&timezone=America%2FNew_York'
                + '&withdateranges=1&showpopupbutton=1&locale=en';

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
            if (e.target === modal) {{
                modal.style.display = 'none';
                var iframe = document.getElementById('tv-iframe');
                if (iframe) iframe.src = '';
            }}
        }});

        document.addEventListener('click', function(e) {{
            var btn = e.target.closest('#btn-tv-close');
            if (btn) {{
                var modal = document.getElementById('tv-modal');
                if (modal) modal.style.display = 'none';
                var iframe = document.getElementById('tv-iframe');
                if (iframe) iframe.src = '';
            }}
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
