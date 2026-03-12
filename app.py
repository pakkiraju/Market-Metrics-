"""Market Metrics Dashboard — Plotly Dash entry point."""

import logging
import sys
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = Dash(
    __name__,
    title="Pradly Portal",
    update_title="Loading...",
    suppress_callback_exceptions=True,
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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
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
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: {COLORS['border_light']}; border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: {COLORS['text_faint']}; }}
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
    </script>
</body>
</html>"""

app.layout = build_layout()
register_callbacks(app)


@app.server.after_request
def _disable_browser_cache(response):
    """Prevent browser from caching any responses."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8050))
    app.run(debug=True, host="127.0.0.1", port=port)
