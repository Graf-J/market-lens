-- One row per tracked ticker: descriptive attributes from the seed plus the
-- date range of price data we actually have.

with tickers as (

    select * from {{ ref('tickers') }}

),

coverage as (

    select
        ticker,
        min(price_date) as first_price_date,
        max(price_date) as last_price_date,
        count(*)        as trading_days
    from {{ ref('stg_stock_prices') }}
    group by ticker

)

select
    t.ticker,
    t.company_name,
    t.sector,
    t.is_benchmark,
    c.first_price_date,
    c.last_price_date,
    c.trading_days
from tickers as t
left join coverage as c
    on t.ticker = c.ticker
