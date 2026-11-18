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

NAVY = "#1F3A5F"
GREY = "#5B6573"
GRID = "#E6E9EF"
NEUTRAL = "#4C6A92"
FONT = "Source Sans Pro, Helvetica, Arial, sans-serif"


def _layout(fig, height=420, legend=True):
    """Shared look: white background, navy text, room for labels."""
    fig.update_layout(
        height=height,
        template="plotly_white",
        font={"family": FONT, "color": "#1C2430", "size": 13},
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


def bubble_chart(rows, lines, currency):
    """Tracked actions vs cost per tracked action, sized by spend.

    rows: data.bubble_rows. lines: data.reference_lines (the first
    is the benchmark, dashed; the ratio lines are dotted). Each
    bubble names its campaign; hover shows its label period, its
    own benchmark and its ratio.
    """
    fig = go.Figure()
    max_spend = float(rows["label_spend"].max()) if len(rows) else 1.0
    # Alternate name positions over all bubbles, ordered by cost, so
    # names of bubbles close together do not print on each other.
    ordered = rows.sort_values("label_cost_per_tracked_action")["campaign"]
    positions = {name: ("bottom center", "top center")[i % 2]
                 for i, name in enumerate(ordered)}
    for label in dashboard_data.JUDGED_LABELS:
        part = rows.loc[rows["label"] == label].sort_values(
            "label_cost_per_tracked_action")
        if part.empty:
            continue
        style = dashboard_data.LABEL_STYLE[label]
        fig.add_trace(go.Scatter(
            x=part["label_tracked_actions"],
            y=part["label_cost_per_tracked_action"],
            mode="markers+text",
            name=dashboard_data.label_text(label),
            text=part["campaign"],
            textposition=[positions[name] for name in part["campaign"]],
            textfont={"size": 12, "color": "#1C2430"},
            cliponaxis=False,
            marker={
                "size": part["label_spend"],
                "sizemode": "area",
                "sizeref": 2.0 * max_spend / (60.0 ** 2),
                "sizemin": 8,
                "color": style["colour"],
                "symbol": style["marker"],
                "opacity": 0.85,
                "line": {"width": 1.5, "color": "white"},
            },
            customdata=part[["label_text", "label_period", "label_spend",
                             "label_benchmark", "label_ratio",
                             "status_now"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>%{customdata[0]} · %{customdata[5]}"
                "<br>Label period: %{customdata[1]}"
                "<br>Tracked actions: %{x:,.0f}"
                f"<br>Cost per tracked action: %{{y:,.2f}} {currency}"
                f"<br>Spend: %{{customdata[2]:,.0f}} {currency}"
                f"<br>Its benchmark: %{{customdata[3]:,.2f}} {currency}"
                "<br>Ratio to benchmark: %{customdata[4]:.2f}x"
                "<extra></extra>"),
        ))
    # The benchmark line is also the 1.0x line: name it once.
    drawn = []
    for name, ratio, value in lines:
        if drawn and abs(value - drawn[0][2]) < 1e-9:
            drawn[0] = (f"{drawn[0][0]} = {name.lower()}", 1.0, value)
            continue
        drawn.append((name, ratio, value))
    # Log axes: one campaign far above the benchmark must not squash
    # the rest; equal steps on the y axis are equal ratios. Ranges
    # are set explicitly (in log10 units) so the lines always show.
    xs = list(rows["label_tracked_actions"]) or [1.0]
    ys = list(rows["label_cost_per_tracked_action"]) + [
        value for _name, _ratio, value in drawn]
    x_range = [math.log10(min(xs) / 2.0), math.log10(max(xs) * 3.0)]
    y_range = [math.log10(min(ys) / 1.6), math.log10(max(ys) * 1.6)]
    x_line = [10 ** x_range[0], 10 ** x_range[1]]
    for index, (name, _ratio, value) in enumerate(drawn):
        colour = NAVY if index == 0 else GREY
        fig.add_trace(go.Scatter(
            x=x_line, y=[value, value], mode="lines",
            line={"color": colour, "width": 1.5,
                  "dash": "dash" if index == 0 else "dot"},
            showlegend=False, hoverinfo="skip"))
        # On a log axis an annotation's y is given in log10 units.
        fig.add_annotation(
            x=0.01, xref="paper", y=math.log10(value), yref="y",
            text=f"{name}: {value:,.2f} {currency}", showarrow=False,
            xanchor="left", yanchor="bottom",
            font={"color": colour, "size": 12},
            bgcolor="rgba(255,255,255,0.85)")
    fig.update_xaxes(title="Tracked actions in the label period (log)",
                     type="log", range=x_range)
    fig.update_yaxes(title=f"Cost per tracked action ({currency}, log)",
                     type="log", range=y_range)
    return _layout(fig, height=520)


def label_count_bar(counts):
    """Horizontal bar of judged label counts (data.judged_label_counts)."""
    fig = go.Figure(go.Bar(
        x=counts["campaigns"], y=counts["label_text"], orientation="h",
        marker_color=counts["colour"], text=counts["campaigns"],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x} campaigns<extra></extra>"))
    fig.update_xaxes(title="Campaigns", dtick=1, rangemode="tozero")
    fig.update_yaxes(title=None, autorange="reversed")
    return _layout(fig, height=260, legend=False)


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
                        "color": "#D55E00", "line": {"width": 2}},
                hovertemplate="%{x}: %{text}<extra></extra>"))
    fig.update_xaxes(title=x_title, type="category")
    fig.update_yaxes(title=f"Cost per tracked action ({currency})",
                     rangemode="tozero")
    return _layout(fig, height=360)


def weekday_bar(table, currency, highlight=None):
    """Cost per tracked action by weekday, Monday to Sunday."""
    short = str(highlight)[:3] if highlight else None
    colours = [("#D55E00" if str(day)[:3] == short else NEUTRAL)
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
