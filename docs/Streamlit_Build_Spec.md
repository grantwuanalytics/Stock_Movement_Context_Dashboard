# Stock Movement Context Dashboard — Phase 2 Build Specification

## 1. Vision and decision
An investor-relations analyst at a large investment firm needs to explain unusual
stock movements before speaking with investors. Today, for each move, the analyst
finds the wide day on a separate price chart, then searches a news site and the
SEC filing site for that date one company at a time; with the dashboard, they pick
a stock, see its unusually wide days ranked, and open one day to see that week's
news summaries and the filing in effect on that day side by side.
The analyst decides which movements and disclosures deserve further human review.
The tool supplies historical context, not causal conclusions, forecasts, or
trading advice.

Changes from Phase 1: a period selector (full range by default, with year options)
and an eight-stock overview were added. The selector replaces year tabs because
2024 is December only (21 trading days), too short to stand alone as a tab. The
threshold is fixed for the MVP (Phase 1's adjustable threshold was removed).

| User selects | Dashboard shows | User decides |
|---|---|---|
| Period (default: full range) | Eight-stock relative price chart and summary table | Which stock deserves investigation |
| Stock | Closing-price chart and ranked flagged days | Which event to review |
| Flagged day | Day metrics, eight-stock same-date comparison, nearby news, latest filing | Which potential explanations to investigate |
| News or filing section | Stored news summaries and MD&A/risk text with quality labels | Which evidence to verify or discuss |

## 2. Data contract
Use the committed canonical files in `data/cleaned/` exactly as they are. **Never
download, re-clean, or regenerate data**, and never use the `sample/` CSVs as data.
This dataset is the team-adopted cleaning (`docs/team_reconciliation.md`; rules in
`docs/cleaning_decision_log.md`).

| Table (rows) | Grain and key | Columns |
|---|---|---|
| `prices` (2,656) | Company × trading day; `symbol` + `date` | id, symbol, date, open, high, low, close, adj_close, volume, daily_range_pct |
| `news` (3,888) | Company × calendar day; `symbol` + `date` | id, symbol, date, highlights, highlights_low_info |
| `filings` (73) | One 10-K/10-Q; `symbol` + `date` + `document_type` | id, symbol, date, document_type, mda_content, risk_content, risk_refers_to_10k |
| `price_context` (2,656) | Company × trading day; `symbol` + `date` | price_id, symbol, date, high, low, close, daily_range_pct, is_flagged, co_flag_count, news_id, highlights_low_info, filing_id, filing_date, document_type, risk_refers_to_10k, filed_same_day, latest_10k_id, latest_10k_date |

`date` columns are datetimes at day grain; `filings.date` is the filing date, not
the fiscal period end. Tickers, in this order for tables and controls: AAPL Apple,
ADBE Adobe, AMZN Amazon, GOOGL Alphabet, META Meta, MSFT Microsoft, NVDA Nvidia,
TSLA Tesla. Price coverage is 2024-12-02 to 2026-03-31 (332 trading days per
company): 2024 is December only, 2025 is complete, 2026 is January–March.

**Flag rule (fixed for the MVP):** a day is flagged when `daily_range_pct =
(high − low) / close` is at or above that company's 95th percentile over the full
range. It is computed once in cleaning and stored as `is_flagged`: 17 flagged days
per company, 136 in total. The dashboard never recomputes thresholds, per period
or otherwise. `co_flag_count` is the number of the eight companies flagged that date.

**Quality labels:** "Limited information" when `highlights_low_info` is true (news
summary under 300 characters); "refers to 10-K" when `risk_refers_to_10k` is true
(10-Q risk section under 2,000 characters that points to the annual report).

## 3. Starting view and state
Title: **Stock Movement Context Dashboard**. Subtitle: "Compare eight stocks,
identify unusually wide daily ranges, and review related news and company filings."

Layout, top to bottom: (1) period selector, (2) coverage banner, (3) eight-stock
relative price chart, (4) eight-stock summary table, (5) stock selector and detail
chart, (6) flagged-day table, (7) selected-day metrics and eight-stock comparison,
(8) news and filing panels.

| State | Default | On change |
|---|---|---|
| Period | Full range | Keep the stock; select its largest flagged day in the new period |
| Stock | AAPL | Select its largest flagged day in the current period |
| Selected day | Largest `daily_range_pct` among the stock's flagged days in the period; ties → earliest date | Set by choosing one row in the flagged-day table |

Opening view: full range, AAPL, selected day 2025-04-09 (range 14.44%, 8 of 8
stocks flagged). If the stock has no flags in the period, selected day is None:
show "No flagged trading days for this stock in the selected period.", keep the
detail chart, and hide panels 7–8. Example: AAPL, ADBE and NVDA in 2024; NVDA and
TSLA in 2026. The flagged-day table is the only way to select a day; there is no
chart-point selection in the MVP.

## 4. Period overview
**Period selector:** options "Full range" (default), 2024, 2025, 2026.
**Coverage banner:** the period's first and last trading dates, company count,
trading dates, and `coverage_label` (from `year_coverage`).

**Relative price chart:** date on x; adjusted close indexed to 100 on the first
trading day of the selected period, per company; eight lines with a legend and a
reference line at 100. Title: "Relative price performance — first trading day of
period = 100". Hover: ticker, date, indexed price, change since the period's first
day. Legend toggles affect only this chart. Use one consistent color per ticker
in every view, with ticker names in the legend and hover.

**Summary table:** one row per ticker, default order as in §2, sortable:
company, ticker, last close, change over period, flagged days, largest daily
range, trading days. A missing value shows "Unavailable", never 0.

## 5. Stock and flagged-day details
**Stock selector:** "Select a stock to investigate"; options "Apple (AAPL)" etc.
It does not filter the overview.

**Detail chart:** date on x, unadjusted close (USD) on y, line for the selected
stock, distinct markers on flagged days. Hover: ticker, date, close, high, low,
daily range, flag, co-flag count. No interpolated or invented rows.

**Flagged-day table:** the selected stock's flagged days in the period: date,
close, high, low, daily range, co-flag count; sorted by range descending, then
date ascending; single-row selection.

**Selected-day metrics:** company and ticker, date, close, high, low, daily range,
and "X of 8 stocks flagged". Below it, all eight tickers' daily range and flag
status on that date (missing shows "Unavailable"). Caption: "A higher count may
suggest shared conditions; it does not establish a market-wide cause."

## 6. News and filing context
**News:** the selected stock's summaries dated D−7 through D (calendar days,
inclusive, up to eight; weekends and earlier periods included), newest first. The
selected day's summary is expanded; others are collapsed. Each shows its date,
"AI-generated news summary", and "Limited information" when applicable. If none:
"No news summaries are available for this company in the selected date window."

**Filing:** the selected stock's latest 10-K or 10-Q with filing date ≤ D (may be
from an earlier period). Show document type and filing date; if filed on D, add
"Filed on selected date; publication time unavailable." MD&A and Risk Factors
each show the first ~2,000 characters, with an expander for the rest. If the
filing is a 10-Q labelled "refers to 10-K", also show the latest 10-K's risk text
(same display rule), labelled with its filing date. If no filing exists: "No
eligible 10-K or 10-Q filing is available for this company as of the selected
date." Filing text is excerpted from the filings, not the complete documents.

Render all stored news and filing text as plain text so `$` amounts display
literally (Markdown would treat text between two `$` as math).

## 7. Metrics
Backend ratios are decimals; the interface formats them once as percentages with
two decimals (0.05 → 5.00%). Dates display as YYYY-MM-DD, dollars with two
decimals, counts as integers.

| Metric — question answered | Source and calculation | Scope |
|---|---|---|
| Relative price — how did stocks move against each other? | `adj_close / first adj_close in period × 100` | Each ticker, selected period |
| Change over period — how much did each stock move? | `last adj_close / first adj_close − 1` | Each ticker, selected period |
| Last close — latest quoted price | Last `close` in period | Each ticker, selected period |
| Daily range — how wide was the day's swing? | `daily_range_pct = (high − low) / close` | One company, one day |
| Flag — was the swing unusual for this company? | Stored `is_flagged` (§2) | One company, one day |
| Flagged days / largest range / trading days | Count of `is_flagged`; max `daily_range_pct`; count of price rows | Each ticker, selected period |
| Co-flags — did many stocks swing together? | Stored `co_flag_count` | All eight stocks on a date; never filtered |
| News window | Same symbol, `D − 7 ≤ date ≤ D` | Any period |
| Filing context | Latest filing with `date ≤ D`, same symbol | Any period |

Period changes use adjusted prices at both ends; the last close is the unadjusted
quote. Daily range measures the intraday swing, not direction or a close-to-close
return. Percentile thresholds use the whole sample, so they are retrospective,
not real-time signals.

## 8. Architecture and backend contracts
Each module has one job; analysis functions are pure: they never modify inputs,
read UI state, use the network, or keep mutable globals. Unsupported periods or
tickers raise `ValueError`.

| Module | Job | Output |
|---|---|---|
| `constants.py` | Ticker list (`COMPANIES`), `YEARS`, `PERIODS = ('full', 2024, 2025, 2026)` | Constants |
| `cleaning.py` | Agreed cleaning, fixed flags, joins (already run; do not rerun) | Canonical Parquet files |
| `data_loader.py` | Load and validate the four canonical files | Dict of DataFrames |
| `analysis.py` | Filtering, aggregation and context lookup | Values and DataFrames below |
| `phase2.py` | Validate, then export all backend tables | `outputs/analysis/` (git-ignored) |
| `charts.py`, `app.py` (Phase 3) | Plotly figures; Streamlit controls, state, layout | Interface |

The validator recomputes the stored news and filing links by calling
`cleaning.build_price_context`, so it checks that the stored data matches the
cleaning logic, not that the logic itself is right (the tests cover that).
`cleaning.py` keeps its own copy of the ticker set so it can run as a standalone
script; a test checks it equals `constants.COMPANIES`.

`period` is `'full'` or a year from `YEARS`; `date` is any date-like value.

| Function | Returns |
|---|---|
| `load_cleaned(directory='data/cleaned')` | dict: `prices`, `news`, `filings`, `price_context` (DataFrames); raises `FileNotFoundError` / `ValueError` if missing or invalid |
| `validate_data(data)` | dict: `rows` (dict of row counts), `flagged_days` (int), `validated` (True) |
| `year_coverage(prices, period)` | dict: `period`, `start_date`, `end_date` (Timestamps), `companies`, `trading_dates` (ints), `coverage_label` (str) |
| `year_summary(prices, context, period)` | DataFrame, 8 rows: symbol, company, trading_days, last_close, period_change, flagged_days, largest_daily_range, start_date, end_date |
| `indexed_prices(prices, period)` | DataFrame: symbol, date, adj_close, indexed_price, period_change |
| `stock_series(context, period, symbol)` | DataFrame: all 18 `price_context` columns, date ascending |
| `flagged_days(context, period, symbol)` | Same columns, flagged rows only, range descending then date ascending |
| `initial_date(context, period, symbol='AAPL')` | Timestamp of the first `flagged_days` row, or None |
| `date_comparison(context, date)` | DataFrame, 8 rows in ticker order: symbol, daily_range_pct, is_flagged, co_flag_count (NaN when no trading that date) |
| `news_context(news, symbol, date)` | DataFrame: id, symbol, date, highlights, highlights_low_info; newest first |
| `filing_context(filings, symbol, date)` | dict: `filing` and `annual_risk_fallback` (each a dict with id, symbol, date, document_type, mda_content, risk_content, risk_refers_to_10k, or None), `filed_same_day` (bool) |

## 9. Technical choices
Python 3.13 with pandas and pyarrow, managed by `uv` (`pyproject.toml`, `uv.lock`).
The tables are small enough to keep in memory; no database or AI API is needed.
Phase 3 adds Streamlit and Plotly with `uv add streamlit plotly` (pinned in
`uv.lock`); the flagged-day table needs Streamlit's single-row dataframe selection.
Load the data once with `st.cache_data`, keyed on each file's path, size and
modification time. Keep long text in `news` and `filings` and look it up by id or
date; never copy it into `price_context`.

The MVP runs locally with `uv run streamlit run app.py`. Later deployment can use
a hosted Streamlit service that reads the committed `data/cleaned/` files.

Commands (project root; macOS needs `PYTHONPATH=src` because Python 3.13 ignores
the hidden editable-install `.pth` file):
```bash
PYTHONPATH=src uv run python -m unittest discover -s tests -v
PYTHONPATH=src uv run python -m dso576_python.phase2
```

## 10. Data limitations
News highlights are LLM-written summaries with no publication times; filings have
dates but no times. There is no market index, only eight large companies over a
short period. The short-text quality flags are length heuristics. Cleaning kept
every observation, imputed nothing, and removed no extremes.

## 11. Build order and acceptance
Done in Phase 2: canonical data on `main`, backend, tests. Phase 3 build order:
1. `uv add streamlit plotly`; load data through `load_cleaned` with caching.
2. Period selector, coverage banner, relative price chart, summary table.
3. Stock selector, detail chart, flagged-day table with selection state.
4. Selected-day metrics, eight-stock comparison, news and filing panels.
5. Check every item below.

Acceptance checks:
- Opens on full range, AAPL, 2025-04-09; every company shows 17 flagged days.
- Every indexed series starts at 100 on the period's first day; change over period matches the adjusted endpoints.
- Switching period changes price views and counts but never thresholds, flags, co-flags, or the news/filing windows.
- NVDA in 2026 shows the no-flags message and hides panels 7–8.
- Flagged-day order, default selections and tie-breaks match `flagged_days` / `initial_date`.
- Co-flag count always covers all eight stocks; legend toggles never change metrics.
- News window is D−7..D; no filing dated after D; same-day label; 10-K risk shown for "refers to 10-K" 10-Qs.
- Filing text shows ~2,000 characters plus an expander; `$` amounts display literally.
- Unknown values show "Unavailable", never 0; empty states show their messages.
- `PYTHONPATH=src uv run python -m unittest discover -s tests -v` passes and the backend imports without Streamlit.
