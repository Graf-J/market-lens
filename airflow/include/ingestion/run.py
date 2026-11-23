"""Run extract + load locally, outside of Airflow.

Usage (from the ``airflow/`` folder, credentials in ``Final-Project/.env``):

    uv run python -m include.ingestion.run              # extract + load
    uv run python -m include.ingestion.run --dry-run    # extract only, print a preview

In Airflow the same ``fetch_prices`` / ``load_prices`` functions are called from
the DAG, with the connection coming from ``SnowflakeHook`` instead.
"""

import argparse
import logging
import os
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

from include.ingestion.config import HISTORY_PERIOD, load_tickers
from include.ingestion.snowflake_loader import load_prices
from include.ingestion.yahoo_finance import fetch_prices

# Final-Project/.env (local credentials). Not airflow/.env, which is for Docker.
LOCAL_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def connect_from_env() -> snowflake.connector.SnowflakeConnection:
    """Open a key-pair authenticated Snowflake connection from SNOWFLAKE_* env vars."""
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "STOCKS_DB"),
        authenticator="SNOWFLAKE_JWT",
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="extract only, do not load")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(LOCAL_ENV_FILE)

    df = fetch_prices(load_tickers(), period=HISTORY_PERIOD)
    if args.dry_run:
        print(df.groupby("TICKER")["PRICE_DATE"].agg(["count", "min", "max"]))
        print(df.tail())
        return

    with connect_from_env() as conn:
        print(load_prices(conn, df))


if __name__ == "__main__":
    main()
