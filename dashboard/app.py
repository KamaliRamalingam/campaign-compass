"""Local Streamlit dashboard (T8, reworked in PR 4).

Run it with: bash dashboard.sh (after bash run.sh). It listens
on localhost only.

Reads only the client's results and reports folders, never
data/raw/ or outputs/interim/. All data preparation lives in
dashboard/data.py; this file only displays. Labels are the FINAL
labels (after the trend override) from
recommendations_by_campaign.csv; nothing is recomputed here. No
hosting, login, uploads or network access.

Every page shows the client's caveat from its config, the data
date range and the last-updated date. The wording is "tracked
actions" everywhere.
"""

import html
import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import data as dashboard_data  # noqa: E402

WIDE = st.column_config.TextColumn  # shorthand below
NUM = st.column_config.NumberColumn
PAGE_KEY = "page"
DETAIL_KEY = "detail_campaign"

STYLE = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 4rem;
                  max-width: 1400px;}
h1, h2, h3, h4 {color: #1F3A5F !important;}
.cc-sub {color: #5B6573; font-size: 1.02rem; margin: -0.4rem 0 1.1rem;}
.cc-badge {display: inline-block; padding: 0.2rem 0.75rem;
           border-radius: 999px; font-weight: 600; font-size: 1.05rem;
           border: 2px solid; color: #1C2430;}
.cc-foot {color: #5B6573; font-size: 0.88rem; line-height: 1.5;}
</style>
"""


def _title(question, subtitle, level=2):
    """A navy question heading with a grey subtitle under it."""
    st.markdown(f"{'#' * level} {question}")
    st.markdown(f"<p class='cc-sub'>{html.escape(subtitle)}</p>",
                unsafe_allow_html=True)


def _card(column, label, value, definition):
    """A bordered KPI card with a one-line definition."""
    with column.container(border=True):
        st.metric(label, value)
        st.caption(definition)


def _tint(colour, amount=0.78):
    """A light tint of a hex colour, for readable cell backgrounds."""
    colour = colour.lstrip("#")
    red, green, blue = (int(colour[i:i + 2], 16) for i in (0, 2, 4))
    mix = [round(value + (255 - value) * amount)
           for value in (red, green, blue)]
    return "#{:02X}{:02X}{:02X}".format(*mix)


LABEL_CELL = {dashboard_data.label_text(label): style["colour"]
              for label, style in dashboard_data.LABEL_STYLE.items()}


def _label_cell(value):
    """Cell style for a label shown as text: tinted, dark text."""
    colour = LABEL_CELL.get(value)
    if colour is None:
        return ""
    return (f"background-color: {_tint(colour)}; color: #1C2430; "
            f"font-weight: 600")


def _styled(table, columns):
    """A Styler that colours the given label-text columns."""
    present = [column for column in columns if column in table.columns]
    return table.style.map(_label_cell, subset=present)


def _badge(label):
    """A coloured label badge that also says the label in text."""
    colour = dashboard_data.label_colour(label)
    text = html.escape(dashboard_data.label_text(label) or "—")
    return (f"<span class='cc-badge' style='background:{_tint(colour)};"
            f"border-color:{colour}'>{text}</span>")


def _footnotes(lines):
    """Small grey footnotes under a page."""
    items = "".join(f"<li>{line}</li>" for line in lines)
    st.markdown(f"<div class='cc-foot'><ul>{items}</ul></div>",
                unsafe_allow_html=True)


def _open_detail(campaign):
    """Drill-through: open the Campaign detail page on a campaign.

    Runs as a button callback, before the next rerun, so it may set
    the page radio and the campaign selector.
    """
    st.session_state[PAGE_KEY] = "Campaign detail"
    st.session_state[DETAIL_KEY] = campaign


def _context(ctx):
    """Caveat banner, data date range and last-updated date."""
    st.info(ctx["caveat"], icon="ℹ️")
    first, last = ctx["date_range"]
    st.caption(
        f"Client: {ctx['client']} · Data date range: {first} to "
        f"{last} · Last updated: {ctx['updated']:%Y-%m-%d %H:%M}"
    )


def _table(table, file_name=None, column_config=None, key=None,
           height="auto"):
    """A sortable table (click a header), with a CSV download.

    The download is the table exactly as shown.
    """
    st.dataframe(table, hide_index=True, width="stretch",
                 height=height, column_config=column_config or {})
    if file_name:
        st.download_button(
            "Download CSV", dashboard_data.csv_bytes(table),
            file_name=file_name, mime="text/csv",
            key=key or f"download_{file_name}")


def _campaign_axis(title="Campaign"):
    """A y axis that never cuts campaign names short."""
    return alt.Axis(title=title, labelLimit=0)


# --- Act ----------------------------------------------------------

ACT_COLUMNS = {
    "rank": NUM("#", width="small", format="%d"),
    "campaign": WIDE("Campaign", width="large", pinned=True),
    "group": WIDE("Group", width="small"),
    "final_label": WIDE("Final label", width="medium",
                        help="After the trend override"),
    "status_now": WIDE("Status now", width="small"),
    "ratio_to_benchmark": NUM("Ratio to benchmark", format="%.2fx",
                              width="small"),
    "tracked_actions": NUM("Tracked actions", format="%.0f",
                           width="small"),
    "recent_trend": WIDE("Recent trend", width="small"),
    "action": WIDE("Action", width="large"),
    "label_period": WIDE("Label period", width="medium",
                         help="The run or recent window the label "
                              "comes from"),
}


def _act_definitions(ctx, kpi):
    """Footnote lines: definitions, then the config footnote."""
    config = ctx["config"]
    rules = (config.get("analysis") or {}).get(
        "recommendation_rules") or {}
    currency = ctx["currency"]
    window = (rules.get("recent_label") or {}).get("window_days")
    bench = (f"<b>Benchmark</b>: pooled cost per tracked action of "
             f"group(s) {html.escape(str(kpi['benchmark_groups']))}, "
             f"{kpi['benchmark']:,.2f} {currency}.")
    if kpi["leave_one_out"]:
        bench += (f" Each campaign is compared with the benchmark "
                  f"without itself ({kpi['loo_min']:,.2f} to "
                  f"{kpi['loo_max']:,.2f}); the hover shows its own.")
    lines = [
        "<b>Tracked action</b>: a conversion the account counts "
        "(mainly get-directions requests and calls), not a booking.",
        bench,
        f"<b>Ratio lines</b>: continue up to "
        f"{rules.get('continue_max_ratio')}x and test up to "
        f"{rules.get('test_max_ratio')}x the benchmark (from the "
        f"config); above that, pause or review.",
        "<b>Label period</b>: the latest run with enough volume"
        + (f", or the last {window} days for active campaigns"
           if window else "") + ". Bubbles use that period's figures.",
        "<b>Filters</b> only hide rows and bubbles; they never change "
        "a label or a KPI card.",
        f"<b>{html.escape(dashboard_data.footnote_text(config))}</b>",
    ]
    return lines


def _page_act(ctx):
    """Which campaigns should we continue, test or pause?"""
    _title("Act: which campaigns should we continue, test or pause?",
           "Final labels after the trend override, ranked by urgency. "
           "Read the Context page before acting on any of them.",
           level=1)
    _context(ctx)
    tables = ctx["tables"]
    currency = ctx["currency"]
    recs = ctx["all_recommendations"]

    filters = st.columns(3)
    group = filters[0].selectbox(
        "Campaign group", dashboard_data.group_options(recs),
        key="act_group")
    status = filters[1].selectbox(
        "Status now", dashboard_data.status_options(recs),
        key="act_status")
    min_actions = filters[2].number_input(
        "Minimum tracked actions", min_value=0, value=0, step=10,
        key="act_min_actions",
        help="Display filter only: hides campaigns with fewer tracked "
             "actions in their label period. Labels do not change.")
    view = dashboard_data.filter_view(recs, group, status, min_actions)

    kpi = dashboard_data.kpi_values(tables["benchmarks"])
    cards = st.columns(4)
    _card(cards[0], "Spend", f"{kpi['spend']:,.0f} {currency}",
          "Total spend of the judged campaigns.")
    _card(cards[1], "Tracked actions", f"{kpi['tracked_actions']:,.0f}",
          "Directions requests and calls the account counts.")
    _card(cards[2], "Cost per tracked action",
          f"{kpi['cost_per_tracked_action']:,.2f} {currency}",
          "Spend divided by tracked actions.")
    bench_note = (f"Leave-one-out range {kpi['loo_min']:,.2f} to "
                  f"{kpi['loo_max']:,.2f}." if kpi["leave_one_out"]
                  else "Pooled over the benchmark group(s).")
    _card(cards[3], "Benchmark", f"{kpi['benchmark']:,.2f} {currency}",
          f"What a campaign is compared with. {bench_note}")
    st.caption(f"Cards cover all {kpi['judged_campaigns']} judged "
               f"campaigns over the whole daily range "
               f"(benchmarks.csv). The filters do not change them.")

    st.write("")
    left, right = st.columns([2.2, 1], gap="large")
    with left:
        st.markdown("#### Where does each campaign sit against the "
                    "benchmark?")
        bubbles = dashboard_data.bubble_rows(view)
        if bubbles.empty:
            st.info("No judged campaign with label-period figures "
                    "matches the filters.")
        else:
            lines = dashboard_data.reference_lines(
                ctx["config"], kpi["benchmark"])
            st.plotly_chart(charts.bubble_chart(bubbles, lines, currency),
                            width="stretch", key="act_bubble")
            st.caption("Bubble size = spend in the label period. Marker "
                       "shape and legend text name the label, so colour "
                       "is never the only cue.")
    with right:
        counts, others = dashboard_data.judged_label_counts(view)
        st.markdown(f"#### Final labels: {int(counts['campaigns'].sum())}"
                    f" judged campaigns")
        st.plotly_chart(charts.label_count_bar(counts), width="stretch",
                        key="act_counts")
        if others:
            names = ", ".join(
                f"{count} {dashboard_data.LABEL_STYLE.get(label, {}).get('text', label).lower()}"
                for label, count in sorted(others.items()))
            st.caption(f"Not counted here: {names}. They are not judged "
                       f"against the benchmark.")

    st.write("")
    st.markdown("#### What should we do, most urgent first?")
    st.caption("Pause or review first, then test, then continue; within "
               "a label, the highest ratio to the benchmark first. "
               "Select a row to open its detail.")
    show_hidden = st.checkbox(
        "Also show insufficient data / not judged campaigns",
        value=False, key="act_show_hidden")
    table = dashboard_data.action_table(view, tables["recent_trend"])
    if not show_hidden:
        table = table.loc[table["label"].isin(
            dashboard_data.JUDGED_LABELS)].reset_index(drop=True)
    if table.empty:
        st.info("No campaign matches the filters.")
    else:
        columns = list(ACT_COLUMNS)
        event = st.dataframe(
            _styled(table, ["final_label"]), hide_index=True,
            width="stretch", column_order=columns,
            column_config=ACT_COLUMNS, on_select="rerun",
            selection_mode="single-row", key="act_table")
        selected = event.selection.rows if event else []
        buttons = st.columns([1, 1, 3])
        if selected:
            campaign = table.loc[selected[0], "campaign"]
            buttons[0].button(f"Open detail: {campaign}",
                              on_click=_open_detail, args=(campaign,),
                              type="primary", key="act_open")
        buttons[1].download_button(
            "Download CSV",
            dashboard_data.csv_bytes(table.drop(columns=["label"])),
            file_name="actions.csv", mime="text/csv",
            key="act_download")

    not_comparable = dashboard_data.not_comparable_rows(recs)
    if not not_comparable.empty:
        st.write("")
        with st.container(border=True):
            st.markdown(f"#### {dashboard_data.label_text('not_comparable')}"
                        f" ({len(not_comparable)})")
            st.caption("Judged against their own history, not the "
                       "benchmark, so they are not in the chart or the "
                       "ranking.")
            for _, row in not_comparable.iterrows():
                st.markdown(f"**{row['campaign']}** · {row['group']} · "
                            f"{row['status_now']}")
                st.write(row["reason"])
                st.markdown(f"*Action:* {row['action_text']}")

    st.divider()
    _footnotes(_act_definitions(ctx, kpi))


# --- Campaign -----------------------------------------------------

def _period_slider(values, label, key):
    """A from-to slider over the sorted periods; returns (start, end)."""
    options = sorted(set(str(value) for value in values))
    if len(options) < 2:
        return None, None
    return st.select_slider(label, options=options,
                            value=(options[0], options[-1]), key=key)


def _trend_section(ctx, campaign, prefix):
    """Monthly or weekly chart and table for one campaign.

    A period slider limits the rows shown (a filter, not a
    recalculation); tooltips include the partial/lagged
    flags for months.
    """
    tables = ctx["tables"]
    currency = ctx["currency"]
    view = st.radio("View", ["Monthly", "Weekly"], horizontal=True,
                    key=f"{prefix}_view")
    if view == "Monthly":
        table = dashboard_data.trend_for_campaign(
            tables["timeline_by_campaign"], campaign)
        timeline = tables["timeline_by_campaign"]
        flag_columns = [column for column in ("is_partial", "is_lagged")
                        if column in timeline.columns]
        if flag_columns:
            flags = timeline.loc[timeline["campaign"] == campaign,
                                 ["month", "source"] + flag_columns]
            table = table.merge(flags, on=["month", "source"],
                                how="left")
            table[flag_columns] = table[flag_columns].astype(
                "object").fillna("").astype(str)
        x_field, x_title, key = "month", "Month", "month"
    else:
        table = dashboard_data.weekly_for_campaign(
            tables["weekly_by_campaign"], campaign)
        x_field, x_title, key = "week_start", "Week starting", "week"
    if table.empty:
        st.caption("No monthly or weekly rows: the trend tables "
                   "cover the time groups in the config.")
    else:
        start, end = _period_slider(table[x_field], "Period",
                                    f"{prefix}_period_{key}")
        table = dashboard_data.filter_period(table, x_field, start, end)
        tooltip = [x_field, "spend", "tracked_actions",
                   alt.Tooltip("cost_per_tracked_action", format=".2f")]
        tooltip += [column for column in ("source", "is_partial",
                                          "is_lagged")
                    if column in table.columns]
        chart = alt.Chart(table).mark_line(point=True).encode(
            x=alt.X(f"{x_field}:O", title=x_title,
                    axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("cost_per_tracked_action:Q",
                    title=f"Cost per tracked action ({currency})"),
            tooltip=tooltip,
        )
        st.altair_chart(chart, width="stretch")
        if "is_partial" in table.columns:
            st.caption("Hover a point: is_partial marks a month the "
                       "campaign ran only part of; is_lagged marks "
                       "a month with days still being reported.")
        _table(dashboard_data.display_table(table),
               f"{key}ly_{campaign}.csv", key=f"{prefix}_trend")



def _page_campaign(ctx):
    """One campaign: label and reasons, runs, trend, weekday, journey."""
    st.header("Campaign")
    _context(ctx)
    tables = ctx["tables"]
    currency = ctx["currency"]
    if not ctx["campaigns"]:
        st.info("No campaigns in this group.")
        return
    campaign = st.selectbox("Campaign", ctx["campaigns"])
    detail = dashboard_data.campaign_detail(
        ctx["all_recommendations"], tables["recent_trend"], campaign)

    cols = st.columns(3)
    cols[0].metric("Final label", detail["label"], border=True)
    cols[1].metric("Status now", detail["status_now"], border=True)
    cols[2].metric("Recent trend", detail["recent_trend"] or "—",
                   border=True)
    with st.container(border=True):
        st.markdown(f"**Action:** {detail['action']}")
        label_period = detail["label_period"] or "no period"
        st.markdown(f"**Label** (from {detail['label_from']}, "
                    f"{label_period})")
        st.write(detail["reason"])
        if detail["trend_window"]:
            st.markdown(
                f"**Trend** (recent window {detail['trend_window']}, "
                f"prior window {detail['prior_window']})")
            st.write(detail["trend_reason"])
        else:
            st.caption("No recent trend: the campaign is not active "
                       "or its group is not judged.")

    st.subheader("Runs")
    runs = dashboard_data.run_recommendations_for_campaign(
        tables["recommendations_by_run"], campaign)
    if runs.empty:
        st.caption("No runs: runs are built only for the run groups "
                   "in the config.")
    else:
        _table(dashboard_data.display_table(runs),
               f"runs_{campaign}.csv", key="campaign_runs")

    st.subheader("Trend")
    _trend_section(ctx, campaign, "campaign")

    st.subheader("Weekday pattern")
    by_campaign = tables["weekday_by_campaign"]
    if campaign not in set(by_campaign["campaign"]):
        st.caption("No weekday rows: weekday tables cover the time "
                   "groups in the config.")
    else:
        weekday = dashboard_data.weekday_campaign_table(
            by_campaign, campaign)
        chart = alt.Chart(weekday).mark_bar().encode(
            x=alt.X("weekday:N", sort=list(weekday["weekday"]),
                    title="Weekday"),
            y=alt.Y("cost_per_tracked_action:Q",
                    title=f"Cost per tracked action ({currency})"),
            tooltip=["weekday", "tracked_actions", "clicks",
                     alt.Tooltip("cost_per_tracked_action",
                                 format=".2f"), "volume_flag"],
        )
        st.altair_chart(chart, width="stretch")
        _table(dashboard_data.display_table(weekday),
               f"weekday_{campaign}.csv", key="campaign_weekday")

    st.subheader("Acquisition journey")
    journey = dashboard_data.journey_row(
        tables["journey_by_campaign"], campaign)
    if journey.empty:
        st.caption("No journey row: the journey covers the time "
                   "groups in the config.")
    else:
        _table(dashboard_data.display_table(
            dashboard_data.journey_display(journey)),
            key="campaign_journey")


# --- Context ------------------------------------------------------

BENCHMARK_NAMES = {
    "benchmark": "Benchmark (pooled, the one used)",
    "with_not_comparable": "Including not-comparable groups",
    "judged_campaigns": "Judged campaigns (KPI cards)",
}


def _section(question, subtitle):
    """A section heading on the Context page."""
    st.write("")
    _title(question, subtitle, level=3)


def _context_trend(ctx):
    """Has performance changed recently?"""
    tables = ctx["tables"]
    currency = ctx["currency"]
    _section("Has performance changed recently?",
             "Recent window against the prior window for active "
             "campaigns, and the monthly trend with incomplete months "
             "marked.")
    rows = dashboard_data.recent_trend_rows(
        tables["recent_trend"], ctx["all_recommendations"])
    if rows.empty:
        st.caption("No active campaign has a recent trend.")
    else:
        _table(rows, "recent_trend.csv", key="ctx_recent",
               column_config={
                   "campaign": WIDE("Campaign", width="large",
                                    pinned=True),
                   "final_label": WIDE("Final label", width="medium"),
                   "recent_trend": WIDE("Recent trend", width="small"),
                   "recent_window": WIDE("Recent window",
                                         width="medium"),
                   "recent_cost_per_tracked_action": NUM(
                       f"Recent cost ({currency})", format="%.2f"),
                   "prior_window": WIDE("Prior window", width="medium"),
                   "prior_cost_per_tracked_action": NUM(
                       f"Prior cost ({currency})", format="%.2f"),
                   "recent_vs_prior_ratio": NUM(
                       "Recent vs prior", format="%.2fx"),
                   "recent_tracked_actions": NUM(
                       "Recent tracked actions", format="%.0f"),
               })
    timeline = tables["timeline_by_campaign"]
    campaigns = sorted(set(timeline["campaign"]))
    if not campaigns:
        return
    active = [name for name in rows["campaign"] if name in campaigns]
    default = active[0] if active else campaigns[0]
    campaign = st.selectbox("Campaign for the monthly trend", campaigns,
                            index=campaigns.index(default),
                            key="ctx_trend_campaign")
    table = dashboard_data.trend_with_flags(timeline, campaign)
    st.plotly_chart(charts.trend_line(table, "month", "Month", currency),
                    width="stretch", key="ctx_trend_chart")
    st.caption("Hollow ring = partial month (the campaign ran only part "
               "of it) or lagged month (days still being reported). "
               "Do not read a jump in those months as a change.")


def _context_lag(ctx):
    """Is the latest data complete?"""
    _section("Is the latest data complete?",
             "Tracked actions can arrive days late. The lag check "
             "reruns the recent signals with other lags and counts "
             "what changes.")
    config = ctx["config"]
    configured = (config.get("analysis", {}).get("recent_trend", {})
                  .get("conversion_lag_days"))
    lag_check = ctx["optional"]["lag_check"]
    if lag_check is None:
        st.info("The lag check is not turned on for this client "
                "(recent_trend.lag_check_days in its config).")
        return
    summary = dashboard_data.lag_check_summary(lag_check)
    changes = summary.drop(columns=["lag"]).fillna(0).to_numpy().sum()
    st.markdown(f"Configured lag: **{configured} days** (unchanged). "
                + ("No trend or label changes with any other lag."
                   if changes == 0 else
                   "Some trends or labels change with another lag: "
                   "treat the most recent weeks with care."))
    _table(summary, "lag_check_summary.csv", key="ctx_lag",
           column_config={
               "lag": NUM("Lag (days)", format="%d"),
               "trend_changes": NUM("Trend changes", format="%d"),
               "label_changes": NUM("Label changes", format="%d")})
    with st.expander("All lag-check counts"):
        _table(lag_check, "lag_check.csv", key="ctx_lag_all")


def _context_weekday(ctx):
    """Do weekdays differ, and is one day distorting it?"""
    tables = ctx["tables"]
    optional = ctx["optional"]
    currency = ctx["currency"]
    _section("Do weekdays differ, and is one day distorting it?",
             "Pooled over the time groups in the config; then each "
             "campaign's share of one weekday and the weekday with "
             "each campaign left out.")
    try:
        pooled = dashboard_data.weekday_core_table(tables["weekday_core"])
    except ValueError as exc:
        st.error(str(exc))
        return
    mix = optional["weekday_mix_by_campaign"]
    loo = optional["weekday_leave_one_out"]
    top = optional["weekday_top_days"]
    focus = (top["weekday"].iloc[0]
             if top is not None and not top.empty else None)
    full = {day[:3]: day for day in dashboard_data.WEEKDAYS}
    st.plotly_chart(charts.weekday_bar(pooled, currency,
                                       highlight=full.get(focus, focus)),
                    width="stretch", key="ctx_weekday_chart")
    if focus:
        st.caption(f"Highlighted: {full.get(focus, focus)}, the weekday "
                   f"with the most pooled clicks.")
    with st.expander("Pooled weekday table"):
        _table(dashboard_data.display_table(pooled), "weekday_pooled.csv",
               key="ctx_weekday_pooled")
    if mix is None or loo is None:
        st.info("The weekday decomposition is not turned on for this "
                "client (analysis.weekday_decomposition in its config).")
        return
    short = [day[:3] for day in dashboard_data.WEEKDAYS
             if day[:3] in set(mix["weekday"])]
    weekday = st.selectbox(
        "Weekday to break down", short,
        index=short.index(focus) if focus in short else 0,
        key="ctx_weekday",
        help="Default: the weekday with the most pooled clicks")
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown(f"**Who makes up {weekday}?**")
        share = dashboard_data.weekday_focus_table(mix, weekday)
        st.plotly_chart(charts.share_bar(share, weekday), width="stretch",
                        key="ctx_share_chart")
    with right:
        st.markdown(f"**{weekday} with one campaign left out**")
        st.caption("Closest to the Mon-Thu baseline first: that campaign "
                   "explains most of the weekday's difference.")
        _table(dashboard_data.leave_one_out_for_weekday(loo, weekday),
               f"weekday_leave_one_out_{weekday}.csv", key="ctx_loo",
               column_config={
                   "left_out": WIDE("Left out", width="large",
                                    pinned=True)})
    if top is not None and not top.empty:
        top_weekday = top["weekday"].iloc[0]
        with st.expander(f"Top {len(top)} {top_weekday}s by pooled clicks "
                         f"(together "
                         f"{top['share_of_weekday_clicks'].sum():.1%} of "
                         f"{top_weekday} clicks)"):
            _table(top, "weekday_top_days.csv", key="ctx_top")


def _context_what_if(ctx):
    """What would moving spend do?"""
    _section("What would moving spend do?",
             "Moving weekday spend to the weekend, as a linear estimate "
             "for each variant of the groups.")
    rows, span = dashboard_data.what_if_parts(
        ctx["tables"]["what_if_weekday_shift"])
    if span is not None:
        with st.container(border=True):
            st.metric("Change in tracked actions, range across variants",
                      span["display"])
    columns = [column for column in (
        "variant", "groups", "scenario", "spend_moved",
        "tracked_actions_before", "tracked_actions_after", "display")
        if column in rows.columns]
    shown = rows[columns].copy()
    for column in ("spend_moved", "tracked_actions_before",
                   "tracked_actions_after"):
        if column in shown.columns:
            shown[column] = shown[column].round(0)
    _table(shown, "what_if.csv", key="ctx_what_if", column_config={
        "scenario": WIDE("Scenario", width="large"),
        "display": WIDE("Change", width="medium")})
    note = rows["note"].iloc[0] if "note" in rows.columns else ""
    if note:
        st.warning(f"{note}.", icon="⚠️")


def _context_journey(ctx):
    """How do people reach the restaurant?"""
    tables = ctx["tables"]
    _section("How do people reach the restaurant?",
             "Share of each campaign's tracked actions that are "
             "directions requests, calls or store visits.")
    long = dashboard_data.journey_intent_long(tables["journey_by_campaign"])
    if long.empty:
        st.caption("No journey rows.")
    else:
        st.plotly_chart(charts.intent_stack(long), width="stretch",
                        key="ctx_journey_chart")
    with st.expander("Journey table"):
        journey = dashboard_data.display_table(
            dashboard_data.journey_display(
                tables["journey_by_campaign"])).rename(columns={
            "directions share": "directions share (%)",
            "calls share": "calls share (%)",
            "store visits share": "store visits share (%)"})
        _table(journey, "journey.csv", key="ctx_journey", column_config={
            "campaign": WIDE("Campaign", width="large", pinned=True)})
    break_even = ctx["break_even"]
    if break_even is not None:
        st.markdown("**Break-even** (illustration: tracked actions are not "
                    "visits)")
        _table(dashboard_data.display_table(break_even), "break_even.csv",
               key="ctx_break_even", column_config={
                   "campaign": WIDE("Campaign", width="large",
                                    pinned=True),
                   "note": WIDE("Note", width="large")})


def _context_method(ctx):
    """Benchmarks, sensitivity, rules and what counts, in an expander."""
    tables = ctx["tables"]
    config = ctx["config"]
    st.write("")
    with st.expander("Method and definitions"):
        st.markdown("**Benchmarks**")
        benchmarks = tables["benchmarks"].copy()
        benchmarks.insert(0, "what", benchmarks["variant"].map(
            BENCHMARK_NAMES).fillna(benchmarks["variant"]))
        _table(benchmarks.drop(columns=["variant"]), "benchmarks.csv",
               key="ctx_benchmarks", column_config={
                   "what": WIDE("What", width="large", pinned=True)})
        st.caption("loo_min / loo_max: the range of leave-one-out "
                   "benchmarks, each campaign judged without itself.")

        st.markdown("**Do the labels hold if the thresholds move?**")
        sensitivity = tables["recommendation_sensitivity"]
        stable = sensitivity.drop_duplicates("campaign")["label_stable"]
        st.caption(f"{int(stable.sum())} of {len(stable)} campaigns keep "
                   f"the same label in every threshold combination "
                   f"(labels before the trend override).")
        _table(sensitivity, "recommendation_sensitivity.csv",
               key="ctx_sensitivity", column_config={
                   "campaign": WIDE("Campaign", width="large",
                                    pinned=True)})

        st.markdown("**Volume rule and thresholds (from the config)**")
        _table(dashboard_data.rules_table(config), "rules.csv",
               key="ctx_rules", column_config={
                   "setting": WIDE("Setting", width="large"),
                   "value": WIDE("Value", width="medium")})

        st.markdown("**What counts as a tracked action**")
        mix = tables["conversion_mix_by_campaign"]
        shares = dashboard_data.conversion_shares(mix)
        display = shares[["action", "action_group", "tracked_actions",
                          "share_pct"]].copy()
        display.columns = ["Action", "Action group", "Tracked actions",
                           "Share of tracked actions (%)"]
        _table(display, "tracked_actions_by_action.csv",
               key="ctx_conversion",
               column_config={"Action": WIDE("Action", width="large")})
        st.caption(
            "Engagement actions (menu views, website visits, other "
            "engagements) are "
            f"{dashboard_data.engagement_share_all(mix):.2%} of All conv. "
            "but are not counted as tracked actions.")


def _page_context(ctx):
    """Can we trust this? Trend, lag, weekdays, what-if, journey."""
    _title("Context: can we trust this?",
           "Checks to read before acting on a label: recent change, "
           "data completeness, weekday effects, what moving spend "
           "would do and how people reach the restaurant.", level=1)
    _context(ctx)
    _context_trend(ctx)
    st.divider()
    _context_lag(ctx)
    st.divider()
    _context_weekday(ctx)
    st.divider()
    _context_what_if(ctx)
    st.divider()
    _context_journey(ctx)
    _context_method(ctx)


# --- Pages kept from T8 -------------------------------------------

def _page_runs(ctx):
    """One campaign's runs, with run labels, as a chart and a table."""
    st.header("Runs")
    _context(ctx)
    currency = ctx["currency"]
    run_recs = ctx["tables"]["recommendations_by_run"]
    campaigns = [name for name in ctx["campaigns"]
                 if name in set(run_recs["campaign"])]
    if not campaigns:
        st.info("No runs for the campaigns in this group: runs are "
                "built only for the run groups in the config.")
        return
    campaign = st.selectbox("Campaign", campaigns)
    table = dashboard_data.run_recommendations_for_campaign(
        run_recs, campaign)
    chart = alt.Chart(table).mark_bar().encode(
        x=alt.X("run_number:O", title="Run"),
        y=alt.Y("cost_per_conversion:Q",
                title=f"Cost per tracked action ({currency})"),
        color=alt.Color("run_label:N", title="Run label"),
        tooltip=["run_number", "start", "end", "spend",
                 alt.Tooltip("cost_per_conversion", format=".2f",
                             title="cost per tracked action"),
                 alt.Tooltip("ratio_to_benchmark", format=".2f"),
                 "run_label"],
    )
    st.altair_chart(chart, width="stretch")
    st.caption("Run labels judge each run on its own; the campaign's "
               "final label is on the Summary and Campaign pages.")
    _table(dashboard_data.display_table(table), f"runs_{campaign}.csv",
           key="runs")


def _page_trend(ctx):
    """Monthly or weekly trend for a selected campaign."""
    st.header("Trend")
    _context(ctx)
    timeline = ctx["tables"]["timeline_by_campaign"]
    campaigns = [name for name in ctx["campaigns"]
                 if name in set(timeline["campaign"])]
    if not campaigns:
        st.info("No trend rows for the campaigns in this group: the "
                "trend tables cover the time groups in the config.")
        return
    campaign = st.selectbox("Campaign", campaigns)
    _trend_section(ctx, campaign, "trend")
    st.caption("Monthly source: day is the daily export, month is "
               "the monthly-history export. Weeks start on Monday.")


PAGES = {
    "Act": _page_act,
    "Context": _page_context,
    "Campaign": _page_campaign,
    "Runs": _page_runs,
    "Trend": _page_trend,
}


def _load(client):
    """Config, tables and context for one client."""
    config = dashboard_data.load_config(
        dashboard_data.client_config_path(client))
    output_root = dashboard_data.client_output_root(client, config)
    tables = dashboard_data.load_tables(config, output_root=output_root)
    optional = dashboard_data.load_optional_tables(
        config, output_root=output_root)
    paths = dashboard_data.table_paths(config, output_root=output_root)
    return {
        "client": client,
        "config": config,
        "caveat": dashboard_data.caveat_text(config),
        "currency": config.get("currency", "SEK"),
        "tables": tables,
        "optional": optional,
        "break_even": dashboard_data.load_break_even(
            config, output_root=output_root),
        "date_range": dashboard_data.data_date_range(
            tables["campaign_summary_day"]),
        "updated": dashboard_data.last_updated(paths.values()),
    }


def main():
    """Pick a client and a page, load the tables, show the page."""
    st.set_page_config(page_title="CampaignCompass", layout="wide")
    st.markdown(STYLE, unsafe_allow_html=True)
    st.sidebar.markdown("## CampaignCompass")
    client = st.sidebar.selectbox(
        "Client", dashboard_data.list_clients(), index=0)
    try:
        ctx = _load(client)
    except FileNotFoundError as exc:
        st.error(f"{exc}")
        st.stop()
    recs = ctx["tables"]["recommendations_by_campaign"]
    ctx["all_recommendations"] = recs
    ctx["campaigns"] = sorted(recs["campaign"])
    page = st.sidebar.radio("Page", list(PAGES), key=PAGE_KEY)
    PAGES[page](ctx)


if __name__ == "__main__":
    main()
