"""FRED series IDs and display config for Macro Monitor — single source of truth."""

from __future__ import annotations

from typing import Any, Literal

Transform = Literal[
    "level",
    "yoy_pct_index",  # monthly index -> YoY %
    "pct_level",  # already a rate in %
    "diff_1m_thousands",  # PAYEMS month-over-month in thousands
    "range_pair",  # fed target lower + upper
    "price_index",  # e.g. SP500 level
]

SOURCE_TAG = Literal["FRED", "BLS via FRED", "EIA via FRED", "Univ. of Mich. via FRED", "Treasury via FRED"]

# metric_id -> config
METRICS: dict[str, dict[str, Any]] = {
    "fed_funds": {
        "label": "Fed Funds",
        "short": "Fed",
        "fred_ids": ("DFEDTARL", "DFEDTARU", "DFF"),
        "transform": "range_pair",
        "freq": "d",
        "source": "FRED",
    },
    "cpi_yoy": {
        "label": "CPI",
        "short": "CPI",
        "fred_ids": ("CPIAUCSL",),
        "transform": "yoy_pct_index",
        "freq": "m",
        "source": "BLS via FRED",
        "unit_suffix": "% YoY",
    },
    "core_cpi_yoy": {
        "label": "Core CPI",
        "short": "Core CPI",
        "fred_ids": ("CPILFESL",),
        "transform": "yoy_pct_index",
        "freq": "m",
        "source": "BLS via FRED",
        "unit_suffix": "% YoY",
    },
    "ppi_yoy": {
        "label": "PPI",
        "short": "PPI",
        "fred_ids": ("PPIACO",),
        "transform": "yoy_pct_index",
        "freq": "m",
        "source": "BLS via FRED",
        "unit_suffix": "% YoY",
    },
    "pce_yoy": {
        "label": "PCE",
        "short": "PCE",
        "fred_ids": ("PCEPI",),
        "transform": "yoy_pct_index",
        "freq": "m",
        "source": "BEA via FRED",
        "unit_suffix": "% YoY",
    },
    "core_pce_yoy": {
        "label": "Core PCE",
        "short": "Core PCE",
        "fred_ids": ("PCEPILFE",),
        "transform": "yoy_pct_index",
        "freq": "m",
        "source": "BEA via FRED",
        "unit_suffix": "% YoY",
    },
    "unemployment": {
        "label": "Unemployment",
        "short": "Unemp.",
        "fred_ids": ("UNRATE",),
        "transform": "pct_level",
        "freq": "m",
        "source": "BLS via FRED",
        "unit_suffix": "%",
    },
    "nfp": {
        "label": "NFP (m/m)",
        "short": "NFP",
        "fred_ids": ("PAYEMS",),
        "transform": "diff_1m_thousands",
        "freq": "m",
        "source": "BLS via FRED",
        "unit_suffix": "K",
    },
    "brent": {
        "label": "Brent Crude",
        "short": "Brent",
        "fred_ids": ("DCOILBRENTEU",),
        "transform": "level",
        "freq": "d",
        "source": "EIA via FRED",
        "unit_prefix": "$",
    },
    "sp500": {
        "label": "S&P 500",
        "short": "S&P 500",
        "fred_ids": ("SP500",),
        "transform": "price_index",
        "freq": "d",
        "source": "FRED",
    },
    "sentiment": {
        "label": "Sentiment",
        "short": "Sent.",
        "fred_ids": ("UMCSENT",),
        "transform": "pct_level",
        "freq": "m",
        "source": "Univ. of Mich. via FRED",
    },
    "deficit": {
        "label": "Deficit",
        "short": "Deficit",
        "fred_ids": ("FYFSDF",),
        "transform": "level",
        "freq": "a",
        "source": "Treasury via FRED",
        "unit_prefix": "$",
    },
}

# usd_unit: FRED units for dollar series — "millions" (GFDEBTN, FYFSDF), "billions" (FGRECPT, FGEXPND)
FISCAL_ROWS: list[dict[str, Any]] = [
    {"id": "total_debt", "label": "Total federal debt", "fred_id": "GFDEBTN", "usd_unit": "millions"},
    {"id": "deficit_fy", "label": "Surplus/deficit (FY)", "fred_id": "FYFSDF", "usd_unit": "millions"},
    {"id": "debt_gdp", "label": "Gross debt / GDP", "fred_id": "GFDEGDQ188S", "usd_unit": "percent"},
    {"id": "receipts", "label": "Federal receipts", "fred_id": "FGRECPT", "usd_unit": "billions"},
    {"id": "outlays", "label": "Federal expenditures", "fred_id": "FGEXPND", "usd_unit": "billions"},
    {"id": "net_interest", "label": "Net interest (FY)", "fred_id": "FYOINT", "usd_unit": "millions"},
]

# KPI strip order
KPI_ORDER: list[str] = [
    "fed_funds",
    "cpi_yoy",
    "core_cpi_yoy",
    "ppi_yoy",
    "pce_yoy",
    "core_pce_yoy",
    "unemployment",
    "nfp",
    "brent",
    "sp500",
    "sentiment",
    "deficit",
]
