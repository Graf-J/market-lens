-- =============================================================================
-- market-lens | One-time Snowflake setup
-- -----------------------------------------------------------------------------
-- Run once in a Snowflake worksheet (as ACCOUNTADMIN) before the first pipeline
-- run. Creates the database, the three layer schemas and the raw landing table.
--
--   RAW      <- written by the Python loader (Airflow task `load_raw`)
--   STAGING  <- dbt staging views + seeds
--   MARTS    <- dbt fact / mart tables queried by Streamlit
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE COMPUTE_WH;

CREATE DATABASE IF NOT EXISTS STOCKS_DB
    COMMENT = 'market-lens: daily stock prices and performance/risk metrics';

CREATE SCHEMA IF NOT EXISTS STOCKS_DB.RAW
    COMMENT = 'Raw landing zone, loaded by the Python/Airflow ingestion';
CREATE SCHEMA IF NOT EXISTS STOCKS_DB.STAGING
    COMMENT = 'dbt staging models (cleaned, typed views) and seeds';
CREATE SCHEMA IF NOT EXISTS STOCKS_DB.MARTS
    COMMENT = 'dbt marts consumed by the Streamlit dashboard';

-- -----------------------------------------------------------------------------
-- Raw daily OHLCV prices from Yahoo Finance (one row per ticker and trading day)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS STOCKS_DB.RAW.STOCK_PRICES_DAILY (
    TICKER      VARCHAR(10)    NOT NULL COMMENT 'Ticker symbol, e.g. AAPL',
    PRICE_DATE  DATE           NOT NULL COMMENT 'Trading day (exchange local date)',
    OPEN        NUMBER(18, 6)           COMMENT 'Opening price (unadjusted)',
    HIGH        NUMBER(18, 6)           COMMENT 'Intraday high (unadjusted)',
    LOW         NUMBER(18, 6)           COMMENT 'Intraday low (unadjusted)',
    CLOSE       NUMBER(18, 6)           COMMENT 'Closing price (unadjusted)',
    ADJ_CLOSE   NUMBER(18, 6)           COMMENT 'Close adjusted for splits and dividends; basis for returns',
    VOLUME      NUMBER(38, 0)           COMMENT 'Shares traded',
    SOURCE      VARCHAR(50)    NOT NULL COMMENT 'Data source, always yfinance',
    LOADED_AT   TIMESTAMP_NTZ  NOT NULL COMMENT 'UTC timestamp of the load that last wrote this row',
    -- Snowflake does not enforce PKs; it documents the grain. Uniqueness is
    -- guaranteed by the MERGE in the loader and tested in dbt.
    CONSTRAINT PK_STOCK_PRICES_DAILY PRIMARY KEY (TICKER, PRICE_DATE)
)
COMMENT = 'Daily OHLCV prices from Yahoo Finance (yfinance), upserted on (TICKER, PRICE_DATE)';

-- Quick check after the first load:
-- SELECT TICKER, COUNT(*) AS ROWS, MIN(PRICE_DATE), MAX(PRICE_DATE), MAX(LOADED_AT)
-- FROM STOCKS_DB.RAW.STOCK_PRICES_DAILY GROUP BY TICKER ORDER BY TICKER;
