-- One row per ticker and trading day with the daily return and the drawdown
-- from the all-time (within our history) running peak.

with prices as (

    select
        ticker,
        price_date,
        adj_close,
        close_price,
        volume
    from {{ ref('stg_stock_prices') }}

),

with_windows as (

    select
        *,
        lag(adj_close) over (
            partition by ticker order by price_date
        )                                                   as prev_adj_close,
        max(adj_close) over (
            partition by ticker order by price_date
            rows between unbounded preceding and current row
        )                                                   as running_peak
    from prices

)

select
    ticker,
    price_date,
    adj_close,
    close_price,
    volume,
    adj_close / prev_adj_close - 1      as daily_return,   -- null on a ticker's first day
    running_peak,
    adj_close / running_peak - 1        as drawdown        -- <= 0, 0 = new high
from with_windows
