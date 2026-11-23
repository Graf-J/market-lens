-- A drawdown is the % distance below a previous peak, so it must lie in [-1, 0].
-- Any returned row is a failure.

select 'fct_daily_returns' as model, ticker, price_date::varchar as grain, drawdown as value
from {{ ref('fct_daily_returns') }}
where drawdown < -1 or drawdown > 0

union all

select 'mart_stock_performance', ticker, period, max_drawdown
from {{ ref('mart_stock_performance') }}
where max_drawdown < -1 or max_drawdown > 0
