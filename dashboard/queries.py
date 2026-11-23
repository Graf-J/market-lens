"""Data access: read the dbt marts from Snowflake (cached).

Credentials come from the same SNOWFLAKE_* variables as the rest of the project
(``Final-Project/.env`` locally). On Streamlit Community Cloud, root-level
secrets are exposed as environment variables, so the same code works there.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CACHE_TTL = "1h"  # the pipeline loads once per day; 1h keeps the app snappy and fresh


def _connection():
    # Not named "snowflake": with that name Streamlit ignores these kwargs and
    # looks for a secrets.toml / Snowflake config file instead.
    return st.connection(
        "market_lens",
        type="snowflake",
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "STOCKS_DB"),
        authenticator="SNOWFLAKE_JWT",
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
    )


def _query(sql: str) -> pd.DataFrame:
    df = _connection().query(sql, ttl=CACHE_TTL)
    df.columns = [c.lower() for c in df.columns]
    return df


def load_tickers() -> pd.DataFrame:
    """dim_tickers: one row per ticker (name, sector, benchmark flag)."""
    return _query("""
        select ticker, company_name, sector, is_benchmark
        from MARTS.DIM_TICKERS
        order by is_benchmark, ticker
    """)


def load_performance() -> pd.DataFrame:
    """mart_stock_performance: return / volatility / max drawdown per ticker and period."""
    df = _query("""
        select ticker, period, period_order, start_date, end_date, trading_days,
               total_return, annualized_volatility, max_drawdown
        from MARTS.MART_STOCK_PERFORMANCE
    """)
    df["start_date"] = pd.to_datetime(df["start_date"])
    for col in ("total_return", "annualized_volatility", "max_drawdown"):
        df[col] = df[col].astype(float)
    return df


def load_daily_prices() -> pd.DataFrame:
    """fct_daily_returns: adjusted close per ticker and day (~16k rows, loaded once)."""
    df = _query("""
        select ticker, price_date, adj_close
        from MARTS.FCT_DAILY_RETURNS
        order by ticker, price_date
    """)
    df["price_date"] = pd.to_datetime(df["price_date"])
    df["adj_close"] = df["adj_close"].astype(float)
    return df


def load_last_loaded_at() -> pd.Timestamp:
    """Timestamp (UTC) of the most recent pipeline load."""
    return _query("select max(loaded_at) as loaded_at from STAGING.STG_STOCK_PRICES")["loaded_at"].iloc[0]
