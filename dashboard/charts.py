"""Plotly figure builders and the colour system.

Colour rules (validated with the dataviz palette validator):
* Each selected stock gets a categorical slot in fixed order and keeps it while
  it stays selected (colour follows the entity, never its rank).
* The SPY benchmark is always neutral gray, never a categorical colour.
* Light and dark mode use their own validated steps of the same eight hues.
"""

import pandas as pd
import plotly.graph_objects as go

MAX_SERIES = 8

PALETTES = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                   "#e87ba4", "#008300", "#6250d6", "#e34948"],
        "ink": "#0b0b0b", "ink_2": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500",
                   "#d55181", "#0ca30c", "#9085e9", "#e66767"],
        "ink": "#f0efec", "ink_2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835", "surface": "#1a1a19",
    },
}
BENCHMARK = "SPY"


def assign_color_slots(selected: list[str], slots: dict[str, int]) -> dict[str, int]:
    """Keep existing ticker->slot assignments; give new tickers the lowest free slot."""
    kept = {t: s for t, s in slots.items() if t in selected}
    free = [s for s in range(MAX_SERIES) if s not in kept.values()]
    for t in selected:
        if t not in kept:
            kept[t] = free.pop(0)
    return kept


def color_for(ticker: str, slots: dict[str, int], pal: dict) -> str:
    return pal["muted"] if ticker == BENCHMARK else pal["series"][slots[ticker]]


def _base_layout(fig: go.Figure, pal: dict, *, y_title: str, y_format: str, height: int = 420) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=72, r=64, t=8, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=pal["ink_2"], size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None, font=dict(color=pal["ink_2"])),
        hoverlabel=dict(font_family='system-ui, -apple-system, "Segoe UI", sans-serif'),
    )
    fig.update_xaxes(showgrid=False, linecolor=pal["axis"], tickfont=dict(color=pal["muted"]), title=None, automargin=True)
    fig.update_yaxes(
        gridcolor=pal["grid"], gridwidth=1, zeroline=False, linecolor=pal["axis"],
        tickfont=dict(color=pal["muted"]), tickformat=y_format,
        title=dict(text=y_title, font=dict(color=pal["muted"], size=12), standoff=12),
        automargin=True,
    )
    return fig


def _end_labels(fig: go.Figure, series: dict[str, pd.DataFrame], y_col: str, pal: dict) -> None:
    """Direct-label the line ends with the ticker (only when <= 4 series; the legend covers the rest).

    Labels closer than ~5% of the y-range are pushed apart so they never overlap.
    """
    if not series or len(series) > 4:
        return
    ends = sorted(((df.iloc[-1][y_col], t, df.iloc[-1]["price_date"]) for t, df in series.items()))
    all_y = pd.concat([df[y_col] for df in series.values()])
    min_gap = (all_y.max() - all_y.min()) * 0.05
    placed: list[float] = []
    for y, ticker, x in ends:
        label_y = max(y, placed[-1] + min_gap) if placed else y
        placed.append(label_y)
        fig.add_annotation(
            x=x, y=label_y, text=f"<b>{ticker}</b>", showarrow=False,
            xanchor="left", xshift=6, font=dict(color=pal["ink"], size=12),
        )


def _period_slices(daily: pd.DataFrame, tickers: list[str], start_dates: dict[str, pd.Timestamp]) -> dict[str, pd.DataFrame]:
    out = {}
    for t in tickers:
        df = daily[(daily["ticker"] == t) & (daily["price_date"] >= start_dates[t])]
        if not df.empty:
            out[t] = df.copy()
    return out


def performance_chart(daily, tickers, start_dates, slots, pal) -> go.Figure:
    """Prices indexed to 100 at the start of the period, so stocks of any price level compare."""
    series = _period_slices(daily, tickers, start_dates)
    fig = go.Figure()
    for t, df in series.items():
        df["indexed"] = df["adj_close"] / df["adj_close"].iloc[0] * 100
        series[t] = df
        fig.add_trace(go.Scatter(
            x=df["price_date"], y=df["indexed"], name=t, mode="lines",
            line=dict(color=color_for(t, slots, pal), width=2),
            hovertemplate=f"{t}: %{{y:.1f}}<extra></extra>",
        ))
    fig.add_hline(y=100, line=dict(color=pal["axis"], width=1))
    _end_labels(fig, series, "indexed", pal)
    _base_layout(fig, pal, y_title="Value of 100 invested", y_format=".0f")
    fig.update_layout(hovermode="x unified")
    return fig


def drawdown_chart(daily, tickers, start_dates, slots, pal) -> go.Figure:
    """Distance below the running peak within the selected period ("underwater" chart)."""
    series = _period_slices(daily, tickers, start_dates)
    fig = go.Figure()
    for t, df in series.items():
        df["drawdown"] = df["adj_close"] / df["adj_close"].cummax() - 1
        series[t] = df
        fig.add_trace(go.Scatter(
            x=df["price_date"], y=df["drawdown"], name=t, mode="lines",
            line=dict(color=color_for(t, slots, pal), width=2),
            hovertemplate=f"{t}: %{{y:.1%}}<extra></extra>",
        ))
    fig.add_hline(y=0, line=dict(color=pal["axis"], width=1))
    _end_labels(fig, series, "drawdown", pal)
    _base_layout(fig, pal, y_title="Below previous peak", y_format=".0%")
    fig.update_layout(hovermode="x unified")
    return fig


def risk_return_scatter(perf: pd.DataFrame, selected: list[str], slots, pal) -> go.Figure:
    """All stocks for the period: x = volatility, y = total return.

    Unselected stocks are gray context; selected ones carry their line-chart colour.
    Every point is labelled with its ticker, so identity never relies on colour alone.
    """
    fig = go.Figure()
    groups = [
        ("Other stocks", perf[~perf["ticker"].isin(selected) & (perf["ticker"] != BENCHMARK)], None),
        ("S&P 500 (SPY)", perf[perf["ticker"] == BENCHMARK], None),
    ]
    for name, df, _ in groups:
        if df.empty:
            continue
        is_bench = name.startswith("S&P")
        fig.add_trace(go.Scatter(
            x=df["annualized_volatility"], y=df["total_return"], mode="markers+text", name=name,
            text=df["ticker"], textposition="top center",
            textfont=dict(color=pal["ink_2"] if is_bench else pal["muted"], size=11),
            marker=dict(size=10, color=pal["muted"], symbol="diamond" if is_bench else "circle",
                        opacity=1 if is_bench else 0.55, line=dict(color=pal["surface"], width=2)),
            customdata=df[["company_name", "max_drawdown"]],
            hovertemplate=("<b>%{text}</b> · %{customdata[0]}<br>Return %{y:.1%}<br>"
                           "Volatility %{x:.1%}<br>Max drawdown %{customdata[1]:.1%}<extra></extra>"),
        ))
    for t in selected:
        df = perf[perf["ticker"] == t]
        if df.empty:
            continue
        fig.add_trace(go.Scatter(
            x=df["annualized_volatility"], y=df["total_return"], mode="markers+text", name=t,
            text=df["ticker"], textposition="top center", textfont=dict(color=pal["ink"], size=12),
            marker=dict(size=13, color=color_for(t, slots, pal), line=dict(color=pal["surface"], width=2)),
            customdata=df[["company_name", "max_drawdown"]],
            hovertemplate=("<b>%{text}</b> · %{customdata[0]}<br>Return %{y:.1%}<br>"
                           "Volatility %{x:.1%}<br>Max drawdown %{customdata[1]:.1%}<extra></extra>"),
        ))
    fig.add_hline(y=0, line=dict(color=pal["axis"], width=1))
    _base_layout(fig, pal, y_title="Total return", y_format=".0%", height=440)
    fig.update_xaxes(tickformat=".0%", title=dict(text="Annualized volatility (risk)", font=dict(color=pal["muted"], size=12)))
    fig.update_layout(hovermode="closest", margin=dict(l=72, r=24, t=8, b=48))
    return fig
