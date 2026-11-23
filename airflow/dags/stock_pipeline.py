"""market-lens daily pipeline: Yahoo Finance -> Snowflake RAW -> dbt -> quality check.

    extract_load_prices >> dbt_build >> check_marts

* extract_load_prices: download the last 5 years of daily prices for every
  ticker in the dbt seed and MERGE them into STOCKS_DB.RAW.STOCK_PRICES_DAILY.
* dbt_build:           install packages, then seed + run + test all dbt models.
* check_marts:         fail the run if the marts are empty or stale.

Runs on weekdays after the US market close. Every run is idempotent, so manual
re-runs and retries are safe.
"""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLCheckOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator

SNOWFLAKE_CONN_ID = "snowflake_default"
DBT_PROJECT_DIR = "/usr/local/airflow/include/stock_dbt"


def extract_load_prices() -> dict[str, int]:
    """Download prices with yfinance and upsert them into the RAW table.

    Imports live inside the function so that DAG parsing (every few seconds)
    stays fast and does not import yfinance/pandas.
    """
    from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook

    from include.ingestion.config import HISTORY_PERIOD, load_tickers
    from include.ingestion.snowflake_loader import load_prices
    from include.ingestion.yahoo_finance import fetch_prices

    df = fetch_prices(load_tickers(), period=HISTORY_PERIOD)
    conn = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID).get_conn()
    try:
        return load_prices(conn, df)  # returned dict is stored as XCom
    finally:
        conn.close()


with DAG(
    dag_id="stock_pipeline",
    description="Daily stock prices: yfinance -> Snowflake -> dbt",
    doc_md=__doc__,
    # 22:00 UTC Mon-Fri = after the 16:00 New York close (also during DST)
    schedule="0 22 * * 1-5",
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,  # each run reloads the full window, so no backfill needed
    max_active_runs=1,
    default_args={
        "owner": "market-lens",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["market-lens", "snowflake", "dbt"],
) as dag:

    extract_load = PythonOperator(
        task_id="extract_load_prices",
        python_callable=extract_load_prices,
    )

    # Credentials reach dbt via the SNOWFLAKE_* env vars from airflow/.env.
    # Artifacts go to /tmp to keep the (mounted) project folder clean.
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            "dbt deps --profiles-dir . && "
            "dbt build --profiles-dir . --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"
        ),
    )

    # Every value in the returned row must be truthy, otherwise the task fails.
    check_marts = SQLCheckOperator(
        task_id="check_marts",
        conn_id=SNOWFLAKE_CONN_ID,
        sql="""
            select
                (select count(*) from STOCKS_DB.MARTS.FCT_DAILY_RETURNS) > 0,
                (select max(price_date) from STOCKS_DB.MARTS.FCT_DAILY_RETURNS)
                    >= dateadd(day, -5, current_date()),
                (select count(*) from STOCKS_DB.MARTS.MART_STOCK_PERFORMANCE)
                    = 7 * (select count(*) from STOCKS_DB.MARTS.DIM_TICKERS)
        """,
    )

    extract_load >> dbt_build >> check_marts
