-- One row per ticker and look-back period with return and risk metrics.
-- Periods are anchored on the latest trading day in the data (as_of_date);
-- each period starts on the first trading day on or after its start date.

{% set periods = [
    ("1M",  1, "dateadd(month, -1, as_of_date)"),
    ("3M",  2, "dateadd(month, -3, as_of_date)"),
    ("6M",  3, "dateadd(month, -6, as_of_date)"),
    ("YTD", 4, "dateadd(day, -1, date_trunc('year', as_of_date))"),
    ("1Y",  5, "dateadd(year, -1, as_of_date)"),
    ("3Y",  6, "dateadd(year, -3, as_of_date)"),
    ("5Y",  7, "dateadd(year, -5, as_of_date)"),
] %}

with daily as (

    select ticker, price_date, adj_close, daily_return
    from {{ ref('fct_daily_returns') }}

),

as_of as (

    select max(price_date) as as_of_date from daily

),

periods as (

    {% for name, sort, start_expr in periods %}
    select '{{ name }}' as period, {{ sort }} as period_order, {{ start_expr }}::date as period_start
    from as_of
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

in_period as (

    select
        p.period,
        p.period_order,
        d.ticker,
        d.price_date,
        d.adj_close,
        d.daily_return,
        -- running peak restarts at the beginning of every period
        max(d.adj_close) over (
            partition by d.ticker, p.period order by d.price_date
            rows between unbounded preceding and current row
        )                                                           as period_peak,
        row_number() over (
            partition by d.ticker, p.period order by d.price_date
        )                                                           as day_in_period
    from daily as d
    inner join periods as p
        on d.price_date >= p.period_start

),

aggregated as (

    select
        ticker,
        period,
        period_order,
        min(price_date)                                     as start_date,
        max(price_date)                                     as end_date,
        count(*)                                            as trading_days,
        min_by(adj_close, price_date)                       as start_price,
        max_by(adj_close, price_date)                       as end_price,
        -- the first day's return points to a day outside the period -> exclude it
        stddev_samp(iff(day_in_period > 1, daily_return, null)) * sqrt(252)
                                                            as annualized_volatility,
        min(adj_close / period_peak - 1)                    as max_drawdown
    from in_period
    group by ticker, period, period_order

)

select
    ticker,
    period,
    period_order,
    start_date,
    end_date,
    trading_days,
    start_price,
    end_price,
    end_price / start_price - 1     as total_return,
    annualized_volatility,
    max_drawdown
from aggregated
