# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed

- **Key Metrics (FinViz):** Uses a single Elite **export.ashx** request for the full **v=152** custom column set (`FINVIZ_USA_FULL_V152_EXPORT`, no `geo_usa` filter), cached as `usa_full_v152`. NQ100, SPY500, DJIA, RUS2000, and **$1B+** are derived in-app by filtering that dataset (Index / cap / volume / price rules), replacing many per-group and per-metric export calls.
- **Key Metrics refresh:** Invalidating Key Metrics also clears the `usa_full_v152` cache so the next run fetches fresh bulk data.
- **`fetch_export_from_url`:** Accepts an optional `timeout` (seconds); the USA-wide export uses a longer timeout for large CSV responses.

### Added

- **`FINVIZ_USA_FULL_V152_SCREENER`:** Same query string as the export URL but **`screener.ashx`** for opening in a browser to cross-check columns and filters against the downloaded CSV.
- **`FINVIZ_USA_FULL_V152_EXPORT` / `_USA_FULL_V152_QUERY`:** Shared query parameters between export (app) and screener (human) URLs.

### Notes

- **New 20-Day Highs / Lows:** Counts come from 20-day high/low columns in the bulk CSV when present. If either column is missing, the app falls back to **export.ashx** row counts for those two rows only (same FinViz filters as before). Table **links** to FinViz screeners are unchanged for manual verification.
