"""Scrape CNBC Market Insider for latest premarket report.

Fetches https://www.cnbc.com/market-insider/, finds the most recent premarket
article, and extracts stocks with their news headlines.
"""

import html as html_module
import logging
import re
from urllib.parse import urljoin

import requests
from lxml import html

from src import cache
from src.cache import MEDIUM

logger = logging.getLogger(__name__)

CNBC_MARKET_INSIDER = "https://www.cnbc.com/market-insider/"

# Company name (or substring) -> ticker mapping for CNBC articles
COMPANY_TO_TICKER = {
    "bumble": "BMBL",
    "hims": "HIMS",
    "hims & hers": "HIMS",
    "blue owl": "OWL",
    "blue owl capital": "OWL",
    "blackstone": "BX",
    "apollo": "APO",
    "apollo global": "APO",
    "netskope": "NTSK",
    "firefly aerospace": "FLY",
    "firefly": "FLY",
    "petco": "WOOF",
    "petco health": "WOOF",
    "atlassian": "TEAM",
    "dick's sporting": "DKS",
    "dicks sporting": "DKS",
    "dollar general": "DG",
    "uipath": "PATH",
    "adobe": "ADBE",
    "ulta": "ULTA",
    "ulta beauty": "ULTA",
    "lennar": "LEN",
    "lucid": "LCID",
    "cf industries": "CF",
    "oracle": "ORCL",
    "nebius": "NBIS",
    "campbell": "CPB",
    "campbell's": "CPB",
    "serve robotics": "SERV",
    "nike": "NKE",
    "carmax": "KMX",
    "aerovironment": "AVAV",
    "rivian": "RIVN",
    "biotech": "BNTX",
    "biontech": "BNTX",
    "kohl": "KSS",
    "casey's": "CASY",
    "chevron": "CVX",
    "xenon": "XENE",
    "vertiv": "VRT",
    "live nation": "LYV",
    "marvell": "MRVL",
    "blackrock": "BLK",
    "united airlines": "UAL",
    "costco": "COST",
    "gap": "GPS",
    "samsara": "IOT",
    "broadcom": "AVGO",
    "okta": "OKTA",
    "stubhub": "STUB",
    "coinbase": "COIN",
    "coreweave": "CRWV",
    "kkr": "KKR",
    "moderna": "MRNA",
    "target": "TGT",
    "best buy": "BBY",
    "on holding": "ONON",
    "mongodb": "MDB",
    "exxon": "XOM",
    "lockheed": "LMT",
    "block": "SQ",
    "dell": "DELL",
    "netflix": "NFLX",
    "nvidia": "NVDA",
    "salesforce": "CRM",
    "intuit": "INTU",
    "zscaler": "ZS",
    "workday": "WDAY",
    "cava": "CAVA",
    "plug power": "PLUG",
}


def _find_premarket_link(page_url: str) -> str | None:
    """Fetch market-insider page and return URL of latest premarket article."""
    try:
        r = requests.get(page_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        r.raise_for_status()
        tree = html.fromstring(r.content)
        # Find all links
        for a in tree.xpath("//a[@href]"):
            href = a.get("href") or ""
            text = (a.text or "").strip().lower()
            if "premarket" in href.lower() or "pre-market" in href.lower():
                if "stocks-making" in href or "stocks making" in text:
                    full_url = urljoin(page_url, href)
                    if full_url.startswith("https://www.cnbc.com/") and ".html" in full_url:
                        return full_url
    except Exception as e:
        logger.warning("Failed to fetch CNBC market-insider: %s", e)
    return None


def _extract_tickers_from_url(article_url: str) -> list[str]:
    """Extract ticker symbols from CNBC article URL slug (e.g. premarket-bmbl-hims-owl-ntsk)."""
    match = re.search(r"premarket-([a-z0-9-]+)\.html", article_url.lower())
    if not match:
        return []
    slug = match.group(1)
    # Slug is like "bmbl-hims-owl-ntsk" - tickers are 2-5 chars typically
    parts = slug.split("-")
    tickers = []
    for p in parts:
        if len(p) >= 2 and len(p) <= 5 and p.isalpha():
            tickers.append(p.upper())
    return tickers


def _company_to_ticker(company_name: str) -> str | None:
    """Map company name (from article) to ticker."""
    name = company_name.strip().lower()
    for key, ticker in COMPANY_TO_TICKER.items():
        if key in name:
            return ticker
    return None


def _parse_article_sections(body_text: str) -> list[tuple[str, str]]:
    """Split article body into (company_name, news_text) pairs.
    CNBC uses em dash (—), en dash (–), or hyphen (-) to separate company from news."""
    if not body_text or not body_text.strip():
        return []
    # Normalize dashes to em dash (CNBC may use —, –, -, or replacement char)
    text = body_text.replace("\u2013", "\u2014").replace(" - ", " \u2014 ")
    text = text.replace("\ufffd", "\u2014")
    text = re.sub(r"\s+[—–\-]\s+", " \u2014 ", text)
    # Match "  X  " where X is any single char (handles replacement char, etc.)
    text = re.sub(r"\s{2,}.\s{2,}", " \u2014 ", text)
    parts = re.split(r"\s+\u2014\s+", text)
    result = []
    for i, p in enumerate(parts):
        p = p.strip()
        if not p or len(p) < 10:
            continue
        # Skip intro
        if i == 0 and ("check out" in p.lower() or "headlines" in p.lower() or "before the bell" in p.lower()):
            continue
        # Skip contributor line
        if "cnbc's" in p.lower() and "contributed" in p.lower():
            continue
        # Company: first phrase if short and matches; else last known company at end of part
        first_phrase = p.split(".")[0].strip()[:50]
        company = first_phrase if _company_to_ticker(first_phrase) else None
        if not company:
            for key in sorted(COMPANY_TO_TICKER.keys(), key=len, reverse=True):
                if p.strip().endswith(key.title()) or key in p.lower()[-80:]:
                    idx = p.lower().rfind(key)
                    if idx > 100:  # company at end, not in middle
                        company = p[idx:].strip()
                        p = p[:idx].strip()
                    break
        if not company:
            company = first_phrase
        if company and p and len(p) > 30:
            result.append((company, p))
    return result


def _find_tickers_in_text(text: str) -> list[str]:
    """Find all company tickers mentioned in text (company + news)."""
    text_lower = text.lower()
    found = []
    for key, ticker in COMPANY_TO_TICKER.items():
        if key in text_lower and ticker not in found:
            found.append(ticker)
    return found


def _match_sections_to_tickers(
    sections: list[tuple[str, str]], url_tickers: list[str]
) -> list[dict]:
    """Match parsed sections to tickers. Returns list of {ticker, company, news}."""
    rows = []
    seen = set()
    url_ticker_queue = list(url_tickers)

    for company, news in sections:
        # Prefer company name -> ticker match first
        ticker = _company_to_ticker(company)
        if ticker:
            tickers_in_section = [ticker]
        else:
            # For sections with multiple companies (e.g. "Private credit stocks – Blue Owl, Blackstone, Apollo")
            # use only company + start of news to avoid matching next section's company names
            tickers_in_section = _find_tickers_in_text(company + " " + news[:150])
        if not tickers_in_section and url_ticker_queue:
            tickers_in_section = [url_ticker_queue.pop(0)]
        for ticker in tickers_in_section:
            key = (ticker, company[:50])
            if key in seen:
                continue
            seen.add(key)
            news_clean = html_module.unescape(news[:600] + ("..." if len(news) > 600 else ""))
            rows.append({
                "ticker": ticker,
                "company": company[:80],
                "news": news_clean,
            })
    # Deduplicate by ticker (keep first)
    seen_tickers = set()
    deduped = []
    for r in rows:
        if r["ticker"] not in seen_tickers:
            seen_tickers.add(r["ticker"])
            deduped.append(r)
    return deduped


def fetch_cnbc_premarket_watchlist(ttl: int = MEDIUM) -> list[dict]:
    """Scrape CNBC Market Insider for latest premarket report.
    Returns list of {ticker, company, news, url}."""
    cached = cache.get("cnbc_premarket_watchlist")
    if cached is not None:
        return cached

    try:
        article_url = _find_premarket_link(CNBC_MARKET_INSIDER)
        if not article_url:
            logger.warning("No premarket article found on CNBC Market Insider")
            return []

        r = requests.get(article_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        r.raise_for_status()
        tree = html.fromstring(r.content)

        # Extract main article body - CNBC may use JS-rendered content, so fallback to raw HTML
        body_els = tree.xpath(
            "//article//p | //div[contains(@class,'ArticleBody')]//p | "
            "//div[contains(@class,'group-body')]//p | "
            "//div[@data-module='ArticleBody']//p"
        )
        body_text = " ".join(
            (el.text_content() or "").strip() for el in body_els if el.text_content()
        )
        if not body_text or len(body_text) < 200:
            # Fallback: extract from raw HTML (content may be in page but not in parsed tree)
            raw = r.text
            start = raw.find("Check out the companies making headlines before the bell.")
            if start == -1:
                start = raw.find("Check out the companies")
            if start >= 0:
                end = raw.find("CNBC's", start)
                if end == -1:
                    end = start + 8000
                body_text = raw[start:end]
            # Decode common HTML entities
            body_text = body_text.replace("&amp;", "&").replace("&#39;", "'")

        url_tickers = _extract_tickers_from_url(article_url)
        sections = _parse_article_sections(body_text)
        rows = _match_sections_to_tickers(sections, url_tickers)

        # Parse article date from URL (e.g. /2026/03/12/...)
        article_date = ""
        date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", article_url)
        if date_match:
            y, m, d = date_match.group(1), date_match.group(2), date_match.group(3)
            from datetime import datetime
            try:
                dt = datetime(int(y), int(m), int(d))
                article_date = dt.strftime("%b %d, %Y")
            except (ValueError, TypeError):
                article_date = f"{y}-{m}-{d}"

        for r in rows:
            r["url"] = article_url
            r["article_date"] = article_date

        if rows:
            cache.put("cnbc_premarket_watchlist", rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("CNBC premarket scrape failed: %s", e)
        return []
