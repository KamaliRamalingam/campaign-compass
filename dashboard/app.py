"""Local Streamlit dashboard (T8).

Run it with: bash dashboard.sh (after bash run.sh).
Reads only outputs/results/ and outputs/reports/ — never
data/raw/. All data preparation lives in dashboard/data.py;
this file only displays. No hosting, login, uploads or network
access.

Every page shows the caveat from the config, the data date
range and the last-updated date. The wording is "tracked
actions" everywhere.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data as dashboard_data  # noqa: E402


def _context(caveat, date_range, updated):
    """Caveat, data date range and last-updated date, every page."""
    st.info(caveat)
    first, last = date_range
    st.caption(
        f"Data date range: {first} to {last} · "
        f"Last updated: {updated:%Y-%m-%d %H:%M}"
    )


def _page_conversion(tables, caveat, date_range, updated):
    """What counts as a conversion."""
    st.header("What counts as a tracked action")
    _context(caveat, date_range, updated)
    shares = dashboard_data.conversion_shares(
        tables["conversion_mix_by_campaign"])
    import altair as alt
    chart = alt.Chart(shares).mark_bar().encode(
        x=alt.X("share", axis=alt.Axis(format=".2%"),
                title="Share of tracked actions"),
        y=alt.Y("action", sort="-x", title="Action"),
        tooltip=["action", "action_group", "tracked_actions",
                 alt.Tooltip("share", format=".2%")],
    )
    st.altair_chart(chart, use_container_width=True)
    display = shares[["action", "action_group", "tracked_actions",
                      "share_pct"]].copy()
    display.columns = ["Action", "Action group", "Tracked actions",
                       "Share of tracked actions (%)"]
    st.dataframe(display, use_container_width=True)
    engagement_all = dashboard_data.engagement_share_all(
        tables["conversion_mix_by_campaign"])
    st.write(
        "Engagement actions (menu views, website visits, other "
        "engagements) are "
        f"{engagement_all:.2%} of All conv. but are not counted "
        "as tracked actions."
    )


def _page_overview(tables, caveat, date_range, updated):
    """Spend and conversions by group; core campaigns table."""
    st.header("Overview")
    _context(caveat, date_range, updated)
    groups = dashboard_data.overview_groups(tables["group_summary"])
    st.subheader("Spend and tracked actions by group")
    st.dataframe(
        dashboard_data.display_table(groups),
        use_container_width=True,
        column_config={
            "group": st.column_config.TextColumn(
                "Group", width="large"),
        },
    )
    core = dashboard_data.core_campaigns(
        tables["campaign_summary_day"],
        tables["recommendations_by_campaign"])
    st.subheader("Core campaigns")
    st.dataframe(
        dashboard_data.display_table(core),
        use_container_width=True,
        column_config={
            "campaign": st.column_config.TextColumn(
                "Campaign", width="large"),
            "label": st.column_config.TextColumn(
                "Label", width="medium"),
            "action_text": st.column_config.TextColumn(
                "Action", width="large"),
        },
    )


def _page_comparison(tables, caveat, date_range, updated):
    """Cost per tracked action for core campaigns."""
    st.header("Campaign comparison")
    _context(caveat, date_range, updated)
    comparison = dashboard_data.comparison_data(
        tables["campaign_summary_day"],
        tables["recommendations_by_campaign"])
    log_scale = st.checkbox("Log scale", value=False)
    chart_data = comparison.loc[
        comparison["volume_flag"] != "insufficient_data"]
    import altair as alt
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("cost_per_tracked_action",
                scale=alt.Scale(type="log") if log_scale else
                alt.Scale(type="linear"),
                title="Cost per tracked action (SEK)"),
        y=alt.Y("campaign", sort="-x", title="Campaign"),
        tooltip=["campaign", "cost_per_tracked_action", "rank"],
    )
    st.altair_chart(chart, use_container_width=True)
    st.write(
        "Campaigns marked insufficient_data are not ranked; "
        "they are listed below the chart."
    )
    st.dataframe(
        dashboard_data.display_table(comparison),
        use_container_width=True,
        column_config={
            "campaign": st.column_config.TextColumn(
                "Campaign", width="large"),
            "label": st.column_config.TextColumn(
                "Label", width="medium"),
            "action_text": st.column_config.TextColumn(
                "Action", width="large"),
        },
    )


def _page_runs(tables, caveat, date_range, updated):
    """One campaign's runs as a chart and a table."""
    st.header("Runs")
    _context(caveat, date_range, updated)
    runs = tables["runs"]
    campaign = st.selectbox(
        "Campaign", sorted(runs["campaign"].unique()))
    table = dashboard_data.runs_for_campaign(runs, campaign)
    import altair as alt
    chart = alt.Chart(table).mark_bar().encode(
        x=alt.X("run_number", axis=alt.Axis(format="d"),
                title="Run"),
        y=alt.Y("cost_per_tracked_action",
                title="Cost per tracked action (SEK)"),
        tooltip=["run_number", "start", "end", "spend",
                 "cost_per_tracked_action", "volume_flag"],
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(dashboard_data.display_table(table),
                 use_container_width=True)


def _page_weekday(tables, caveat, date_range, updated):
    """Pooled core weekday chart and a campaign selector."""
    st.header("Weekday")
    _context(caveat, date_range, updated)
    try:
        pooled = dashboard_data.weekday_core_table(
            tables["weekday_core"])
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    import altair as alt
    st.subheader("Core group, pooled")
    chart = alt.Chart(pooled).mark_bar().encode(
        x=alt.X("weekday", sort=list(pooled["weekday"]),
                title="Weekday"),
        y=alt.Y("cost_per_tracked_action",
                title="Cost per tracked action (SEK)"),
        tooltip=["weekday", "tracked_actions",
                 "cost_per_tracked_action"],
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(dashboard_data.display_table(pooled),
                 use_container_width=True)
    by_campaign = tables["weekday_by_campaign"]
    campaign = st.selectbox(
        "Campaign", sorted(by_campaign["campaign"].unique()))
    try:
        table = dashboard_data.weekday_campaign_table(
            by_campaign, campaign)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    st.subheader(f"Weekday for {campaign}")
    st.dataframe(dashboard_data.display_table(table),
                 use_container_width=True)


def _page_trend(tables, caveat, date_range, updated):
    """Monthly or weekly trend for a selected campaign."""
    st.header("Trend")
    _context(caveat, date_range, updated)
    timeline = tables["timeline_by_campaign"]
    campaign = st.selectbox(
        "Campaign", sorted(timeline["campaign"].unique()))
    view = st.radio("View", ["Monthly", "Weekly"], horizontal=True)
    import altair as alt
    if view == "Weekly":
        table = dashboard_data.weekly_for_campaign(
            tables["weekly_by_campaign"], campaign)
        chart = alt.Chart(table).mark_line(point=True).encode(
            x=alt.X("week_start", title="Week starting"),
            y=alt.Y("cost_per_tracked_action",
                    title="Cost per tracked action (SEK)"),
            tooltip=["week_start", "spend", "tracked_actions",
                     "cost_per_tracked_action"],
        )
        st.altair_chart(chart, use_container_width=True)
        st.write("Weeks start on Monday, from the daily data.")
        st.dataframe(dashboard_data.display_table(table),
                     use_container_width=True)
        return
    table = dashboard_data.trend_for_campaign(timeline, campaign)
    chart = alt.Chart(table).mark_line(point=True).encode(
        x=alt.X("month", title="Month"),
        y=alt.Y("cost_per_tracked_action",
                title="Cost per tracked action (SEK)"),
        color=alt.Color("source", title="Source"),
        tooltip=["month", "source", "spend", "tracked_actions",
                 "cost_per_tracked_action"],
    )
    st.altair_chart(chart, use_container_width=True)
    st.write(
        "Source marks where each month comes from: day is the "
        "daily export, month is the monthly-history export."
    )
    st.dataframe(dashboard_data.display_table(table),
                 use_container_width=True)


def _page_recommendations(tables, caveat, date_range, updated):
    """Recommendations: small table, then one block per campaign."""
    st.header("Recommendations")
    _context(caveat, date_range, updated)
    table = dashboard_data.recommendations_display(
        tables["recommendations_by_campaign"])
    st.dataframe(
        table[["campaign", "label", "status_now",
               "recent_trend"]],
        use_container_width=True,
        column_config={
            "campaign": st.column_config.TextColumn(
                "Campaign", width="large"),
            "label": st.column_config.TextColumn(
                "Label", width="medium"),
        },
    )
    for _, row in table.iterrows():
        st.subheader(row["campaign"])
        st.markdown(
            f"**Label:** {row['label']}  \n"
            f"**Status:** {row['status_now']}  \n"
            f"**Recent trend:** {row['recent_trend']}  \n"
            "**Ratio vs run average:** "
            f"{dashboard_data.format_ratio(row['ratio_vs_run_average'])}  \n"
            f"**Action:** {row['action_text']}  \n"
            f"**Reason:** {row['reason']}"
        )


PAGES = {
    "What counts as a tracked action": _page_conversion,
    "Overview": _page_overview,
    "Campaign comparison": _page_comparison,
    "Runs": _page_runs,
    "Weekday": _page_weekday,
    "Trend": _page_trend,
    "Recommendations": _page_recommendations,
}


def main():
    """Load the result tables and show the selected page."""
    st.set_page_config(layout="wide")
    st.title("CampaignCompass")
    config = dashboard_data.load_config()
    caveat = dashboard_data.caveat_text(config)
    try:
        tables = dashboard_data.load_tables(config)
    except FileNotFoundError:
        st.error("Run bash run.sh first")
        st.stop()
    paths = dashboard_data.table_paths(config)
    date_range = dashboard_data.data_date_range(
        tables["campaign_summary_day"])
    updated = dashboard_data.last_updated(paths.values())
    page = st.sidebar.radio("Page", list(PAGES))
    PAGES[page](tables, caveat, date_range, updated)


if __name__ == "__main__":
    main()
