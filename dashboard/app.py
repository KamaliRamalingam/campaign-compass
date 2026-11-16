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


def _page_conversion(tables, caveat, date_range, updated,
                     currency="SEK"):
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


def _page_overview(tables, caveat, date_range, updated,
                     currency="SEK"):
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


def _page_comparison(tables, caveat, date_range, updated,
                     currency="SEK"):
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
                title=f"Cost per tracked action ({currency})"),
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


def _page_runs(tables, caveat, date_range, updated,
                     currency="SEK"):
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
                title=f"Cost per tracked action ({currency})"),
        tooltip=["run_number", "start", "end", "spend",
                 "cost_per_tracked_action", "volume_flag"],
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(dashboard_data.display_table(table),
                 use_container_width=True)


def _page_weekday(tables, caveat, date_range, updated,
                     currency="SEK"):
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
                title=f"Cost per tracked action ({currency})"),
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


def _page_trend(tables, caveat, date_range, updated,
                     currency="SEK"):
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
                    title=f"Cost per tracked action ({currency})"),
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
                title=f"Cost per tracked action ({currency})"),
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


def _page_recommendations(tables, caveat, date_range, updated,
                     currency="SEK"):
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
            "**Ratio vs prior 28 days:** "
            f"{dashboard_data.format_ratio(row['recent_vs_prior_ratio'])}  \n"
            f"**Trend reason:** {row['trend_reason']}  \n"
            f"**Action:** {row['action_text']}  \n"
            f"**Reason:** {row['reason']}"
        )


def _page_journey(tables, caveat, date_range, updated,
                  currency="SEK"):
    """Acquisition journey, what-if and break-even."""
    st.header("Acquisition journey")
    _context(caveat, date_range, updated)
    st.subheader("Journey by campaign")
    st.dataframe(
        dashboard_data.display_table(
            dashboard_data.journey_display(
                tables["journey_by_campaign"])).rename(columns={
            "directions share": "directions share (%)",
            "calls share": "calls share (%)",
            "store visits share": "store visits share (%)",
        }),
        use_container_width=True,
        column_config={
            "campaign": st.column_config.TextColumn(
                "Campaign", width="large"),
        },
    )
    st.write(
        "Intent shares are shares of tracked actions. "
        "Engagement actions are All conv. of the engagement "
        "action group."
    )
    campaigns = dashboard_data.journey_campaigns(
        tables["journey_by_campaign"])
    import altair as alt
    chart = alt.Chart(campaigns).mark_bar().encode(
        x=alt.X("tracked_actions_per_click",
                title="Tracked actions per click"),
        y=alt.Y("campaign", sort="-x", title="Campaign"),
        tooltip=["campaign", "tracked_actions_per_click",
                 "cost_per_tracked_action"],
    )
    st.altair_chart(chart, use_container_width=True)
    st.subheader("What-if: weekday spend to the weekend")
    st.dataframe(
        dashboard_data.display_table(
            tables["what_if_weekday_shift"]),
        use_container_width=True,
    )
    break_even = tables.get("break_even")
    if break_even is not None:
        st.subheader("Break-even")
        st.dataframe(
            dashboard_data.display_table(break_even),
            use_container_width=True,
            column_config={
                "campaign": st.column_config.TextColumn(
                    "Campaign", width="large"),
            },
        )
        st.write(
            "Illustration: tracked actions are not visits."
        )


PAGES = {
    "What counts as a tracked action": _page_conversion,
    "Overview": _page_overview,
    "Campaign comparison": _page_comparison,
    "Runs": _page_runs,
    "Weekday": _page_weekday,
    "Trend": _page_trend,
    "Recommendations": _page_recommendations,
    "Acquisition journey": _page_journey,
}


def main():
    """Load the result tables and show the selected page."""
    st.set_page_config(layout="wide")
    st.title("CampaignCompass")
    clients = dashboard_data.list_clients()
    client = st.sidebar.selectbox("Client", clients, index=0)
    repo_root = Path(__file__).resolve().parents[1]
    if client == "restaurant":
        config = dashboard_data.load_config()
        output_root = None
    else:
        client_config = repo_root / "config" / f"{client}.yaml"
        config = (dashboard_data.load_config(client_config)
                  if client_config.is_file()
                  else dashboard_data.load_config())
        output_root = repo_root / "outputs" / client
    caveat = dashboard_data.caveat_text(config)
    currency = config.get("currency", "SEK")
    try:
        tables = dashboard_data.load_tables(
            config, output_root=output_root)
    except FileNotFoundError:
        st.error("Run bash run.sh first")
        st.stop()
    # The break-even table exists only when the config sets a
    # revenue value; the journey page shows it only then.
    tables["break_even"] = dashboard_data.load_break_even(
        config, output_root=output_root)
    paths = dashboard_data.table_paths(
        config, output_root=output_root)
    date_range = dashboard_data.data_date_range(
        tables["campaign_summary_day"])
    updated = dashboard_data.last_updated(paths.values())
    page = st.sidebar.radio("Page", list(PAGES))
    PAGES[page](tables, caveat, date_range, updated, currency)


if __name__ == "__main__":
    main()
