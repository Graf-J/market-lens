"""Extract: download daily OHLCV prices from Yahoo Finance via ``yfinance``."""

import logging
import time

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# yfinance column name -> RAW table column name (uppercase = unquoted in Snowflake)
COLUMN_MAP = {
    "Open": "OPEN",
    "High": "HIGH",
    "Low": "LOW",
    "Close": "CLOSE",
    "Adj Close": "ADJ_CLOSE",
    "Volume": "VOLUME",
}
OUTPUT_COLUMNS = ["TICKER", "PRICE_DATE", *COLUMN_MAP.values()]


def fetch_prices(
    tickers: list[str],
    period: str = "5y",
    max_attempts: int = 3,
    backoff_seconds: int = 30,
) -> pd.DataFrame:
    """Download daily prices for ``tickers`` and return a long (tidy) DataFrame.

    One row per ticker and trading day with columns ``OUTPUT_COLUMNS``.
    Retries the whole download with linear backoff, because Yahoo occasionally
    rate-limits or returns empty frames. Raises if any ticker has no data, so a
    partial download never silently reaches Snowflake.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            wide = yf.download(
                tickers,
                period=period,
                interval="1d",
                auto_adjust=False,  # keep both Close and Adj Close (default is True)
                actions=False,
                group_by="column",
                threads=True,
                progress=False,
            )
            df = _to_long(wide)
            missing = sorted(set(tickers) - set(df["TICKER"]))
            if missing:
                raise ValueError(f"No data returned for tickers: {missing}")
            log.info("Downloaded %d rows for %d tickers", len(df), len(tickers))
            return df
        except Exception as exc:  # noqa: BLE001 - yfinance raises many error types
            if attempt == max_attempts:
                raise
            wait = backoff_seconds * attempt
            log.warning("Download attempt %d failed (%s); retrying in %ds", attempt, exc, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Reshape yfinance's (Price, Ticker) column MultiIndex into one row per ticker/day."""
    if wide.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    long = (
        wide.stack(level="Ticker", future_stack=True)
        .rename_axis(["PRICE_DATE", "TICKER"])
        .reset_index()
        .rename(columns=COLUMN_MAP)
        .rename_axis(columns=None)
    )
    # Days on which a ticker did not trade come back as all-NaN rows.
    long = long.dropna(subset=["CLOSE", "ADJ_CLOSE"])
    long["PRICE_DATE"] = pd.to_datetime(long["PRICE_DATE"]).dt.date
    long["VOLUME"] = long["VOLUME"].fillna(0).astype("int64")
    return long[OUTPUT_COLUMNS].sort_values(["TICKER", "PRICE_DATE"]).reset_index(drop=True)
