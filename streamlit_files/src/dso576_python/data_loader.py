"""Load and validate canonical full data. Never substitute sample CSVs."""
from pathlib import Path
import numpy as np
import pandas as pd
from .constants import COMPANIES

REQUIRED = {
    'prices': ['id', 'symbol', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume', 'daily_range_pct'],
    'news': ['id', 'symbol', 'date', 'highlights', 'highlights_low_info'],
    'filings': ['id', 'symbol', 'date', 'document_type', 'mda_content', 'risk_content', 'risk_refers_to_10k'],
    'price_context': ['price_id', 'symbol', 'date', 'high', 'low', 'close', 'daily_range_pct', 'is_flagged',
                      'co_flag_count', 'news_id', 'highlights_low_info', 'filing_id', 'filing_date',
                      'document_type', 'risk_refers_to_10k', 'filed_same_day', 'latest_10k_id', 'latest_10k_date'],
}
EXPECTED_ROWS = {'prices': 2656, 'news': 3888, 'filings': 73, 'price_context': 2656}


def validate_data(data, strict_source=True):
    for name, cols in REQUIRED.items():
        frame = data[name]
        missing = set(cols) - set(frame.columns)
        if missing:
            raise ValueError(f'{name}: missing columns {sorted(missing)}')
        required_non_null = cols if name != 'price_context' else ['price_id', 'symbol', 'date', 'high', 'low', 'close', 'daily_range_pct', 'is_flagged', 'co_flag_count']
        if frame[required_non_null].isna().any().any():
            raise ValueError(f'{name}: missing required values')
        if not pd.api.types.is_datetime64_any_dtype(frame['date']):
            raise ValueError(f'{name}: date must be datetime')
        if not frame['date'].eq(frame['date'].dt.normalize()).all():
            raise ValueError(f'{name}: dates must be day-grain')
        if not set(frame['symbol']).issubset(COMPANIES):
            raise ValueError(f'{name}: unexpected symbols')
        keys = ['symbol', 'date', 'document_type'] if name == 'filings' else ['symbol', 'date']
        if frame.duplicated(keys).any():
            raise ValueError(f'{name}: duplicate keys')
        id_col = 'price_id' if name == 'price_context' else 'id'
        if frame[id_col].duplicated().any():
            raise ValueError(f'{name}: duplicate IDs')
        if strict_source and (len(frame) != EXPECTED_ROWS[name] or set(frame['symbol']) != set(COMPANIES)):
            raise ValueError(f'{name}: does not match pinned full-source dimensions')
    for name, columns in [('news', ['highlights_low_info']), ('filings', ['risk_refers_to_10k']),
                          ('price_context', ['is_flagged', 'filed_same_day'])]:
        for col in columns:
            if not pd.api.types.is_bool_dtype(data[name][col]):
                raise ValueError(f'{name}.{col}: must be boolean')
    p, c, n, f = (data[k] for k in ['prices', 'price_context', 'news', 'filings'])
    numeric = p[['open', 'high', 'low', 'close', 'adj_close', 'volume', 'daily_range_pct']]
    if not all(pd.api.types.is_numeric_dtype(numeric[k]) for k in numeric) or not np.isfinite(numeric).all().all():
        raise ValueError('prices: expected finite numeric values')
    if (p[['open', 'high', 'low', 'close', 'adj_close']] <= 0).any().any() or (p['volume'] < 0).any():
        raise ValueError('prices: invalid prices or volume')
    if (p['high'] < p[['open', 'close', 'low']].max(axis=1)).any() or (p['low'] > p[['open', 'close', 'high']].min(axis=1)).any():
        raise ValueError('prices: inconsistent OHLC')
    if not set(f['document_type']).issubset({'10-K', '10-Q'}):
        raise ValueError('filings: unexpected document type')
    if f.duplicated(['symbol', 'date']).any():
        raise ValueError('filings: ambiguous same-date filing; reconcile before joining')
    if not np.allclose(p['daily_range_pct'], (p['high'] - p['low']) / p['close']):
        raise ValueError('prices: daily range mismatch')
    ps = p.set_index(['symbol', 'date']).sort_index()
    cs = c.set_index(['symbol', 'date']).sort_index()
    if not ps.index.equals(cs.index):
        raise ValueError('context: trading grid differs from prices')
    for col in ['high', 'low', 'close', 'daily_range_pct']:
        if not np.allclose(ps[col], cs[col]):
            raise ValueError(f'context: {col} differs from prices')
    if not np.array_equal(ps['id'], cs['price_id']):
        raise ValueError('context: incorrect price IDs')
    thresholds = ps.groupby(level='symbol')['daily_range_pct'].transform(lambda s: s.quantile(.95))
    flags = ps['daily_range_pct'].ge(thresholds)
    if not np.array_equal(flags, cs['is_flagged']):
        raise ValueError('context: flags disagree with full-sample 95th percentile')
    counts = cs.groupby(level='date')['is_flagged'].transform('sum')
    if not np.array_equal(counts, cs['co_flag_count']):
        raise ValueError('context: incorrect co-flag counts')
    # Independently recompute expected joins, including absence and as-of maximality.
    from .cleaning import build_price_context
    expected = build_price_context({'prices': p, 'news': n, 'filings': f}).set_index(['symbol', 'date']).sort_index()
    for col in ['news_id', 'highlights_low_info', 'filing_id', 'filing_date', 'document_type',
                'risk_refers_to_10k', 'filed_same_day', 'latest_10k_id', 'latest_10k_date']:
        left, right = cs[col], expected[col]
        if not ((left.eq(right)) | (left.isna() & right.isna())).all():
            raise ValueError(f'context: incorrect temporal link or label in {col}')
    if strict_source:
        if p['date'].min() != pd.Timestamp('2024-12-02') or p['date'].max() != pd.Timestamp('2026-03-31'):
            raise ValueError('prices: unexpected coverage')
        if not p.groupby('symbol').size().eq(332).all() or not counts.groupby(level='date').size().eq(8).all():
            raise ValueError('prices: incomplete eight-stock trading grid')
    return {'rows': {name: len(frame) for name, frame in data.items()},
            'flagged_days': int(c['is_flagged'].sum()), 'validated': True}


def load_cleaned(directory='data/cleaned', strict_source=True):
    root = Path(directory)
    missing = [str(root / f'{name}.parquet') for name in REQUIRED if not (root / f'{name}.parquet').exists()]
    if missing:
        raise FileNotFoundError('Missing canonical files: ' + ', '.join(missing) + '. See README.md; sample CSVs cannot replace these files.')
    data = {name: pd.read_parquet(root / f'{name}.parquet') for name in REQUIRED}
    validate_data(data, strict_source=strict_source)
    return data
