"""Load: upsert price rows into ``STOCKS_DB.RAW.STOCK_PRICES_DAILY``.

Strategy (idempotent, safe to re-run):
1. ``write_pandas`` the DataFrame into a session-scoped TEMPORARY table.
2. ``MERGE`` it into the RAW table on (TICKER, PRICE_DATE): update existing rows
   (adjusted prices may have been restated) and insert new trading days.
"""

import logging
import uuid

import pandas as pd
from snowflake.connector import SnowflakeConnection
from snowflake.connector.pandas_tools import write_pandas

from include.ingestion.config import RAW_DATABASE, RAW_SCHEMA, RAW_TABLE, SOURCE_NAME

log = logging.getLogger(__name__)

MERGE_SQL = """
MERGE INTO {target} AS t
USING (
    SELECT
        TICKER::VARCHAR(10)        AS TICKER,
        PRICE_DATE::DATE           AS PRICE_DATE,
        OPEN::NUMBER(18, 6)        AS OPEN,
        HIGH::NUMBER(18, 6)        AS HIGH,
        LOW::NUMBER(18, 6)         AS LOW,
        CLOSE::NUMBER(18, 6)       AS CLOSE,
        ADJ_CLOSE::NUMBER(18, 6)   AS ADJ_CLOSE,
        VOLUME::NUMBER(38, 0)      AS VOLUME
    FROM {staging}
) AS s
ON t.TICKER = s.TICKER AND t.PRICE_DATE = s.PRICE_DATE
WHEN MATCHED THEN UPDATE SET
    OPEN = s.OPEN, HIGH = s.HIGH, LOW = s.LOW, CLOSE = s.CLOSE,
    ADJ_CLOSE = s.ADJ_CLOSE, VOLUME = s.VOLUME,
    SOURCE = %(source)s, LOADED_AT = SYSDATE()
WHEN NOT MATCHED THEN INSERT
    (TICKER, PRICE_DATE, OPEN, HIGH, LOW, CLOSE, ADJ_CLOSE, VOLUME, SOURCE, LOADED_AT)
VALUES
    (s.TICKER, s.PRICE_DATE, s.OPEN, s.HIGH, s.LOW, s.CLOSE, s.ADJ_CLOSE, s.VOLUME,
     %(source)s, SYSDATE())
"""


def load_prices(conn: SnowflakeConnection, df: pd.DataFrame) -> dict[str, int]:
    """Upsert ``df`` into the RAW table and return the MERGE row counts."""
    if df.empty:
        raise ValueError("Refusing to load an empty DataFrame")

    staging_table = f"STOCK_PRICES_STAGE_{uuid.uuid4().hex[:8].upper()}"
    # Dates as ISO strings -> VARCHAR in the temp table, cast to DATE in the MERGE.
    # This avoids parquet timestamp/date conversion surprises in write_pandas.
    upload = df.assign(PRICE_DATE=df["PRICE_DATE"].astype(str))

    cur = conn.cursor()
    try:
        cur.execute(f"USE SCHEMA {RAW_DATABASE}.{RAW_SCHEMA}")
        success, _, n_rows, _ = write_pandas(
            conn,
            upload,
            table_name=staging_table,
            database=RAW_DATABASE,
            schema=RAW_SCHEMA,
            auto_create_table=True,
            table_type="temporary",
            quote_identifiers=False,  # keep column names unquoted/uppercase
        )
        if not success:
            raise RuntimeError("write_pandas reported a failed upload")
        log.info("Staged %d rows in temporary table %s", n_rows, staging_table)

        cur.execute(
            MERGE_SQL.format(
                target=f"{RAW_DATABASE}.{RAW_SCHEMA}.{RAW_TABLE}",
                staging=f"{RAW_DATABASE}.{RAW_SCHEMA}.{staging_table}",
            ),
            {"source": SOURCE_NAME},
        )
        inserted, updated = cur.fetchone()
        log.info("MERGE done: %d inserted, %d updated", inserted, updated)
        return {"staged": n_rows, "inserted": inserted, "updated": updated}
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {RAW_DATABASE}.{RAW_SCHEMA}.{staging_table}")
        cur.close()
