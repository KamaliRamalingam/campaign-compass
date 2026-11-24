"""Plotly figure builders for the dashboard (PR 5).

Display only: every function takes a table already prepared by
dashboard/data.py and returns a figure. No metric, ratio or label
is computed here. Colours and label text come from
data.LABEL_STYLE, so a label always looks the same and is always
named in text, never shown by colour alone.
"""

import math

import plotly.graph_objects as go

import data as dashboard_data

# Warm spice palette (redesign). Label colours come only from
# data.LABEL_STYLE; the brand green is never used in charts.
TEXT = "#3B2F2A"
GREY = "#7A6B5F"
GRID = "#EADFCF"
NEUTRAL = "#8C6F56"
NEUTRAL_LIGHT = "#D9C8B4"
NAVY = TEXT  # reference lines: charcoal
FONT = "Open Sans, Helvetica, Arial, sans-serif"


def _layout(fig, height=420, legend=True):
    """Shared look: white background, charcoal text, room for labels."""
    fig.update_layout(
        height=height,
        template="plotly_white",
        font={"family": FONT, "color": TEXT, "size": 13},
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=legend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                "xanchor": "left", "x": 0, "title": None},
        hoverlabel={"bgcolor": "white", "font_size": 13},
        legend_traceorder="normal",
    )
    fig.update_xaxes(automargin=True, gridcolor=GRID, zeroline=False,
                     title_font={"color": GREY})
    fig.update_yaxes(automargin=True, gridcolor=GRID, zeroline=False,
                     title_font={"color": GREY})
    return fig


RATIO_CAP = 2.5


def ratio_bar(rows, lines, currency, cap=RATIO_CAP):
    """Ratio to benchmark per judged campaign, as horizontal bars.

    rows: data.ratio_bar_rows (already in the ranked table's order,
    shown top to bottom). lines: data.reference_lines; the dashed
    lines are the threshold ratios from the config (the benchmark
    itself when there are none), each labelled with its cost.
    Bars are coloured by the final label and the label is also
    written after the bar, so colour is never the only cue. A ratio
    above cap is cut at the axis edge, marked with an arrow and its
    real value written. "worsening" follows the value when the label
    comes from the trend override. Linear axis, no log scale.
    """
    fig = go.Figure()
    names = list(rows["campaign"])
    texts = []
    for _, row in rows.iterrows():
        text = f"{row['ratio']:.2f}x · {row['label_text']}"
        if row["over"]:
            text = f"▶ {text}"
        if row["worsening"]:
            text += " · worsening"
        texts.append(text)
    fig.add_trace(go.Bar(
        x=rows["shown"], y=names, orientation="h",
        marker={"color": list(rows["colour"]),
                "line": {"width": 0}},
        text=texts, textposition="outside", cliponaxis=False,
        textfont={"color": TEXT, "size": 12},
        customdata=rows[["label_text", "ratio", "label_period",
                         "cost_per_tracked_action",
                         "benchmark"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>%{customdata[0]}"
            "<br>Ratio to benchmark: %{customdata[1]:.2f}x"
            "<br>Label period: %{customdata[2]}"
            f"<br>Cost per tracked action: %{{customdata[3]:,.2f}} "
            f"{currency}<br>Its benchmark: %{{customdata[4]:,.2f}} "
            f"{currency}<extra></extra>"),
        showlegend=False))
    # One dashed line per distinct threshold ratio from the config.
    drawn = {}
    for _name, ratio, value in lines[1:] or lines[:1]:
        drawn.setdefault(round(ratio, 6), (ratio, value))
    for ratio, value in drawn.values():
        if ratio > cap:
            continue
        fig.add_shape(type="line", x0=ratio, x1=ratio, xref="x",
                      y0=0, y1=1, yref="paper",
                      line={"color": TEXT, "width": 1.2, "dash": "dash"})
        fig.add_annotation(
            x=ratio, xref="x", y=1, yref="paper", yanchor="bottom",
            text=f"{ratio:.1f}x<br>({value:,.2f} {currency})",
            showarrow=False, font={"color": GREY, "size": 11})
    fig.update_xaxes(title="Ratio to benchmark (1.0x = benchmark)",
                     range=[0, cap], dtick=0.5, ticksuffix="x",
                     tickformat=".1f", type="linear")
    fig.update_yaxes(title=None, type="category", autorange="reversed")
    _layout(fig, height=max(240, 46 * len(rows) + 110), legend=False)
    fig.update_layout(margin={"l": 10, "r": 200, "t": 50, "b": 10},
                      bargap=0.35)
    return fig


def trend_line(table, x_field, x_title, currency):
    """Cost per tracked action over time.

    Months with a month_note (partial or lagged) are drawn as
    hollow markers and named on the chart, so they read as
    incomplete without relying on colour.
    """
    fig = go.Figure(go.Scatter(
        x=table[x_field].astype(str), y=table["cost_per_tracked_action"],
        mode="lines+markers", name="Cost per tracked action",
        line={"color": NEUTRAL, "width": 2},
        marker={"size": 9, "color": NEUTRAL},
        customdata=table[["spend", "tracked_actions"]].values,
        hovertemplate=(f"%{{x}}<br>Cost per tracked action: "
                       f"%{{y:,.2f}} {currency}<br>Spend: "
                       f"%{{customdata[0]:,.0f}}<br>Tracked actions: "
                       "%{customdata[1]:,.0f}<extra></extra>")))
    if "month_note" in table.columns:
        flagged = table.loc[table["month_note"] != ""]
        if not flagged.empty:
            fig.add_trace(go.Scatter(
                x=flagged[x_field].astype(str),
                y=flagged["cost_per_tracked_action"],
                mode="markers+text", name="Partial or lagged month",
                text=flagged["month_note"], textposition="top center",
                textfont={"color": GREY, "size": 11},
                marker={"size": 13, "symbol": "circle-open",
                        "color": TEXT, "line": {"width": 2}},
                hovertemplate="%{x}: %{text}<extra></extra>"))
    fig.update_xaxes(title=x_title, type="category")
    fig.update_yaxes(title=f"Cost per tracked action ({currency})",
                     rangemode="tozero")
    return _layout(fig, height=360)


def recent_vs_prior_bar(rows, currency):
    """Prior and recent cost per tracked action per active campaign.

    rows: data.recent_trend_rows. Prior is grey, recent navy; the
    legend names both, so colour is not the only cue.
    """
    fig = go.Figure()
    for column, name, colour in (
            ("prior_cost_per_tracked_action", "Prior window", GRID),
            ("recent_cost_per_tracked_action", "Recent window", NAVY)):
        values = rows[column]
        fig.add_trace(go.Bar(
            x=rows["campaign"], y=values, name=name,
            marker_color=colour,
            marker_line={"color": NAVY, "width": 1},
            text=[f"{value:,.2f}" if value == value else ""
                  for value in values],
            textposition="outside", cliponaxis=False,
            hovertemplate=(f"%{{x}}<br>{name}: %{{y:,.2f}} {currency}"
                           "<extra></extra>")))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title=None, type="category")
    fig.update_yaxes(title=f"Cost per tracked action ({currency})",
                     rangemode="tozero")
    return _layout(fig, height=340)


def weekday_bar(table, currency, highlight=None):
    """Cost per tracked action by weekday, Monday to Sunday."""
    short = str(highlight)[:3] if highlight else None
    colours = [(TEXT if str(day)[:3] == short else NEUTRAL)
               for day in table["weekday"]]
    fig = go.Figure(go.Bar(
        x=table["weekday"], y=table["cost_per_tracked_action"],
        marker_color=colours,
        text=[f"{value:,.2f}" for value in
              table["cost_per_tracked_action"]],
        textposition="outside", cliponaxis=False,
        customdata=table[["tracked_actions", "clicks"]].values,
        hovertemplate=(f"%{{x}}: %{{y:,.2f}} {currency}<br>Tracked "
                       "actions: %{customdata[0]:,.0f}<br>Clicks: "
                       "%{customdata[1]:,.0f}<extra></extra>")))
    fig.update_xaxes(title=None, type="category")
    fig.update_yaxes(title=f"Cost per tracked action ({currency})",
                     rangemode="tozero")
    return _layout(fig, height=340, legend=False)


def share_bar(table, weekday):
    """Each campaign's share of the pooled clicks on one weekday."""
    table = table.sort_values("share_of_weekday_clicks")
    fig = go.Figure(go.Bar(
        x=table["share_of_weekday_clicks"], y=table["campaign"],
        orientation="h", marker_color=NEUTRAL,
        text=[f"{value:.0%}" for value in
              table["share_of_weekday_clicks"]],
        textposition="outside", cliponaxis=False,
        customdata=table[["actions_per_click_vs_baseline"]].values,
        hovertemplate=("%{y}: %{x:.1%} of the clicks<br>Actions per "
                       "click vs baseline: %{customdata[0]:.2f}"
                       "<extra></extra>")))
    fig.update_xaxes(title=f"Share of pooled {weekday} clicks",
                     tickformat=".0%", rangemode="tozero")
    fig.update_yaxes(title=None)
    return _layout(fig, height=max(240, 34 * len(table) + 80),
                   legend=False)


INTENT_COLOURS = {"Directions": "#0072B2", "Calls": "#E69F00",
                  "Store visits": "#009E73"}


def intent_stack(long):
    """Stacked shares of directions, calls and store visits."""
    fig = go.Figure()
    for intent, colour in INTENT_COLOURS.items():
        part = long.loc[long["intent"] == intent]
        if part.empty:
            continue
        fig.add_trace(go.Bar(
            x=part["share"], y=part["campaign"], orientation="h",
            name=intent, marker_color=colour,
            text=[f"{value:.0%}" if value >= 0.08 else ""
                  for value in part["share"]],
            textposition="inside", insidetextanchor="middle",
            hovertemplate=f"%{{y}}<br>{intent}: %{{x:.1%}}<extra></extra>"))
    campaigns = long["campaign"].nunique()
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Share of tracked actions", tickformat=".0%",
                     range=[0, 1])
    fig.update_yaxes(title=None)
    return _layout(fig, height=max(260, 34 * campaigns + 100))
