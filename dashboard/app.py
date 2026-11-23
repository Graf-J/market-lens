"""market-lens: Streamlit dashboard on top of the dbt marts in Snowflake.

Run from the ``dashboard/`` folder:

    uv run streamlit run app.py
"""

import pandas as pd
import streamlit as st

import charts
import queries

st.set_page_config(page_title="market-lens", page_icon=":chart_with_upwards_trend:", layout="wide")

PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y"]
DEFAULT_SELECTION = ["AAPL", "NVDA", "KO"]
BENCHMARK = charts.BENCHMARK

# ---------------------------------------------------------------- data
tickers = queries.load_tickers()
performance = queries.load_performance().merge(
    tickers[["ticker", "company_name", "sector"]], on="ticker", how="left"
)
daily = queries.load_daily_prices()
last_loaded = queries.load_last_loaded_at()

stock_options = tickers.loc[~tickers["is_benchmark"], "ticker"].tolist()
names = dict(zip(tickers["ticker"], tickers["company_name"]))
pal = charts.PALETTES["dark" if st.context.theme.type == "dark" else "light"]

# ---------------------------------------------------------------- header
st.title("market-lens")
as_of = performance["end_date"].max()
st.caption(
    f"Performance and risk of {len(stock_options)} large US stocks vs. the S&P 500 · "
    f"prices through **{as_of:%b %d, %Y}** · last pipeline load {last_loaded:%Y-%m-%d %H:%M} UTC · "
    "source: Yahoo Finance → Snowflake → dbt"
)

# ---------------------------------------------------------------- filters (one row, above all charts)
col_stocks, col_period, col_bench = st.columns([5, 3, 1.4], vertical_alignment="bottom")
selected = col_stocks.multiselect(
    "Stocks",
    options=stock_options,
    default=DEFAULT_SELECTION,
    max_selections=charts.MAX_SERIES,
    format_func=lambda t: f"{t} · {names[t]}",
    placeholder="Pick up to 8 stocks",
)
period = col_period.segmented_control("Period", PERIODS, default="1Y", required=True)
show_benchmark = col_bench.toggle("S&P 500", value=True, help="Show SPY as a gray benchmark line")

if not selected:
    st.info("Select at least one stock to compare.")
    st.stop()

# Colour slots persist across reruns so a stock keeps its colour when others change.
st.session_state["slots"] = charts.assign_color_slots(selected, st.session_state.get("slots", {}))
slots = st.session_state["slots"]

plotted = selected + ([BENCHMARK] if show_benchmark else [])
perf_period = performance[performance["period"] == period]
start_dates = perf_period.set_index("ticker")["start_date"].to_dict()

# ---------------------------------------------------------------- 1. KPI table
st.subheader(f"Key metrics · {period}")
spy_return = perf_period.loc[perf_period["ticker"] == BENCHMARK, "total_return"].iloc[0]
table = pd.concat([
    perf_period[perf_period["ticker"].isin(selected)].sort_values("total_return", ascending=False),
    perf_period[perf_period["ticker"] == BENCHMARK],  # benchmark always as the reference row
]).assign(vs_benchmark=lambda d: (d["total_return"] - spy_return) * 100)
st.dataframe(
    table[["ticker", "company_name", "sector", "total_return", "vs_benchmark",
           "annualized_volatility", "max_drawdown", "start_date"]],
    hide_index=True,
    width="stretch",
    column_config={
        "ticker": st.column_config.TextColumn("Ticker"),
        "company_name": st.column_config.TextColumn("Company"),
        "sector": st.column_config.TextColumn("Sector"),
        "total_return": st.column_config.NumberColumn("Total return", format="percent",
                                                      help="Change of the adjusted close over the period (dividends included)"),
        "vs_benchmark": st.column_config.NumberColumn("vs. S&P 500", format="%+.1f pp",
                                                      help="Total return minus SPY's total return, in percentage points"),
        "annualized_volatility": st.column_config.NumberColumn("Volatility", format="percent",
                                                               help="Std. dev. of daily returns × √252"),
        "max_drawdown": st.column_config.NumberColumn("Max drawdown", format="percent",
                                                      help="Largest drop from a peak within the period"),
        "start_date": st.column_config.DateColumn("Since", format="MMM D, YYYY"),
    },
)

# ---------------------------------------------------------------- 2. price development
st.subheader("How did they move?")
tab_perf, tab_dd = st.tabs(["Growth of 100", "Drawdown"])
with tab_perf:
    st.caption("Adjusted prices indexed to 100 at the start of the period. "
               "A value of 130 means +30% since then.")
    st.plotly_chart(charts.performance_chart(daily, plotted, start_dates, slots, pal),
                    theme=None, width="stretch")
with tab_dd:
    st.caption("How far each stock is below its highest price within the period. 0% = at a new high.")
    st.plotly_chart(charts.drawdown_chart(daily, plotted, start_dates, slots, pal),
                    theme=None, width="stretch")

# ---------------------------------------------------------------- 3. risk vs. return
st.subheader("Was the return worth the risk?")
st.caption("All tracked stocks for the period. Up-and-left is better: more return for less volatility. "
           "Selected stocks are highlighted in their line colour; SPY is the gray diamond.")
st.plotly_chart(charts.risk_return_scatter(perf_period, selected, slots, pal),
                theme=None, width="stretch")
