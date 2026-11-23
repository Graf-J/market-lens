-- Cleaned, consistently typed daily prices: the single entry point to the raw data.
-- One row per ticker and trading day.

with source as (

    select * from {{ source('raw', 'stock_prices_daily') }}

),

cleaned as (

    select
        upper(trim(ticker))                 as ticker,
        price_date::date                    as price_date,
        open::number(18, 6)                 as open_price,
        high::number(18, 6)                 as high_price,
        low::number(18, 6)                  as low_price,
        close::number(18, 6)                as close_price,
        adj_close::number(18, 6)            as adj_close,
        volume::number(38, 0)               as volume,
        loaded_at                           as loaded_at
    from source
    -- a day without a valid (positive) adjusted close is unusable for returns
    where adj_close is not null
      and adj_close > 0

)

select * from cleaned
