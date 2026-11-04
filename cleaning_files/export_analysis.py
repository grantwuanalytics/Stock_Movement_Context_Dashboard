"""Run canonical validation and export dashboard-ready analysis, not a UI."""
import argparse
import json
from pathlib import Path
from .analysis import (COMPANIES, year_summary, indexed_prices,
                       flagged_days, initial_date, news_context, filing_context,
                       date_comparison, year_coverage)
from .constants import FULL_RANGE, PERIODS
from .data_loader import load_cleaned, validate_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='data/cleaned')
    parser.add_argument('--output-dir', default='outputs/analysis')
    args = parser.parse_args()
    data = load_cleaned(args.data_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for period in PERIODS:
        year_summary(data['prices'], data['price_context'], period).to_csv(out / f'stock_summary_{period}.csv', index=False)
        indexed_prices(data['prices'], period).to_csv(out / f'indexed_prices_{period}.csv', index=False)
        flags = [flagged_days(data['price_context'], period, symbol) for symbol in COMPANIES]
        import pandas as pd
        pd.concat(flags, ignore_index=True).to_csv(out / f'flagged_days_{period}.csv', index=False)
        reports.append(year_coverage(data['prices'], period))
    # Example context for the default view: full range, AAPL
    selected = initial_date(data['price_context'], FULL_RANGE)
    if selected is not None:
        news_context(data['news'], 'AAPL', selected).to_csv(out / 'example_news_AAPL.csv', index=False)
        date_comparison(data['price_context'], selected).to_csv(out / 'example_cross_stock.csv', index=False)
        context = filing_context(data['filings'], 'AAPL', selected)
        (out / 'example_filings_AAPL.json').write_text(json.dumps(context, default=str, indent=2))
    report = {'validation': validate_data(data), 'coverage': reports,
              'source': 'Pinned Herculean full data; not sample or synthetic data'}
    (out / 'full_data_validation.json').write_text(json.dumps(report, default=str, indent=2))
    print(json.dumps(report, default=str, indent=2))


if __name__ == '__main__':
    main()
