# Market Metrics Dashboard v2 — Complete Specification

Based on Steve Jacobs' (@SteveDJacobs) daily trading dashboard with ALL 14 sections.
Reference image: /home/user/workspace/image.jpg

## CRITICAL: This dashboard is SPREADSHEET-DENSE
The original dashboard looks like a dense financial spreadsheet, NOT a modern dashboard with cards.
Every section is a compact table with colored cells. The layout is tightly packed.
Think Bloomberg Terminal / Excel spreadsheet, NOT a modern SaaS dashboard.

## Layout Overview (from reference image)
The dashboard is a SINGLE SCREEN with no scrolling, maximum density:

```
+--TOP ROW-------------------------------------------------------+
| [1] Key Metrics Table  | [2] QQQE+RSP    | [3] Composite+$1B  |
|   (left ~30%)          |   Barchart       |   Barchart          |
|                        |   (center ~35%)  |   (right ~35%)      |
+--MIDDLE ROWS (right side of top row)---------------------------+
|                        | [4] Qullamaggie  | [5] Minervini       |
|                        |   Screener       |   Screener          |
|                        | [6] O'Neil       | [7] Watchlist       |
|                        |   Screener       |                     |
+-SECTOR ROW----------------------------------------------------|
| [8] Sector SPDR ETFs (full width table)                       |
+--BOTTOM 4-COLUMN ROW-----------------------------------------+
| [9] 97 Club  | [10] 9M Movers | [11] 20% Weekly | [12] 4% Daily|
|              |                |                  |   Gainers     |
+-BOTTOM WIDE ROW-----------------------------------------------|
| [13] Leading Industries              | [14] Stage Analysis    |
+---------------------------------------------------------------+
```

## Section Details

### 1. KEY METRICS TABLE (Top Left)
A grid/table with these EXACT rows and columns:

**Columns**: Metric | NASDAQ (QQQE) Above/Below/Pct | S&P500 (RSP) Above/Below/Pct | RSP+QQQE+DIA Above/Below/Pct | 1B+ UNIVERSE Above/Below/Pct

**Rows**:
- Day Chg (# up vs down, ratio)
- Open Chg
- Week
- Month
- Qtr
- Half Year
- Year
- Price to SMA10
- Price to SMA20
- Price to SMA50
- Price to SMA200
- EMA10>SMA20
- SMA20>SMA50
- SMA50>SMA200
- SMA20>SMA50>SMA200
- 4% Up vs 4% Down
- New 20-Day High's
- New 20-Day Low's (inverse)
- Price-to 20 Day Range
- Stocks (count: 101, 503, 516, 2486)

Color coding: Green cells = bullish (>50% above), Red cells = bearish (<50%), darker shades for more extreme

### 2. QQQE + RSP Barchart (Top Center)
Stacked horizontal bar chart showing:
- S&P500 Down | Nasdaq Down | Nasdaq Up | S&P500 Up
- Rows: DAY CHG, OPEN CHG, WEEK, MONTH, QTR, HALF YEAR, YEAR, PRICE TO SMA10/20/50/200, EMA10>SMA20, SMA20>SMA50, SMA50>SMA200, TREND DAYS, etc.
- Dark green/red = QQQE (Nasdaq), Light green/red = RSP (S&P500)

### 3. Composite + $1B Barchart (Top Right)
Same format as #2 but for the Composite Index and $1B+ universe.

### 4. Qullamaggie Inspired Screener (Right side)
A compact table of stock tickers meeting Qullamaggie breakout criteria:
- Columns: Ticker
- Color coded cells (green = strong, yellow = moderate)
- Show as a grid of ticker pills/cells

### 5. Minervini Inspired Screener
Minervini Trend Template stocks:
- Price > 50-day, 150-day, 200-day SMA
- 150-day SMA > 200-day SMA  
- 200-day SMA trending up 1+ month
- Price within 25% of 52-week high
- RS rating > 70
- Compact ticker grid like #4

### 6. O'Neil Inspired Screener
William O'Neil / CANSLIM methodology stocks:
- Similar compact ticker grid

### 7. Watchlist
Personal watchlist with ticker grid, color coded

### 8. SECTOR SPDR ETFs (Full Width Table)
A detailed table with these columns:
Sector | Ticker | Gap | Chg | O Chg | Week | Month | Qtr | H.Year | Year | 20-Day | Trend Days | Last | EMA10 | SMA20 | SMA200 | 52 WEEK | DISC | ATR % | ATR Chg | ATR $ | ATR RS | ATR Ext | ATR Ext $ | SATR Ext | STOP LOSS | SMA50 | ENTRY | HOLD | -20% | -20% | -20% | -20% | Return | Reward

Rows (11 sectors + 2 reference):
- Technology (XLK)
- Healthcare (XLV)
- Communication Services (XLC)
- Consumer Cyclical (XLY)
- Utilities (XLU)
- Industrials (XLI)
- Energy (XLE)
- Real Estate (XLRE)
- Financial (XLF)
- Basic Materials (XLB)
- Consumer Defensive (XLP)
- S&P Equal Weight (RSP)
- Nasdaq100 Equal Weight (QQQE)

Sorted by ATR Extension. Color coded cells throughout.

### 9. The "97 Club" (Bottom Left)
Table of $1B+ stocks in top 3% relative strength across Day, Week, Month.
Columns: Industry | Ticker | Stage | ATR % | ATR Ext % | R-R
- ~35 stocks
- Pale blue ticker = True Market Leader (TML)
- Color coded by stage (2A green, 2B yellow, 2C orange, etc.)

### 10. Stockbee 9 Million Movers (Bottom Center-Left)
Stocks trading above average volume with 9M+ shares.
Columns: Industry | Ticker | Vol. | Rel Vol | Chg | Stage | ATR % | ATR Ext | R-R
- ~37 stocks

### 11. Stockbee 20% Weekly Movers (Bottom Center-Right)
Stocks that increased/decreased 20% within 5 sessions.
Columns: Industry | Ticker | Week | Stage | ATR % | ATR Ext | R-R
- ~17 stocks

### 12. Stockbee 4% Daily Gainers (Bottom Right)
Stocks up 4%+ in current session.
Columns: Industry | Ticker | Chg | Stage | ATR % | Min Rel Vol | 1.00
- ~37 stocks  

### 13. Leading Industries (Bottom Left Wide)
Top 20% (30 of 149) industry groups by weekly/monthly strength.
Columns: Industry | Ticker(s) showing top 4 performers
- Green highlight = top 20% on both weekly AND monthly basis
- Shows: 1st, 2nd, 3rd, 4th best tickers per industry

### 14. Stage Analysis Summary (Bottom Right)
Bar chart + table showing breakdown of $1B+ stocks by stage:
- Stage 1 | Stage 2 (2A, 2B, 2C) | Stage 3 | Stage 4
- Bullish vs Bearish indicator
- Count per stage
- Visual bar chart

## Color Coding System
- Dark Green: Strong bullish (>70% above metric)
- Light Green: Moderate bullish (55-70%)
- Yellow/Neutral: ~50%
- Light Red: Moderate bearish (30-45%)
- Dark Red: Strong bearish (<30%)
- Pale Blue: True Market Leader (TML) designation
- Stage colors: 1=gray, 2A=green, 2B=yellow, 2C=orange, 3=red, 4=dark red

## Technical Notes
- Font: Small, monospace-like for data density (11-12px)
- ZERO wasted space — every pixel shows data
- Tables have tight cell padding (2-4px)
- Background: Dark theme (#0a0e17 base)
- This should look like a professional trading terminal, not a consumer app
