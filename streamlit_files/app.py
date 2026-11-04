"""Streamlit UI for the Stock Movement Context Dashboard.

Run from Phase_2_Submission with: streamlit run app.py
"""
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

SRC = Path(__file__).resolve().parent / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dso576_python.analysis import (  # noqa: E402
    COMPANIES, YEARS, date_comparison, flagged_days, filing_context, indexed_prices,
    initial_date, news_context, stock_series, year_coverage, year_summary,
)
from dso576_python.charts import relative_price_figure, stock_price_figure  # noqa: E402
from dso576_python.data_loader import load_cleaned  # noqa: E402

st.set_page_config(page_title='Stock Movement Context Dashboard', layout='wide')


@st.cache_data(show_spinner='Loading and validating canonical data…')
def load_data(path_key, _file_signatures):
    # Cache key includes path, size and mtime for each canonical file.
    del _file_signatures
    return load_cleaned(path_key)


def file_signatures(directory):
    root = Path(directory)
    return tuple((name, (root / f'{name}.parquet').stat().st_size,
                  (root / f'{name}.parquet').stat().st_mtime_ns)
                 for name in ('prices', 'news', 'filings', 'price_context')
                 if (root / f'{name}.parquet').exists())


def fmt_date(value):
    return 'Unavailable' if pd.isna(value) else pd.Timestamp(value).strftime('%Y-%m-%d')


def fmt_pct(value):
    return 'Unavailable' if pd.isna(value) else f'{float(value):.2%}'


def set_year(year):
    st.session_state.active_year = year
    st.session_state.selected_symbol = 'AAPL'
    st.session_state.selected_date = initial_date(st.session_state.data['price_context'], year, 'AAPL')


def set_symbol(symbol):
    st.session_state.selected_symbol = symbol
    st.session_state.selected_date = initial_date(
        st.session_state.data['price_context'], st.session_state.active_year, symbol)


st.title('Stock Movement Context Dashboard')
st.caption('Compare eight stocks, identify unusually wide daily ranges, and review related news and company filings.')

data_dir = Path(__file__).resolve().parent / 'data' / 'cleaned'
try:
    data = load_data(str(data_dir), file_signatures(data_dir))
except (FileNotFoundError, ValueError, OSError) as exc:
    st.error(str(exc))
    st.stop()

st.session_state.data = data
if 'active_year' not in st.session_state:
    st.session_state.active_year = 2025
    st.session_state.selected_symbol = 'AAPL'
    st.session_state.selected_date = initial_date(data['price_context'], 2025, 'AAPL')

year = st.segmented_control('Year', options=list(YEARS), default=st.session_state.active_year,
                            key='year_control', format_func=lambda value: str(value))
if year != st.session_state.active_year:
    set_year(year)
    st.rerun()

prices, context, news, filings = (data[k] for k in ('prices', 'price_context', 'news', 'filings'))
coverage = year_coverage(prices, year)
start, end = coverage['start_date'], coverage['end_date']
notice = coverage['coverage_label']
st.info(f"**{year} coverage:** {fmt_date(start)} to {fmt_date(end)} · "
        f"{coverage['companies']} companies · {coverage['trading_dates']} trading dates · {notice}")

st.subheader('Eight-stock overview')
st.plotly_chart(relative_price_figure(indexed_prices(prices, year)), use_container_width=True)

summary = year_summary(prices, context, year).rename(columns={
    'company': 'Company', 'symbol': 'Ticker', 'last_close': 'Last available close (USD)',
    'period_change': 'Change over available period', 'flagged_days': 'Flagged trading days',
    'largest_daily_range': 'Largest normalized daily range', 'trading_days': 'Trading days available',
})
summary = summary[['Company', 'Ticker', 'Last available close (USD)', 'Change over available period',
                   'Flagged trading days', 'Largest normalized daily range', 'Trading days available']]
st.dataframe(summary, hide_index=True, use_container_width=True,
             column_config={
                 'Last available close (USD)': st.column_config.NumberColumn(format='$%.2f'),
                 'Change over available period': st.column_config.NumberColumn(format='%.2%%'),
                 'Largest normalized daily range': st.column_config.NumberColumn(format='%.2%%'),
                 'Flagged trading days': st.column_config.NumberColumn(format='%d'),
                 'Trading days available': st.column_config.NumberColumn(format='%d'),
             })

st.subheader('Investigate a stock')
symbols = list(COMPANIES)
symbol = st.selectbox('Select a stock to investigate', symbols,
                      format_func=lambda item: f'{COMPANIES[item]} ({item})',
                      index=symbols.index(st.session_state.selected_symbol), key='stock_control')
if symbol != st.session_state.selected_symbol:
    set_symbol(symbol)
    st.rerun()

series = stock_series(context, year, symbol)
st.plotly_chart(stock_price_figure(series, symbol), use_container_width=True)
ranked_flags = flagged_days(context, year, symbol)
if ranked_flags.empty:
    st.info('No flagged trading days for this stock in the selected year.')
    st.session_state.selected_date = None
    st.stop()

st.markdown('**Flagged trading days** — select one row to update the event context.')
flag_table = ranked_flags[['date', 'close', 'high', 'low', 'daily_range_pct', 'co_flag_count']].copy()
flag_table['date'] = flag_table['date'].dt.strftime('%Y-%m-%d')
flag_table = flag_table.rename(columns={'date': 'Date', 'close': 'Close (USD)', 'high': 'High (USD)',
                                        'low': 'Low (USD)', 'daily_range_pct': 'Normalized daily range',
                                        'co_flag_count': 'Co-flag count'})
try:
    event = st.dataframe(flag_table, hide_index=True, use_container_width=True,
                         on_select='rerun', selection_mode='single-row',
                         column_config={'Close (USD)': st.column_config.NumberColumn(format='$%.2f'),
                                        'High (USD)': st.column_config.NumberColumn(format='$%.2f'),
                                        'Low (USD)': st.column_config.NumberColumn(format='$%.2f'),
                                        'Normalized daily range': st.column_config.NumberColumn(format='%.2%%'),
                                        'Co-flag count': st.column_config.NumberColumn(format='%d')})
except Exception as exc:
    st.error(f'The installed Streamlit version does not support selectable table rows: {exc}')
    st.stop()

selected_rows = event.selection.rows
if selected_rows:
    st.session_state.selected_date = ranked_flags.iloc[selected_rows[0]]['date']
elif st.session_state.selected_date not in set(ranked_flags['date']):
    st.session_state.selected_date = ranked_flags.iloc[0]['date']
selected_date = st.session_state.selected_date

if selected_date is not None:
    st.subheader(f'Event context · {symbol} · {fmt_date(selected_date)}')
    event_row = series.loc[series['date'].eq(selected_date)].iloc[0]
    comparison = date_comparison(context, selected_date)
    co_flags = int(comparison['is_flagged'].fillna(False).sum())
    metric_cols = st.columns(6)
    metrics = [('Company', f"{COMPANIES[symbol]} ({symbol})"), ('Date', fmt_date(selected_date)),
               ('Close', f"${event_row['close']:.2f}"), ('High', f"${event_row['high']:.2f}"),
               ('Low', f"${event_row['low']:.2f}"), ('Normalized range', fmt_pct(event_row['daily_range_pct']))]
    for col, (label, value) in zip(metric_cols, metrics):
        col.metric(label, value)
    st.markdown(f'**{co_flags} of 8 stocks flagged on this date**')
    comparison_view = comparison.rename(columns={'symbol': 'Ticker', 'daily_range_pct': 'Normalized daily range',
                                                  'is_flagged': 'Flagged', 'co_flag_count': 'Co-flag count'})
    st.dataframe(comparison_view, hide_index=True, use_container_width=True,
                 column_config={'Normalized daily range': st.column_config.NumberColumn(format='%.2%%'),
                                'Flagged': st.column_config.CheckboxColumn(),
                                'Co-flag count': st.column_config.NumberColumn(format='%d')})
    st.caption('A higher count may suggest shared conditions; it does not establish a market-wide cause. '
               'Intraday range is neither a close-to-close return nor evidence of direction. '
               'Full-sample thresholds are retrospective.')

    left, right = st.columns(2)
    with left:
        st.markdown('### News')
        st.caption('Stored AI-generated summaries are context; same-day summaries may include information released after market hours.')
        news_rows = news_context(news, symbol, selected_date)
        if news_rows.empty:
            st.info('No news summaries are available for this company in the selected date window.')
        for _, row in news_rows.iterrows():
            label = fmt_date(row['date']) + (' · selected date' if row['date'] == selected_date else '')
            with st.expander(label, expanded=row['date'] == selected_date):
                st.markdown(str(row['highlights']))
                st.caption('AI-generated news summary')
                if bool(row['highlights_low_info']):
                    st.warning('Limited information')
    with right:
        st.markdown('### SEC filing context')
        result = filing_context(filings, symbol, selected_date)
        filing = result['filing']
        if filing is None:
            st.info('No eligible 10-K or 10-Q filing is available for this company as of the selected date.')
        else:
            st.write(f"Latest eligible filing: **{filing['document_type']} · {fmt_date(filing['date'])}**")
            if result['filed_same_day']:
                st.caption('Filed on selected date; publication time unavailable.')
            with st.expander('Management Discussion & Analysis (MD&A)', expanded=False):
                st.markdown(filing['mda_content'] or 'MD&A content unavailable.')
            with st.expander('Risk Factors', expanded=False):
                st.markdown(filing['risk_content'] or 'Risk Factors content unavailable.')
            annual = result['annual_risk_fallback']
            if annual is not None:
                with st.expander(f"Risk Factors from annual 10-K · {fmt_date(annual['date'])}", expanded=False):
                    st.markdown(annual['risk_content'] or 'Annual Risk Factors content unavailable.')
        st.caption('Stored filing content consists of excerpts, not complete SEC documents. Filing date is not the fiscal period end.')
