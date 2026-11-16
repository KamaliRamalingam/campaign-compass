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

import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data as dashboard_data  # noqa: E402

WIDE = st.column_config.TextColumn  # shorthand below


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


# --- Summary ------------------------------------------------------

def _page_summary(ctx):
    """Answer first: KPIs, final labels and one row per campaign."""
    st.header("Summary")
    _context(ctx)
    tables = ctx["tables"]
    currency = ctx["currency"]
    kpi = dashboard_data.kpi_values(tables["benchmarks"])
    cols = st.columns(4)
    cols[0].metric("Spend", f"{kpi['spend']:,.0f} {currency}",
                   border=True)
    cols[1].metric("Tracked actions", f"{kpi['tracked_actions']:,.0f}",
                   border=True)
    cols[2].metric("Cost per tracked action",
                   f"{kpi['cost_per_tracked_action']:.2f} {currency}",
                   border=True)
    bench_help = f"Pooled cost per tracked action of group(s) " \
                 f"{kpi['benchmark_groups']}."
    if kpi["leave_one_out"]:
        bench_help += (
            f" Each campaign is judged against the benchmark "
            f"without itself: {kpi['loo_min']:.2f} to "
            f"{kpi['loo_max']:.2f}.")
    cols[3].metric("Benchmark", f"{kpi['benchmark']:.2f} {currency}",
                   help=bench_help, border=True)
    st.caption(
        f"Tiles cover the {kpi['judged_campaigns']} judged campaigns "
        f"over the whole daily range, read from benchmarks.csv. "
        f"The group filter does not change them: that would mean "
        f"recomputing.")

    recs = ctx["recommendations"]
    st.subheader("Final labels (after the trend override)")
    counts = dashboard_data.final_label_counts(recs)
    chart = alt.Chart(counts).mark_bar().encode(
        x=alt.X("campaigns:Q", title="Campaigns",
                axis=alt.Axis(format="d", tickMinStep=1)),
        y=alt.Y("label:N", sort="-x", axis=_campaign_axis("Label")),
        tooltip=["label", "campaigns"],
    )
    st.altair_chart(chart, width="stretch")

    st.subheader("Judged campaigns")
    show_hidden = st.checkbox(
        "Show not_judged / insufficient_data campaigns", value=False)
    rows = dashboard_data.summary_rows(
        ctx["all_recommendations"], tables["recent_trend"],
        show_hidden=show_hidden, group=ctx["group"])
    _table(rows, "summary_campaigns.csv", column_config={
        "campaign": WIDE("Campaign", width="medium", pinned=True),
        "group": WIDE("Group", width="small"),
        "label": WIDE("Final label", width="small"),
        "status_now": WIDE("Status now", width="small"),
        "recent_trend": WIDE("Recent trend", width="small"),
        "action": WIDE("Action", width="large",
                       help="One-line action for the final label"),
        "label_from": WIDE("Label from", width="small",
                           help="recent_window, latest_run or fixed"),
        "label_period": WIDE("Label period", width="medium"),
        "trend_period": WIDE("Trend window", width="medium",
                             help="Recent window of the trend; "
                                  "empty for campaigns not active"),
    })
    with st.expander("Full reasons"):
        for _, row in rows.iterrows():
            detail = dashboard_data.campaign_detail(
                ctx["all_recommendations"], tables["recent_trend"],
                row["campaign"])
            st.markdown(f"**{detail['campaign']}** — {detail['label']}")
            st.write(detail["reason"])
            if detail["trend_reason"]:
                st.write(f"Trend: {detail['trend_reason']}")

    not_comparable = dashboard_data.not_comparable_rows(
        ctx["all_recommendations"])
    if not not_comparable.empty:
        with st.container(border=True):
            st.subheader("Not comparable")
            st.caption("Judged against their own history, not the "
                       "benchmark.")
            for _, row in not_comparable.iterrows():
                st.markdown(f"**{row['campaign']}** ({row['group']}, "
                            f"{row['status_now']})")
                st.write(row["reason"])
                st.write(f"Action: {row['action_text']}")


# --- Campaign -----------------------------------------------------

def _period_slider(values, label, key):
    """A from-to slider over the sorted periods; returns (start, end)."""
    options = sorted(set(str(value) for value in values))
    if len(options) < 2:
        return None, None
    return st.select_slider(label, options=options,
                            value=(options[0], options[-1]), key=key)


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
    view = st.radio("View", ["Monthly", "Weekly"], horizontal=True,
                    key="campaign_view")
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
                                    f"period_{key}")
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
               f"{key}ly_{campaign}.csv", key="campaign_trend")

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


# --- Pages kept from T8 (fixed in a later commit) ----------------

def _page_conversion(ctx):
    """What counts as a tracked action."""
    st.header("What counts as a tracked action")
    _context(ctx)
    tables = ctx["tables"]
    shares = dashboard_data.conversion_shares(
        tables["conversion_mix_by_campaign"])
    chart = alt.Chart(shares).mark_bar().encode(
        x=alt.X("share", axis=alt.Axis(format=".2%"),
                title="Share of tracked actions"),
        y=alt.Y("action", sort="-x", title="Action"),
        tooltip=["action", "action_group", "tracked_actions",
                 alt.Tooltip("share", format=".2%")],
    )
    st.altair_chart(chart, width="stretch")
    display = shares[["action", "action_group", "tracked_actions",
                      "share_pct"]].copy()
    display.columns = ["Action", "Action group", "Tracked actions",
                       "Share of tracked actions (%)"]
    st.dataframe(display, width="stretch")
    engagement_all = dashboard_data.engagement_share_all(
        tables["conversion_mix_by_campaign"])
    st.write(
        "Engagement actions (menu views, website visits, other "
        "engagements) are "
        f"{engagement_all:.2%} of All conv. but are not counted "
        "as tracked actions."
    )


def _page_runs(ctx):
    """One campaign's runs as a chart and a table."""
    st.header("Runs")
    _context(ctx)
    currency = ctx["currency"]
    runs = ctx["tables"]["runs"]
    campaign = st.selectbox(
        "Campaign", sorted(runs["campaign"].unique()))
    table = dashboard_data.runs_for_campaign(runs, campaign)
    chart = alt.Chart(table).mark_bar().encode(
        x=alt.X("run_number", axis=alt.Axis(format="d"),
                title="Run"),
        y=alt.Y("cost_per_tracked_action",
                title=f"Cost per tracked action ({currency})"),
        tooltip=["run_number", "start", "end", "spend",
                 "cost_per_tracked_action", "volume_flag"],
    )
    st.altair_chart(chart, width="stretch")
    st.dataframe(dashboard_data.display_table(table), width="stretch")


def _page_trend(ctx):
    """Monthly or weekly trend for a selected campaign."""
    st.header("Trend")
    _context(ctx)
    currency = ctx["currency"]
    tables = ctx["tables"]
    timeline = tables["timeline_by_campaign"]
    campaign = st.selectbox(
        "Campaign", sorted(timeline["campaign"].unique()))
    view = st.radio("View", ["Monthly", "Weekly"], horizontal=True)
    if view == "Weekly":
        table = dashboard_data.weekly_for_campaign(
            tables["weekly_by_campaign"], campaign)
        chart = alt.Chart(table).mark_line(point=True).encode(
            x=alt.X("week_start", title="Week starting"),
            y=alt.Y("cost_per_tracked_action",
                    title=f"Cost per tracked action ({currency})"),
            tooltip=["week_start", "spend", "tracked_actions",
                     "cost_per_tracked_action"],
        )
        st.altair_chart(chart, width="stretch")
        st.write("Weeks start on Monday, from the daily data.")
        st.dataframe(dashboard_data.display_table(table),
                     width="stretch")
        return
    table = dashboard_data.trend_for_campaign(timeline, campaign)
    chart = alt.Chart(table).mark_line(point=True).encode(
        x=alt.X("month", title="Month"),
        y=alt.Y("cost_per_tracked_action",
                title=f"Cost per tracked action ({currency})"),
        color=alt.Color("source", title="Source"),
        tooltip=["month", "source", "spend", "tracked_actions",
                 "cost_per_tracked_action"],
    )
    st.altair_chart(chart, width="stretch")
    st.write(
        "Source marks where each month comes from: day is the "
        "daily export, month is the monthly-history export."
    )
    st.dataframe(dashboard_data.display_table(table), width="stretch")


def _page_journey(ctx):
    """Acquisition journey, what-if and break-even."""
    st.header("Acquisition journey")
    _context(ctx)
    tables = ctx["tables"]
    st.subheader("Journey by campaign")
    st.dataframe(
        dashboard_data.display_table(
            dashboard_data.journey_display(
                tables["journey_by_campaign"])).rename(columns={
            "directions share": "directions share (%)",
            "calls share": "calls share (%)",
            "store visits share": "store visits share (%)",
        }),
        width="stretch",
        column_config={
            "campaign": WIDE("Campaign", width="large"),
        },
    )
    st.write(
        "Intent shares are shares of tracked actions. "
        "Engagement actions are All conv. of the engagement "
        "action group."
    )
    campaigns = dashboard_data.journey_campaigns(
        tables["journey_by_campaign"])
    chart = alt.Chart(campaigns).mark_bar().encode(
        x=alt.X("tracked_actions_per_click",
                title="Tracked actions per click"),
        y=alt.Y("campaign", sort="-x", title="Campaign"),
        tooltip=["campaign", "tracked_actions_per_click",
                 "cost_per_tracked_action"],
    )
    st.altair_chart(chart, width="stretch")
    break_even = ctx["break_even"]
    if break_even is not None:
        st.subheader("Break-even")
        st.dataframe(
            dashboard_data.display_table(break_even),
            width="stretch",
            column_config={
                "campaign": WIDE("Campaign", width="large"),
            },
        )
        st.write(
            "Illustration: tracked actions are not visits."
        )


PAGES = {
    "Summary": _page_summary,
    "Campaign": _page_campaign,
    "What counts as a tracked action": _page_conversion,
    "Runs": _page_runs,
    "Trend": _page_trend,
    "Acquisition journey": _page_journey,
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
    st.title("CampaignCompass")
    client = st.sidebar.selectbox(
        "Client", dashboard_data.list_clients(), index=0)
    try:
        ctx = _load(client)
    except FileNotFoundError as exc:
        st.error(f"{exc}")
        st.stop()
    recs = ctx["tables"]["recommendations_by_campaign"]
    group = st.sidebar.selectbox(
        "Campaign group", dashboard_data.group_options(recs))
    ctx["group"] = group
    ctx["all_recommendations"] = recs
    ctx["campaigns"] = dashboard_data.campaigns_in_group(recs, group)
    ctx["recommendations"] = recs.loc[
        recs["campaign"].isin(ctx["campaigns"])]
    page = st.sidebar.radio("Page", list(PAGES))
    PAGES[page](ctx)


if __name__ == "__main__":
    main()
