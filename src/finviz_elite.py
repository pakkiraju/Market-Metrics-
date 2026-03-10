"""FinViz Elite API authentication and requests.

Uses export.ashx with auth query param per FinViz API docs:
  url = "https://elite.finviz.com/export.ashx?[filters]&auth=YOUR_API_KEY"

- FINVIZ_API_KEY: Passed as auth= query param to export.ashx
- FINVIZ_EMAIL + FINVIZ_PASSWORD: Cookie-based fallback for screener.ashx
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


def get_auth_params() -> dict:
    """Return auth query params for Elite API. Per FinViz docs: auth=API_KEY."""
    api_key = get_api_key()
    if api_key:
        return {"auth": api_key}
    return {}


def get_auth_headers() -> dict | None:
    """Return auth headers (cookie) for screener.ashx when no API key. Legacy."""
    _load_env()
    if get_api_key():
        return {}  # API key uses query param, no header needed
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


def fetch_elite_stock(ticker: str) -> dict | None:
    """
    Fetch single-ticker data from Elite quote.ashx.
    Returns dict with Price, Change, Perf Week, etc. (same keys as finviz get_stock) or None.
    """
    auth_params = get_auth_params()
    headers = get_auth_headers()
    if not auth_params and not headers:
        return None

    params = {"t": ticker, **auth_params}
    req_headers = {**headers, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(
            f"{ELITE_BASE}/quote.ashx",
            params=params,
            headers=req_headers,
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Elite quote.ashx %s failed: %s", ticker, e)
        return None

    if "login" in resp.url.lower() or "sign in" in resp.text[:2000].lower():
        logger.warning("Elite quote returned login page - check FINVIZ_API_KEY")
        return None

    try:
        from lxml import html as lxml_html
        tree = lxml_html.fromstring(resp.text)
    except Exception as e:
        logger.warning("Elite quote parse failed for %s: %s", ticker, e)
        return None

    data = {"Ticker": ticker}
    all_rows = tree.cssselect("tr.table-dark-row")
    for row in all_rows:
        cells = row.cssselect("td.snapshot-td2")
        for i in range(0, len(cells) - 1, 2):
            label = cells[i].text_content().strip()
            value = cells[i + 1].text_content().strip()
            if not label:
                continue
            if label == "EPS next Y" and "EPS next Y" in data:
                data["EPS growth next Y"] = value
                continue
            if label == "Volatility":
                vols = value.split()
                if len(vols) >= 2:
                    data["Volatility (Week)"] = vols[0]
                    data["Volatility (Month)"] = vols[1]
                else:
                    data["Volatility (Week)"] = vols[0] if vols else ""
                    data["Volatility (Month)"] = data["Volatility (Week)"]
                continue
            data[label] = value

    if len(data) <= 1:
        all_rows_old = [row.xpath("td//text()") for row in tree.cssselect("tr.table-dark-row")]
        for row in all_rows_old:
            for col in range(0, min(11, len(row) - 1)):
                if col % 2 == 0:
                    data[row[col]] = row[col + 1]

    return data if len(data) > 1 else None


def fetch_elite_by_url(url: str) -> list[dict]:
    """Fetch screener data by exact URL. Adds auth= query param when FINVIZ_API_KEY is set."""
    auth_params = get_auth_params()
    headers = get_auth_headers()
    if not auth_params and not headers:
        return []

    # Append auth to URL when using API key
    base_url = url
    if auth_params:
        sep = "&" if "?" in url else "?"
        base_url = f"{url}{sep}auth={auth_params['auth']}"

    req_headers = {**headers, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    all_data = []
    page = 0

    while True:
        page_url = f"{base_url}&r={1 + page * 20}" if page > 0 else base_url
        try:
            resp = requests.get(page_url, headers=req_headers, timeout=30, verify=False)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Elite fetch by URL failed: %s", e)
            break

        if "login" in resp.url.lower() or "sign in" in resp.text[:2000].lower():
            logger.warning("Elite returned login page - check FINVIZ_API_KEY or use FINVIZ_EMAIL+FINVIZ_PASSWORD")
            break

        _, page_data = _parse_elite_table(resp.text)
        if not page_data:
            break
        all_data.extend(page_data)
        if len(page_data) < 20:
            break
        page += 1

    return all_data


def _fetch_elite_csv(filters: list[str], table: str, order: str) -> list[dict]:
    """Fetch Elite screener data via export.ashx (CSV). Uses auth= query param per FinViz API docs."""
    auth_params = get_auth_params()
    if not auth_params:
        return []

    table_code = TABLE_CODES.get(table, table) if isinstance(table, str) else table
    params = {
        "v": table_code,
        "f": ",".join(filters) if filters else "",
        "o": order,
        "ft": "3",  # filter type for tad_* (technical) filters
        **auth_params,
    }
    req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(
            f"{ELITE_BASE}/export.ashx",
            params=params,
            headers=req_headers,
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Elite export.ashx failed: %s", e)
        return []

    # If we got HTML (login page) instead of CSV, fall through to screener
    if resp.text.strip().startswith("<"):
        logger.debug("Elite export.ashx returned HTML (login?), trying screener.ashx")
        return []

    import csv
    import io
    try:
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        # Normalize column names (CSV may use "Ticker" or "ticker")
        if rows and "ticker" in rows[0] and "Ticker" not in rows[0]:
            for r in rows:
                r["Ticker"] = r.get("ticker", "")
        return rows
    except Exception as e:
        logger.warning("Elite export.ashx parse failed: %s", e)
        return []


def fetch_elite_screener(filters: list[str], table: str = "Overview",
                         order: str = "-change", rows: int | None = None) -> list[dict]:
    """
    Fetch screener data from Elite (real-time). Returns list of dicts like Screener.data.
    Uses export.ashx with auth= query param when FINVIZ_API_KEY is set.
    Falls back to HTML screener.ashx only when using cookie auth (no API key).
    """
    auth_params = get_auth_params()
    headers = get_auth_headers()
    if not auth_params and not headers:
        logger.debug("Elite: no auth configured (FINVIZ_API_KEY or FINVIZ_EMAIL+PASSWORD)")
        return []

    table_code = TABLE_CODES.get(table, table) if isinstance(table, str) else table
    base_params = {
        "v": table_code,
        "f": ",".join(filters) if filters else "",
        "o": order,
        "ft": "3",  # filter type for tad_* (technical) filters
        **auth_params,
    }
    req_headers = {**headers, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # 1. Try export.ashx first (CSV, uses auth= query param)
    csv_data = _fetch_elite_csv(filters, table, order)
    if csv_data:
        if rows:
            return csv_data[:rows]
        return csv_data

    # 2. Fall back to HTML screener (cookie auth or auth param)
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

        # Check for login redirect (auth failed)
        if "login" in resp.url.lower() or "sign in" in resp.text[:2000].lower():
            logger.warning("Elite screener returned login page - API key may not work for HTML; try FINVIZ_EMAIL+FINVIZ_PASSWORD")
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
