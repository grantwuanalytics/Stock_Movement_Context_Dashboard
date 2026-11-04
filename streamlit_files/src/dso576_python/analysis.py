"""Pure analysis functions for the Phase 3 dashboard; no UI or network calls.

Ratios are returned as decimals; indexed_price has base 100. Input frames
are never modified. Full-sample flags are supplied by cleaning.py.
"""
import pandas as pd

from .constants import COMPANIES, FULL_RANGE, PERIODS, YEARS  # noqa: F401 (re-exported)


def _period(frame, period):
    # 'full' keeps every row; a year keeps only that calendar year
    if period not in PERIODS:
        raise ValueError(f'Period must be one of {PERIODS}')
    if period == FULL_RANGE:
        return frame.copy()
    return frame.loc[frame['date'].dt.year.eq(period)].copy()


def _symbol(symbol):
    if symbol not in COMPANIES:
        raise ValueError(f'Unknown symbol: {symbol}')


def year_coverage(prices, period):
    frame = _period(prices, period)
    return {
        'period': period, 'start_date': frame['date'].min(),
        'end_date': frame['date'].max(), 'companies': frame['symbol'].nunique(),
        'trading_dates': frame['date'].nunique(),
        'coverage_label': {FULL_RANGE: 'Full available range',
                           2024: 'Partial year: December only',
                           2025: 'Full available year',
                           2026: 'Partial year: January–March'}[period],
    }


def indexed_prices(prices, period):
    """Return ratios as decimals, except indexed_price (base 100)."""
    frame = _period(prices, period).sort_values(['symbol', 'date'])
    base = frame.groupby('symbol')['adj_close'].transform('first')
    frame['period_change'] = frame['adj_close'] / base - 1
    frame['indexed_price'] = (frame['period_change'] + 1) * 100
    return frame[['symbol', 'date', 'adj_close', 'indexed_price', 'period_change']].reset_index(drop=True)


def year_summary(prices, context, period):
    """One row per expected ticker, including explicit missing-data rows."""
    p = _period(prices, period).sort_values(['symbol', 'date'])
    c = _period(context, period)
    rows = []
    for symbol, company in COMPANIES.items():
        stock = p.loc[p['symbol'].eq(symbol)]
        ctx = c.loc[c['symbol'].eq(symbol)]
        row = {'symbol': symbol, 'company': company, 'trading_days': len(stock),
               'last_close': float('nan'), 'period_change': float('nan'),
               'flagged_days': pd.NA, 'largest_daily_range': float('nan'),
               'start_date': pd.NaT, 'end_date': pd.NaT}
        if not stock.empty:
            row.update(last_close=stock.iloc[-1]['close'],
                       period_change=stock.iloc[-1]['adj_close'] / stock.iloc[0]['adj_close'] - 1,
                       flagged_days=int(ctx['is_flagged'].sum()),
                       largest_daily_range=ctx['daily_range_pct'].max(),
                       start_date=stock.iloc[0]['date'], end_date=stock.iloc[-1]['date'])
        rows.append(row)
    return pd.DataFrame(rows).astype({'flagged_days': 'Int64'})


def stock_series(context, period, symbol):
    _symbol(symbol)
    frame = _period(context, period)
    return frame.loc[frame['symbol'].eq(symbol)].sort_values('date').reset_index(drop=True)


def flagged_days(context, period, symbol):
    frame = stock_series(context, period, symbol)
    return frame.loc[frame['is_flagged']].sort_values(
        ['daily_range_pct', 'date'], ascending=[False, True]).reset_index(drop=True)


def initial_date(context, period, symbol='AAPL'):
    frame = flagged_days(context, period, symbol)
    return None if frame.empty else frame.iloc[0]['date']


def date_comparison(context, date):
    """Always retain all eight tickers; missing observations stay missing."""
    day = pd.Timestamp(date).normalize()
    frame = context.loc[context['date'].eq(day),
                        ['symbol', 'daily_range_pct', 'is_flagged', 'co_flag_count']]
    return frame.set_index('symbol').reindex(list(COMPANIES)).rename_axis('symbol').reset_index()


def news_context(news, symbol, date):
    _symbol(symbol)
    end = pd.Timestamp(date).normalize()
    start = end - pd.Timedelta(days=7)
    return news.loc[news['symbol'].eq(symbol) & news['date'].between(start, end)].sort_values(
        'date', ascending=False).reset_index(drop=True)


def filing_context(filings, symbol, date):
    """As-of filing and optional annual risk fallback. Ties fail explicitly."""
    _symbol(symbol)
    day = pd.Timestamp(date).normalize()
    eligible = filings.loc[filings['symbol'].eq(symbol) & filings['date'].le(day)]

    def latest(frame):
        if frame.empty:
            return None
        rows = frame.loc[frame['date'].eq(frame['date'].max())]
        if len(rows) != 1:
            raise ValueError('Ambiguous same-date filings: resolve in canonical cleaning')
        return rows.iloc[0].to_dict()

    filing = latest(eligible)
    annual = None
    if filing and filing['document_type'] == '10-Q' and filing['risk_refers_to_10k']:
        annual = latest(eligible.loc[eligible['document_type'].eq('10-K')])
    return {'filing': filing, 'annual_risk_fallback': annual,
            'filed_same_day': filing is not None and filing['date'] == day}
