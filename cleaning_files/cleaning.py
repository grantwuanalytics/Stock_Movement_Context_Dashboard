"""Clean the Herculean prices, news, and filings tables.

Reads the unchanged raw Parquet files in data/raw/, applies rules R1-R11 from
docs/cleaning_decision_log.md, and writes:

    data/cleaned/prices.parquet
    data/cleaned/news.parquet
    data/cleaned/filings.parquet
    data/cleaned/price_context.parquet  (prices joined to news and latest filings)
    outputs/cleaning_changes.csv   (one row per rule: what changed, and how much)
    sample/{price_context,news,filings}_sample.csv  (50-row cleaned sample)

Run from the project root:  uv run python src/dso576_python/cleaning.py
"""

import hashlib
import html
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/cleaned")
OUTPUT_DIR = Path("outputs")
SAMPLE_DIR = Path("sample")

# Dataset version: TheFinAI/Herculean commit 52d3ecb97e490a2392717935402cde283e8fa36e
RAW_SHA256 = {
    "prices": "736c124db22e976dbf4ec1dd65e5a983497e5890e7999f7925b343dee5c965d5",
    "news": "1fd109796eada02af37a15178cc150ec252e7c02bc440c3f76641eb8fab6da25",
    "filings": "822a854865651e042c9d64288785efa0f2c0fecdec2a16016ff3c2e7a5601299",
}
# Mirrors constants.COMPANIES; kept here so this file still runs as a standalone script.
# tests/test_analysis.py checks the two stay identical.
TICKERS = {"AAPL", "ADBE", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"}
DOCUMENT_TYPES = {"10-K", "10-Q"}
LOW_INFO_HIGHLIGHT_CHARS = 300  # R5: shorter news summaries are broken or "no content" LLM output
REFERENCE_RISK_CHARS = 2000  # R6: shorter risk sections just point back to the 10-K
FLAG_QUANTILE = 0.95  # a day is flagged when its daily range is in its symbol's top 5%
SAMPLE_TEXT_CHARS = 300  # text columns in the sample CSVs are cut to this length


def verify_raw_files() -> None:
    """Stop if any raw file differs from the published dataset version."""
    for table, expected in RAW_SHA256.items():
        digest = hashlib.sha256((RAW_DIR / f"{table}.parquet").read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f"data/raw/{table}.parquet does not match the expected SHA-256")


def load_raw() -> dict[str, pd.DataFrame]:
    return {table: pd.read_parquet(RAW_DIR / f"{table}.parquet") for table in RAW_SHA256}


def _change(rule, table, column, action, before, after, values_changed):
    """One row of the change log."""
    return {
        "rule": rule,
        "table": table,
        "column": column,
        "action": action,
        "rows_before": len(before),
        "rows_after": len(after),
        "nulls_before": int(before[column].isna().sum()) if column in before else None,
        "nulls_after": int(after[column].isna().sum()),
        "values_changed": int(values_changed),
    }


def convert_dates(df: pd.DataFrame, table: str, changes: list) -> pd.DataFrame:
    """R1: object (Python date) -> datetime64, so tables share one joinable date type."""
    out = df.copy()
    out["date"] = pd.to_datetime(df["date"], errors="coerce")
    failed = out["date"].isna() & df["date"].notna()
    if failed.any():
        raise ValueError(f"{table}: {failed.sum()} dates failed to convert")
    changes.append(_change("R1", table, "date", "object -> datetime64", df, out, len(out)))
    return out


def standardize_symbol(df: pd.DataFrame, table: str, changes: list) -> pd.DataFrame:
    """R2: strip/uppercase tickers and check they are the expected eight."""
    out = df.copy()
    out["symbol"] = df["symbol"].str.strip().str.upper()
    unexpected = set(out["symbol"]) - TICKERS
    if unexpected:
        raise ValueError(f"{table}: unexpected symbols {unexpected}")
    changed = (out["symbol"] != df["symbol"]).sum()
    changes.append(_change("R2", table, "symbol", "strip + upper; validate 8 tickers", df, out, changed))
    return out


def clean_prices(prices: pd.DataFrame, changes: list) -> pd.DataFrame:
    out = convert_dates(prices, "prices", changes)
    out = standardize_symbol(out, "prices", changes)
    # R8: keep every row, extreme days included; same-day ratio so splits don't matter
    out["daily_range_pct"] = (out["high"] - out["low"]) / out["close"]
    changes.append(_change("R8", "prices", "daily_range_pct", "derived (high - low) / close; no rows removed",
                           prices, out, 0))
    return out


def clean_news(news: pd.DataFrame, changes: list) -> pd.DataFrame:
    out = convert_dates(news, "news", changes)
    out = standardize_symbol(out, "news", changes)
    # R5: text left unchanged; broken summaries are flagged, not deleted
    out["highlights_low_info"] = out["highlights"].str.len() < LOW_INFO_HIGHLIGHT_CHARS
    changes.append(_change("R5", "news", "highlights_low_info", f"flag len(highlights) < {LOW_INFO_HIGHLIGHT_CHARS}",
                           news, out, out["highlights_low_info"].sum()))
    # R11: weekend and holiday rows are kept for the D-7 news window
    return out


def clean_filings(filings: pd.DataFrame, changes: list) -> pd.DataFrame:
    out = convert_dates(filings, "filings", changes)
    out = standardize_symbol(out, "filings", changes)
    # R3: only 10-K and 10-Q
    unexpected = set(out["document_type"]) - DOCUMENT_TYPES
    if unexpected:
        raise ValueError(f"filings: unexpected document_type {unexpected}")
    changes.append(_change("R3", "filings", "document_type", "validate 10-K or 10-Q only", filings, out, 0))
    # R4: decode HTML entities and strip outer whitespace; wording is otherwise untouched
    for column in ["mda_content", "risk_content"]:
        out[column] = filings[column].map(html.unescape).str.strip()
        changed = (out[column] != filings[column]).sum()
        changes.append(_change("R4", "filings", column, "html.unescape + strip", filings, out, changed))
    # R6: 10-Q risk sections that only refer back to the annual report
    out["risk_refers_to_10k"] = out["risk_content"].str.len() < REFERENCE_RISK_CHARS
    changes.append(_change("R6", "filings", "risk_refers_to_10k", f"flag len(risk_content) < {REFERENCE_RISK_CHARS}",
                           filings, out, out["risk_refers_to_10k"].sum()))
    # R10: filings dated before the price window are kept for the as-of join
    return out


def clean_all(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    changes = []
    cleaned = {
        "prices": clean_prices(raw["prices"], changes),
        "news": clean_news(raw["news"], changes),
        "filings": clean_filings(raw["filings"], changes),
    }
    # R7 / R9: no rows dropped, nothing imputed
    for table, df in cleaned.items():
        if len(df) != len(raw[table]):
            raise ValueError(f"{table}: row count changed {len(raw[table])} -> {len(df)}")
    return cleaned, pd.DataFrame(changes).astype({"nulls_before": "Int64"})


def build_price_context(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per (symbol, trading day): flag, same-day news, and latest filings.

    Text stays in the news and filings tables; this table carries their ids.
    """
    prices = cleaned["prices"]

    # Flag: top 5% of daily_range_pct within each symbol
    threshold = prices.groupby("symbol")["daily_range_pct"].transform(lambda s: s.quantile(FLAG_QUANTILE))
    context = prices[["id", "symbol", "date", "high", "low", "close", "daily_range_pct"]].rename(columns={"id": "price_id"})
    context["is_flagged"] = context["daily_range_pct"] >= threshold
    # How many of the 8 companies were flagged that day (high = likely market-wide)
    context["co_flag_count"] = context.groupby("date")["is_flagged"].transform("sum")

    # prices -> news: exactly one news row per trading day
    news = cleaned["news"][["id", "symbol", "date", "highlights_low_info"]].rename(columns={"id": "news_id"})
    context = context.merge(news, on=["symbol", "date"], how="left", validate="one_to_one")

    # prices -> latest filing on or before the day; same-day filings included (team decision)
    filings = cleaned["filings"].rename(columns={"id": "filing_id", "date": "filing_date"})
    latest = filings[["filing_id", "symbol", "filing_date", "document_type", "risk_refers_to_10k"]]
    context = pd.merge_asof(
        context.sort_values("date"), latest.sort_values("filing_date"),
        left_on="date", right_on="filing_date", by="symbol", direction="backward", allow_exact_matches=True,
    )
    context["filed_same_day"] = context["filing_date"] == context["date"]

    # prices -> latest 10-K, for 10-Q risk sections that only refer back to it (R6)
    annual = filings.loc[filings["document_type"] == "10-K", ["filing_id", "symbol", "filing_date"]]
    annual = annual.rename(columns={"filing_id": "latest_10k_id", "filing_date": "latest_10k_date"})
    context = pd.merge_asof(
        context, annual.sort_values("latest_10k_date"),
        left_on="date", right_on="latest_10k_date", by="symbol", direction="backward", allow_exact_matches=True,
    )

    context = context.sort_values(["symbol", "date"]).reset_index(drop=True)
    if len(context) != len(prices):
        raise ValueError(f"price_context: expected {len(prices)} rows, got {len(context)}")
    return context


def _first_reason(picks: list[tuple[pd.DataFrame, str]], id_column: str) -> pd.DataFrame:
    """Stack picked rows in priority order, keeping each id once with the first reason it was picked for."""
    stacked = pd.concat([rows.assign(sample_reason=reason) for rows, reason in picks])
    return stacked.drop_duplicates(id_column)


def build_sample(cleaned: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """50 cleaned rows: 40 price_context, 5 news, 5 filings. Difficult cases first, then a seeded random fill."""
    ctx = cleaned["price_context"]
    news = cleaned["news"]
    filings = cleaned["filings"]
    day = pd.Timestamp

    def at(symbol, date):
        return ctx[(ctx["symbol"] == symbol) & (ctx["date"] == day(date))]

    ranked = ctx.sort_values("daily_range_pct")
    context = _first_reason([
        (at("TSLA", "2025-04-09"), "record check 1: largest range"),
        (at("AAPL", "2024-12-02"), "record check 2: first trading day"),
        (at("NVDA", "2025-02-26"), "record check 3: filing same day"),
        (ctx[ctx["is_flagged"] & ctx["highlights_low_info"]], "flagged day with low-info news"),
        (ctx[ctx["date"] == day("2025-04-07")], "all 8 flagged (market-wide)"),
        (ranked.groupby("symbol").tail(1), "largest range for symbol"),
        (ranked.groupby("symbol").head(1), "smallest range for symbol"),
        (ctx[ctx["filed_same_day"]].groupby("symbol").head(1), "filing same day"),
        (ctx[ctx["risk_refers_to_10k"]].groupby("symbol").head(1), "latest 10-Q risk refers to 10-K"),
    ], "price_id")
    fill = ctx[~ctx["price_id"].isin(context["price_id"])].sample(40 - len(context), random_state=576)
    context = pd.concat([context, fill.assign(sample_reason="random (seed 576)")])

    news_rows = _first_reason([
        (news[news["id"] == 543], "record check 4: Sunday, broken summary"),
        (news[news["id"] == 1962], "low-info summary on a flagged day"),
        (news[news["highlights"].str.contains("&D;", regex=False)], "literal '&D;' left unchanged"),
        (news[(news["date"].dt.dayofweek == 5) & ~news["highlights_low_info"]].head(1), "weekend news"),
        (news[(news["date"].dt.dayofweek == 0) & ~news["highlights_low_info"]].head(1), "typical weekday news"),
    ], "id")
    filing_rows = _first_reason([
        (filings[filings["id"] == 1], "record check 5: entity + leading space"),
        (filings[filings["id"] == 4], "latest filing for record check 2"),
        (filings[filings["id"] == 60], "filed same day as record check 3"),
        (filings[filings["id"] == 66], "risk section refers to 10-K (repeated text)"),
        (filings[filings["id"] == 10], "earliest filing, before price window"),
    ], "id")

    # Long text is cut to keep the CSV readable; full lengths are kept alongside
    news_rows = news_rows.assign(highlights_chars=news_rows["highlights"].str.len(),
                                 highlights=news_rows["highlights"].str[:SAMPLE_TEXT_CHARS])
    for column in ["mda_content", "risk_content"]:
        filing_rows = filing_rows.assign(**{f"{column}_chars": filing_rows[column].str.len(),
                                            column: filing_rows[column].str[:SAMPLE_TEXT_CHARS]})
    return {"price_context": context, "news": news_rows, "filings": filing_rows}


def validate_raw(raw: dict[str, pd.DataFrame]) -> None:
    """Reject invalid raw keys/types before the supplied deterministic cleaning."""
    import numpy as np
    required = {
        "prices": ["id", "symbol", "date", "open", "high", "low", "close", "adj_close", "volume"],
        "news": ["id", "symbol", "date", "highlights"],
        "filings": ["id", "symbol", "date", "document_type", "mda_content", "risk_content"],
    }
    expected = {"prices": 2656, "news": 3888, "filings": 73}
    for name, columns in required.items():
        frame = raw[name]
        if set(columns) - set(frame.columns) or len(frame) != expected[name]:
            raise ValueError(f"{name}: unexpected pinned-source schema or row count")
        if frame[columns].isna().any().any():
            raise ValueError(f"{name}: missing raw values; reconcile before cleaning")
        if frame["id"].duplicated().any():
            raise ValueError(f"{name}: duplicate raw IDs")
        dates = pd.to_datetime(frame["date"], errors="raise")
        key = pd.DataFrame({"symbol": frame["symbol"].str.strip().str.upper(), "date": dates})
        if set(key["symbol"]) != TICKERS or key.duplicated().any():
            raise ValueError(f"{name}: unknown/missing ticker or ambiguous company/date key")
    prices = raw["prices"]
    values = prices[["open", "high", "low", "close", "adj_close", "volume"]]
    if not all(pd.api.types.is_numeric_dtype(values[c]) for c in values) or not np.isfinite(values).all().all():
        raise ValueError("prices: expected finite numeric values")
    if (prices[["open", "high", "low", "close", "adj_close"]] <= 0).any().any() or (prices["volume"] < 0).any():
        raise ValueError("prices: nonpositive price or negative volume")
    if (prices["high"] < prices[["open", "close", "low"]].max(axis=1)).any() or (prices["low"] > prices[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("prices: inconsistent OHLC")


def main() -> None:
    verify_raw_files()
    raw = load_raw()
    validate_raw(raw)
    cleaned, changes = clean_all(raw)
    cleaned["price_context"] = build_price_context(cleaned)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for table, df in cleaned.items():
        df.to_parquet(CLEAN_DIR / f"{table}.parquet", index=False)
        print(f"wrote {CLEAN_DIR / table}.parquet  ({len(df):,} rows)")
    changes.to_csv(OUTPUT_DIR / "cleaning_changes.csv", index=False)
    print(f"wrote {OUTPUT_DIR / 'cleaning_changes.csv'}")
    for table, df in build_sample(cleaned).items():
        df.to_csv(SAMPLE_DIR / f"{table}_sample.csv", index=False)
        print(f"wrote {SAMPLE_DIR / table}_sample.csv  ({len(df)} rows)")


if __name__ == "__main__":
    main()
