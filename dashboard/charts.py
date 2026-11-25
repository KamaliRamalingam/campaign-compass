"""Plotly figure builders for the dashboard (PR 5).

Display only: every function takes a table already prepared by
dashboard/data.py and returns a figure. No metric, ratio or label
is computed here. Colours and label text come from
data.LABEL_STYLE, so a label always looks the same and is always
named in text, never shown by colour alone.
"""

import html

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


def _safe(values):
    """Data text for Plotly (which renders some HTML): escaped."""
    return [html.escape(str(value)) for value in values]


def _wrapped(values, width=16):
    """Escaped names, long ones split over two lines at a space, so
    the axis labels leave room for the bars on narrow screens."""
    out = []
    for value in _safe(values):
        if len(value) > width and " " in value:
            middle = len(value) // 2
            spaces = [i for i, char in enumerate(value) if char == " "]
            cut = min(spaces, key=lambda i: abs(i - middle))
            value = value[:cut] + "<br>" + value[cut + 1:]
        out.append(value)
    return out


# Overall chart scale (with the --cc-s CSS scale in dashboard/app.py):
# every chart height goes through _layout, so this one number sizes
# them all. 0.88 = about 12% smaller than the original design.
CHART_SCALE = 0.88
CHART_FONT = 12  # px; no chart text is smaller


def _layout(fig, height=420, legend=True):
    """Shared look: white background, charcoal text, room for labels.
    The height is scaled by CHART_SCALE."""
    fig.update_layout(
        height=round(height * CHART_SCALE),
        template="plotly_white",
        font={"family": FONT, "color": TEXT, "size": CHART_FONT},
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=legend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                "xanchor": "left", "x": 0, "title": None,
                "font": {"size": CHART_FONT}},
        hoverlabel={"bgcolor": "white", "font_size": CHART_FONT},
        legend_traceorder="normal",
    )
    # Explicit sizes: Streamlit's chart theme sizes ticks in rem, which
    # would follow the smaller root font below 12px.
    axis = {"automargin": True, "gridcolor": GRID, "zeroline": False,
            "title_font": {"color": GREY, "size": CHART_FONT},
            "tickfont": {"size": CHART_FONT}}
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
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
    names = _wrapped(rows["campaign"])
    texts = []
    for _, row in rows.iterrows():
        text = f"{row['ratio']:.2f}x · {html.escape(row['label_text'])}"
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
        textfont={"color": TEXT, "size": CHART_FONT},
        customdata=list(zip(
            _safe(rows["label_text"]), rows["ratio"],
            _safe(rows["label_period"]), rows["cost_per_tracked_action"],
            rows["benchmark"])),
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
            text=f"{ratio:.1f}x<br>{value:,.2f}<br>{currency}",
            showarrow=False, font={"color": GREY, "size": CHART_FONT})
    fig.update_xaxes(title="Ratio to benchmark (1.0x = benchmark)",
                     range=[0, cap], dtick=0.5, ticksuffix="x",
                     tickformat=".1f", type="linear")
    fig.update_yaxes(title=None, type="category", autorange="reversed")
    _layout(fig, height=max(240, 46 * len(rows) + 110), legend=False)
    fig.update_layout(margin={"l": 10, "r": 170, "t": 50, "b": 10},
                      bargap=0.35)
    fig.update_xaxes(tickangle=0)
    return fig


def trend_line(table, x_field, x_title, currency, height=360,
               freq="MS"):
    """Cost per tracked action over time, on a date axis.

    The table gets a real date per period and an empty row for each
    missing month (freq "MS") or week (freq "W-MON"), so the line
    breaks across gaps. Months with a month_note (partial or lagged)
    are drawn as hollow rings and named on the chart, so they read
    as incomplete without relying on colour.
    """
    table = dashboard_data.with_period_gaps(table, x_field, freq)
    notes = (table["month_note"].fillna("")
             if "month_note" in table.columns else [""] * len(table))
    # A flagged month has no filled dot: only the hollow ring below.
    fill = ["rgba(0,0,0,0)" if note else NEUTRAL for note in notes]
    extra = [column for column in ("spend", "tracked_actions")
             if column in table.columns]
    fig = go.Figure(go.Scatter(
        x=table["period_date"], y=table["cost_per_tracked_action"],
        mode="lines+markers", name="Cost per tracked action",
        connectgaps=False,
        line={"color": NEUTRAL, "width": 2},
        marker={"size": 9, "color": fill, "line": {"width": 0}},
        customdata=table[extra].values if len(extra) == 2 else None,
        hovertemplate=(f"%{{x|{'%b %Y' if freq == 'MS' else '%d %b %Y'}}}"
                       f"<br>Cost per tracked action: %{{y:,.2f}} "
                       f"{currency}<br>Spend: %{{customdata[0]:,.0f}}"
                       "<br>Tracked actions: %{customdata[1]:,.0f}"
                       "<extra></extra>")))
    if "month_note" in table.columns:
        flagged = table.loc[table["month_note"].fillna("") != ""]
        if not flagged.empty:
            fig.add_trace(go.Scatter(
                x=flagged["period_date"],
                y=flagged["cost_per_tracked_action"],
                mode="markers+text", name="Partial or lagged month",
                text=flagged["month_note"], textposition="top center",
                textfont={"color": GREY, "size": CHART_FONT}, cliponaxis=False,
                marker={"size": 12, "symbol": "circle-open",
                        "color": TEXT, "line": {"width": 2}},
                hovertemplate="%{x|%b %Y}: %{text}<extra></extra>"))
    # One tick per month (or per 3, 6, 12 months on long ranges), so
    # a month label is never repeated.
    dtick = None
    if freq == "MS" and table["period_date"].notna().any():
        months = len(table)
        dtick = ("M1" if months <= 12 else "M3" if months <= 36
                 else "M6" if months <= 72 else "M12")
    fig.update_xaxes(title=x_title, type="date", dtick=dtick,
                     tickformat="%b %Y" if freq == "MS" else "%d %b %Y")
    values = table["cost_per_tracked_action"].dropna()
    top = float(values.max()) * 1.2 if len(values) else None
    fig.update_yaxes(title=f"Cost per tracked action ({currency})",
                     rangemode="tozero",
                     range=[0, top] if top else None)
    return _layout(fig, height=height)


def weekday_bar(table, currency, highlight=None, note=None):
    """Cost per tracked action by weekday, Monday to Sunday.

    All bars in the neutral colour with value labels; no good or bad
    colours. The busiest weekday (highlight), and the cheapest and
    most expensive weekdays, get a dark outline; when given, the note
    is written above the highlighted weekday (for example "most
    pooled clicks").
    """
    short = str(highlight)[:3] if highlight is not None else None
    highlighted = [str(day)[:3] == short for day in table["weekday"]]
    costs = table["cost_per_tracked_action"]
    cheapest = costs == costs.min()
    dearest = costs == costs.max()
    marked = [h or lo or hi for h, lo, hi in
              zip(highlighted, cheapest, dearest)]
    fig = go.Figure(go.Bar(
        x=table["weekday"], y=table["cost_per_tracked_action"],
        marker={"color": NEUTRAL,
                "line": {"color": [TEXT if mark else NEUTRAL
                                   for mark in marked],
                         "width": [2.5 if mark else 0
                                   for mark in marked]}},
        text=[f"{value:,.2f}" for value in
              table["cost_per_tracked_action"]],
        textposition="outside", cliponaxis=False,
        textfont={"color": TEXT},
        customdata=table[["tracked_actions", "clicks"]].values,
        hovertemplate=(f"%{{x}}: %{{y:,.2f}} {currency}<br>Tracked "
                       "actions: %{customdata[0]:,.0f}<br>Clicks: "
                       "%{customdata[1]:,.0f}<extra></extra>")))
    if note and any(highlighted):
        row = table.loc[highlighted].iloc[0]
        fig.add_annotation(
            x=row["weekday"], y=row["cost_per_tracked_action"],
            text=note, showarrow=False, yshift=34,
            font={"color": TEXT, "size": CHART_FONT},
            bgcolor="#FBF6EE", bordercolor=TEXT, borderwidth=1,
            borderpad=3)
    fig.update_xaxes(title=None, type="category")
    fig.update_yaxes(title=f"Cost per tracked action ({currency})",
                     rangemode="tozero")
    return _layout(fig, height=340, legend=False)


def share_bar(table, weekday):
    """Each campaign's share of the pooled clicks on one weekday."""
    table = table.sort_values("share_of_weekday_clicks")
    fig = go.Figure(go.Bar(
        x=table["share_of_weekday_clicks"], y=_safe(table["campaign"]),
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


# Segment labels under this share are hidden (they do not fit).
INTENT_LABEL_MIN = 0.05
# A brown family (no red, amber or green: those are for labels only),
# dark to light. The share inside each bar is white on the dark bar
# and near-black brown on the lighter ones, all at least 4.5:1
# (white on #6B5240 7.2:1; #1E1713 on #A68A6D 5.5:1, on #D9C7B0 10.7:1).
INTENT_COLOURS = {"Directions": "#6B5240", "Calls": "#A68A6D",
                  "Store visits": "#D9C7B0"}
INTENT_TEXT = {"Directions": "#FFFFFF", "Calls": "#1E1713",
               "Store visits": "#1E1713"}


def intent_stack(long):
    """Stacked shares of directions, calls and store visits."""
    fig = go.Figure()
    for intent, colour in INTENT_COLOURS.items():
        part = long.loc[long["intent"] == intent]
        if part.empty:
            continue
        fig.add_trace(go.Bar(
            x=part["share"], y=_safe(part["campaign"]), orientation="h",
            name=intent, marker_color=colour,
            text=[f"{value:.0%}" if value >= INTENT_LABEL_MIN else ""
                  for value in part["share"]],
            textposition="inside", insidetextanchor="middle",
            insidetextfont={"color": INTENT_TEXT[intent]},
            textfont={"color": INTENT_TEXT[intent]},
            hovertemplate=f"%{{y}}<br>{intent}: %{{x:.1%}}<extra></extra>"))
    campaigns = long["campaign"].nunique()
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Share of tracked actions", tickformat=".0%",
                     range=[0, 1])
    fig.update_yaxes(title=None)
    return _layout(fig, height=max(260, 34 * campaigns + 100))
