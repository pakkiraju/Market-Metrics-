"""FinViz Elite API authentication and requests.

Supports:
- FINVIZ_API_KEY: Official API key (header-based)
- FINVIZ_EMAIL + FINVIZ_PASSWORD: Cookie-based auth (legacy)

When credentials are set, requests use elite.finviz.com for real-time data.
"""

import os
import logging
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

ELITE_BASE = "https://elite.finviz.com"
FREE_BASE = "https://finviz.com"
LOGIN_URL = "https://finviz.com/login_submit.ashx"


def _load_env():
    """Load .env file if python-dotenv available."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass


def get_api_key() -> str | None:
    """Return FINVIZ_API_KEY if set."""
    _load_env()
    key = os.environ.get("FINVIZ_API_KEY", "").strip()
    return key or None


def get_auth_headers() -> dict | None:
    """
    Return auth headers for Elite API.
    Tries API key first, then cookie from email/password login.
    """
    _load_env()

    # 1. API key
    api_key = get_api_key()
    if api_key:
        return {"X-API-Key": api_key}
        # Some APIs use: {"Authorization": f"Bearer {api_key}"}

    # 2. Cookie-based (email + password)
    email = os.environ.get("FINVIZ_EMAIL", "").strip()
    password = os.environ.get("FINVIZ_PASSWORD", "").strip()
    if not email or not password:
        return None

    try:
        resp = requests.post(
            LOGIN_URL,
            data={"email": email, "password": password},
            allow_redirects=True,
            timeout=15,
        )
        for h in resp.history:
            if h.cookies:
                for c in h.cookies:
                    if c.name == ".ASPXAUTH":
                        return {"Cookie": f"{c.name}={c.value}"}
    except Exception as e:
        logger.warning("FinViz Elite login failed: %s", e)
    return None


def is_elite_configured() -> bool:
    """True if any Elite credential is set."""
    _load_env()
    if os.environ.get("FINVIZ_API_KEY", "").strip():
        return True
    if os.environ.get("FINVIZ_EMAIL", "").strip() and os.environ.get("FINVIZ_PASSWORD", "").strip():
        return True
    return False


TABLE_CODES = {"Overview": "111", "Valuation": "121", "Performance": "141", "Technical": "171"}


def _parse_elite_table(resp_text: str) -> tuple[list[str], list[dict]]:
    """Parse Elite screener HTML. Returns (headers, rows)."""
    try:
        from lxml import html as lxml_html
        tree = lxml_html.fromstring(resp_text)
    except Exception:
        return [], []

    header_rows = tree.cssselect('tr[valign="middle"]')
    if not header_rows:
        return [], []
    header_el = header_rows[0].cssselect("th") or header_rows[0].xpath("td")
    headers = [el.text_content().strip() for el in header_el if el.text_content().strip()]

    data = []
    for row in tree.cssselect('tr[valign="top"]'):
        cells = row.xpath("td//text()")
        if len(cells) >= len(headers):
            data.append(dict(zip(headers, cells[: len(headers)])))
        elif len(cells) == len(headers):
            data.append(dict(zip(headers, cells)))
    return headers, data


def _get_total_rows(tree) -> int:
    """Extract total row count from page (e.g. '#1 / 500 Total')."""
    try:
        from lxml import etree
        text = etree.tostring(tree, encoding="unicode", method="html")
        for beg, end in [('class="count-text whitespace-nowrap">#1 / ', ' Total '),
                         ('class="count-text">#1 / ', ' Total ')]:
            if beg in text:
                parts = text.split(beg)[1].split(end)[0]
                return int(parts)
    except Exception:
        pass
    return 0


def fetch_elite_screener(filters: list[str], table: str = "Overview",
                         order: str = "-change", rows: int | None = None) -> list[dict]:
    """
    Fetch screener data from Elite (real-time). Returns list of dicts like Screener.data.
    Paginates to get all rows when rows is None.
    """
    headers = get_auth_headers()
    if not headers:
        return []

    table_code = TABLE_CODES.get(table, table) if isinstance(table, str) else table
    base_params = {
        "v": table_code,
        "f": ",".join(filters) if filters else "",
        "o": order,
    }
    req_headers = {**headers, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    all_data = []
    page = 1
    total_rows = None

    while True:
        params = {**base_params, "r": 1 + (page - 1) * 20}
        try:
            resp = requests.get(
                f"{ELITE_BASE}/screener.ashx",
                params=params,
                headers=req_headers,
                timeout=30,
                verify=False,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Elite screener fetch failed: %s", e)
            break

        try:
            from lxml import html as lxml_html
            tree = lxml_html.fromstring(resp.text)
        except Exception as e:
            logger.warning("Elite screener parse failed: %s", e)
            break

        _, page_data = _parse_elite_table(resp.text)
        if not page_data:
            break
        all_data.extend(page_data)

        if total_rows is None:
            total_rows = _get_total_rows(tree)
        if rows and len(all_data) >= rows:
            break
        if total_rows and len(all_data) >= total_rows:
            break
        if len(page_data) < 20:
            break
        page += 1

    return all_data
