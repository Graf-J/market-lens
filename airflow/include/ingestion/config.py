"""Central configuration for the ingestion step.

The ticker universe lives in the dbt seed ``tickers.csv`` so that the list of
stocks we download and the ``dim_tickers`` dimension can never drift apart.
"""

import csv
from pathlib import Path

# include/ingestion/config.py -> include/
INCLUDE_DIR = Path(__file__).resolve().parents[1]
TICKERS_SEED = INCLUDE_DIR / "stock_dbt" / "seeds" / "tickers.csv"

# How much history to (re)download on every run. Adjusted prices get restated
# after splits/dividends, so we always re-pull the full window and upsert it.
HISTORY_PERIOD = "5y"

RAW_DATABASE = "STOCKS_DB"
RAW_SCHEMA = "RAW"
RAW_TABLE = "STOCK_PRICES_DAILY"
SOURCE_NAME = "yfinance"


def load_tickers(seed_path: Path = TICKERS_SEED) -> list[str]:
    """Return the ticker symbols from the dbt seed file."""
    with seed_path.open(newline="", encoding="utf-8") as f:
        return [row["ticker"].strip().upper() for row in csv.DictReader(f)]
