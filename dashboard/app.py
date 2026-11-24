"""Local Streamlit dashboard (T8, reworked in PR 4, restyled in PR 5).

Run it with: bash dashboard.sh (after bash run.sh). It listens
on localhost only.

Three pages (PR 5): Act (which campaigns to continue, test or
pause), Context (can we trust this?) and Campaign detail (opened
from the Act ranking or picked directly). Charts are Plotly,
built in dashboard/charts.py.

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

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import data as dashboard_data  # noqa: E402

WIDE = st.column_config.TextColumn  # shorthand below
NUM = st.column_config.NumberColumn
PAGE_KEY = "page"
DETAIL_KEY = "detail_campaign"
# Widgets whose options depend on the client: reset on a switch.
CLIENT_WIDGETS = ("act_group", "act_status", "act_pick", DETAIL_KEY,
                  "ctx_trend_campaign", "ctx_weekday")

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
.cc-table {width: 100%; border-collapse: collapse; font-size: 0.92rem;
           margin: 0.4rem 0 1rem;}
.cc-table th {text-align: left; color: #1F3A5F; font-weight: 600;
              border-bottom: 2px solid #1F3A5F; padding: 0.5rem 0.6rem;}
.cc-table td {border-bottom: 1px solid #E6E9EF; padding: 0.55rem 0.6rem;
              vertical-align: top;}
.cc-table .n {text-align: right; white-space: nowrap;}
.cc-table .nw {white-space: nowrap;}
.cc-table .lab {font-weight: 600; white-space: nowrap; color: #1C2430;}
.cc-todo {border: 2px solid #1F3A5F; border-radius: 0.6rem;
          padding: 0.9rem 1.1rem; margin: 0.4rem 0 1.2rem;
          background: #F4F7FB; color: #1C2430; font-size: 1.05rem;
          line-height: 1.6;}
.cc-todo .cc-counts {color: #5B6573; font-size: 0.95rem;}
.cc-todo .cc-first {font-size: 1.15rem;}
.cc-take {font-size: 1.05rem; color: #1C2430; margin: -0.2rem 0 0.8rem;}
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


# --- Act ----------------------------------------------------------

def _fmt(value, pattern):
    """A formatted number, or an em dash for a missing one."""
    if value is None or pd.isna(value):
        return "—"
    return pattern.format(value)


def _action_html(table):
    """The ranked action table as HTML: text wraps, nothing is cut.

    The label cell is tinted with the label colour and also names
    the label in text (with its symbol).
    """
    head = ("<tr><th>#</th><th>Campaign</th><th>Final label</th>"
            "<th>Status</th><th class='n'>Ratio</th>"
            "<th class='n'>Tracked actions</th><th>Trend</th>"
            "<th>Action</th><th>Label period</th></tr>")
    body = []
    for _, row in table.iterrows():
        colour = dashboard_data.label_colour(row["label"])
        body.append(
            "<tr>"
            f"<td class='n'>{int(row['rank'])}</td>"
            f"<td><b>{html.escape(str(row['campaign']))}</b></td>"
            f"<td class='lab' style='background:{_tint(colour)};"
            f"border-left:4px solid {colour}'>"
            f"{html.escape(row['final_label'])}</td>"
            f"<td>{html.escape(str(row['status_now']))}</td>"
            f"<td class='n'>{_fmt(row['ratio_to_benchmark'], '{:.2f}x')}</td>"
            f"<td class='n'>{_fmt(row['tracked_actions'], '{:,.0f}')}</td>"
            f"<td>{html.escape(_readable(row['recent_trend']))}</td>"
            f"<td>{html.escape(_readable(row['action'], keep=True))}</td>"
            f"<td class='nw'>{html.escape(str(row['label_period'] or '—'))}"
            "</td></tr>")
    return (f"<table class='cc-table'><thead>{head}</thead>"
            f"<tbody>{''.join(body)}</tbody></table>")


def _readable(value, keep=False):
    """Text for a cell: empty for missing; underscores to spaces."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "—"
    return str(value) if keep else str(value).replace("_", " ")




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


def _todo_html(summary):
    """The "What to do" box: running campaigns, ended campaigns not to
    restart as they were, then the label counts. Every data value is
    escaped."""
    def item(entry):
        label = html.escape(dashboard_data.label_text(entry["label"]))
        action = (f": {html.escape(entry['action'])}"
                  if entry["action"] else "")
        return (f"<b>{html.escape(entry['campaign'])}</b> "
                f"({label}){action}")

    running = summary["running"]
    lead = ("Running now: " + "; ".join(item(e) for e in running)
            if running else "Running now: no campaign is active.")
    lines = [f"<div class='cc-first'>{lead}</div>"]
    if summary["ended"]:
        lines.append("<div>Ended: " + "; ".join(
            item(e) for e in summary["ended"]) + "</div>")
    if summary["restart"]:
        lines.append("<div>Worth restarting: " + "; ".join(
            item(e) for e in summary["restart"]) + "</div>")
    counts = " · ".join(
        f"{html.escape(dashboard_data.label_text(label))} {count}"
        for label, count in summary["counts"])
    lines.append(f"<div class='cc-counts'>{counts}</div>")
    return f"<div class='cc-todo'>{''.join(lines)}</div>"


def _totals_scope(ctx, kpi):
    """The two scopes: what the totals cover, what the benchmark uses."""
    judged, bench = dashboard_data.scope_groups(
        ctx["config"], ctx["tables"]["benchmarks"])
    too_little = dashboard_data.too_little_data_count(
        ctx["all_recommendations"], judged)
    return dashboard_data.totals_scope_text(
        kpi["judged_campaigns"], judged, too_little, bench)


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

    # 1. What to do: all campaigns, never filtered.
    st.markdown("#### What to do")
    st.markdown(_todo_html(dashboard_data.act_summary(recs)),
                unsafe_allow_html=True)

    # 2. The ranked table (the filters only hide rows and bubbles).
    st.markdown("#### What should we do, most urgent first?")
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
    st.caption("Pause or review first, then test, then continue; within "
               "a label, the highest ratio to the benchmark first. "
               "Ratio = cost per tracked action in the label period / "
               "its benchmark. Costs and group are in the CSV.")
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
        st.markdown(_action_html(table), unsafe_allow_html=True)
        picks = st.columns([2, 1, 1], vertical_alignment="bottom")
        campaign = picks[0].selectbox(
            "Open a campaign's detail", list(table["campaign"]),
            key="act_pick")
        picks[1].button("Open detail", on_click=_open_detail,
                        args=(campaign,), type="primary",
                        key="act_open")
        picks[2].download_button(
            "Download CSV",
            dashboard_data.csv_bytes(table.drop(columns=["label"])),
            file_name="actions.csv", mime="text/csv",
            key="act_download")

    # 3. The bubble chart.
    kpi = dashboard_data.kpi_values(tables["benchmarks"])
    st.write("")
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

    # 4. Not comparable.
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

    # 5. Totals and benchmark.
    st.write("")
    with st.expander("Totals and benchmark"):
        scope = _totals_scope(ctx, kpi)
        cards = st.columns(4)
        _card(cards[0], "Spend", f"{kpi['spend']:,.0f} {currency}",
              "Total spend of the campaigns in the totals.")
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
        st.caption(f"{scope} Totals use the whole daily range "
                   f"(benchmarks.csv); the filters do not change them.")

    # 6. How to read this.
    with st.expander("How to read this"):
        _footnotes(_act_definitions(ctx, kpi))


# --- Context ------------------------------------------------------

BENCHMARK_NAMES = {
    "benchmark": "Benchmark (pooled, the one used)",
    "with_not_comparable": "Including not-comparable groups",
    "judged_campaigns": "Judged campaigns (KPI cards)",
}


def _section(question):
    """A tab's question heading on the Context page."""
    st.markdown(f"### {question}")


def _takeaway(text):
    """The one-sentence takeaway under a tab's question."""
    st.markdown(f"<p class='cc-take'>{html.escape(text)}</p>",
                unsafe_allow_html=True)


def _context_trend(ctx):
    """Recent change: recent vs prior window per active campaign."""
    tables = ctx["tables"]
    currency = ctx["currency"]
    _section("Has performance changed recently?")
    rows = dashboard_data.recent_trend_rows(
        tables["recent_trend"], ctx["all_recommendations"])
    _takeaway(dashboard_data.trend_takeaway(rows))
    if rows.empty:
        return
    st.plotly_chart(charts.recent_vs_prior_bar(rows, currency),
                    width="stretch", key="ctx_recent_chart")
    st.caption("Cost per tracked action in the recent window against "
               "the prior window, for active campaigns.")
    with st.expander("Recent trend table"):
        _table(rows.drop(columns=["recent_tracked_actions"]),
               "recent_trend.csv", key="ctx_recent",
               column_config={
                   "campaign": WIDE("Campaign", pinned=True),
                   "final_label": WIDE("Final label"),
                   "recent_trend": WIDE("Trend"),
                   "recent_window": WIDE("Recent window"),
                   "recent_cost_per_tracked_action": NUM(
                       f"Recent ({currency})", format="%.2f"),
                   "prior_window": WIDE("Prior window"),
                   "prior_cost_per_tracked_action": NUM(
                       f"Prior ({currency})", format="%.2f"),
                   "recent_vs_prior_ratio": NUM(
                       "Recent / prior", format="%.2fx"),
               })


def _context_completeness(ctx):
    """Data completeness: monthly trend with incomplete months, lag."""
    tables = ctx["tables"]
    currency = ctx["currency"]
    _section("Is the latest data complete?")
    config = ctx["config"]
    configured = (config.get("analysis", {}).get("recent_trend", {})
                  .get("conversion_lag_days"))
    lag_check = ctx["optional"]["lag_check"]
    summary = None
    if lag_check is None:
        st.info("The lag check is not turned on for this client "
                "(recent_trend.lag_check_days in its config).")
    else:
        summary = dashboard_data.lag_check_summary(lag_check)
        _takeaway(dashboard_data.lag_takeaway(summary, configured))
    timeline = tables["timeline_by_campaign"]
    campaigns = sorted(set(timeline["campaign"]))
    if campaigns:
        rows = dashboard_data.recent_trend_rows(
            tables["recent_trend"], ctx["all_recommendations"])
        active = [name for name in rows["campaign"] if name in campaigns]
        default = active[0] if active else campaigns[0]
        campaign = st.selectbox("Campaign for the monthly trend",
                                campaigns, index=campaigns.index(default),
                                key="ctx_trend_campaign")
        table = dashboard_data.trend_with_flags(timeline, campaign)
        st.plotly_chart(charts.trend_line(table, "month", "Month",
                                          currency),
                        width="stretch", key="ctx_trend_chart")
        st.caption("Hollow ring = partial month (the campaign ran only "
                   "part of it) or lagged month (days still being "
                   "reported). Do not read a jump in those months as a "
                   "change.")
    if summary is not None:
        with st.expander("Lag check by lag"):
            st.caption("Tracked actions can arrive days late. The lag "
                       "check reruns the recent signals with other lags "
                       "and counts what changes.")
            _table(summary, "lag_check_summary.csv", key="ctx_lag",
                   column_config={
                       "lag": NUM("Lag (days)", format="%d"),
                       "trend_changes": NUM("Trend changes", format="%d"),
                       "label_changes": NUM("Label changes",
                                            format="%d")})
        with st.expander("All lag-check counts"):
            _table(lag_check, "lag_check.csv", key="ctx_lag_all")


def _context_weekday(ctx):
    """Weekdays and spend: weekday chart, one-day breakdown, what-if."""
    tables = ctx["tables"]
    optional = ctx["optional"]
    currency = ctx["currency"]
    _section("Do weekdays differ, and would moving spend help?")
    try:
        pooled = dashboard_data.weekday_core_table(tables["weekday_core"])
    except ValueError as exc:
        st.error(str(exc))
        return
    rows, span = dashboard_data.what_if_parts(
        tables["what_if_weekday_shift"])
    scenario = (rows["scenario"].iloc[0]
                if "scenario" in rows.columns and not rows.empty else None)
    change = span["display"] if span is not None else (
        rows["display"].iloc[0]
        if "display" in rows.columns and not rows.empty else None)
    _takeaway(dashboard_data.weekday_takeaway(pooled, currency, change,
                                              scenario))
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
                   f"with the most pooled clicks. Pooled over the time "
                   f"groups in the config.")
    note = rows["note"].iloc[0] if "note" in rows.columns \
        and not rows.empty else ""
    if note:
        st.warning(f"{note}.", icon="⚠️")
    with st.expander("Pooled weekday table"):
        _table(dashboard_data.display_table(pooled), "weekday_pooled.csv",
               key="ctx_weekday_pooled")
    if mix is None or loo is None:
        st.info("The weekday decomposition is not turned on for this "
                "client (analysis.weekday_decomposition in its config).")
    else:
        label = full.get(focus, focus) if focus else "one weekday"
        with st.expander(f"Is one campaign distorting {label}?"):
            _weekday_breakdown(mix, loo, top, focus)
    with st.expander("What would moving spend do?"):
        _what_if(rows, span, currency)


def _weekday_breakdown(mix, loo, top, focus):
    """Who makes up one weekday, and the weekday with each left out."""
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
        loo_table = dashboard_data.leave_one_out_for_weekday(
            loo, weekday)
        loo_columns = [column for column in (
            "left_out", "actions_per_click_vs_baseline",
            "actions_per_click", "clicks") if column in loo_table]
        _table(loo_table[loo_columns],
               f"weekday_leave_one_out_{weekday}.csv", key="ctx_loo",
               column_config={
                   "left_out": WIDE("Left out", pinned=True),
                   "actions_per_click_vs_baseline": NUM(
                       "vs Mon-Thu", format="%.2fx"),
                   "actions_per_click": NUM("Actions / click",
                                            format="%.3f"),
                   "clicks": NUM("Clicks", format="%.0f")})
    if top is not None and not top.empty:
        top_weekday = top["weekday"].iloc[0]
        st.markdown(f"**Top {len(top)} {top_weekday}s by pooled clicks** "
                    f"(together {top['share_of_weekday_clicks'].sum():.1%}"
                    f" of {top_weekday} clicks)")
        _table(top, "weekday_top_days.csv", key="ctx_top")


def _what_if(rows, span, currency):
    """Moving weekday spend to the weekend, per variant of the groups."""
    if span is not None:
        with st.container(border=True):
            st.metric("Change in tracked actions, range across variants",
                      span["display"])
    columns = [column for column in (
        "groups", "scenario", "spend_moved",
        "tracked_actions_before", "tracked_actions_after", "display")
        if column in rows.columns]
    shown = rows[columns].copy()
    for column in ("spend_moved", "tracked_actions_before",
                   "tracked_actions_after"):
        if column in shown.columns:
            shown[column] = shown[column].round(0)
    _table(shown, "what_if.csv", key="ctx_what_if", column_config={
        "groups": WIDE("Groups"),
        "scenario": WIDE("Scenario"),
        "spend_moved": NUM(f"Spend moved ({currency})", format="%.0f"),
        "tracked_actions_before": NUM("Actions before", format="%.0f"),
        "tracked_actions_after": NUM("Actions after", format="%.0f"),
        "display": WIDE("Change")})


def _context_journey(ctx):
    """How people reach us: directions, calls, store visits."""
    tables = ctx["tables"]
    _section("How do people reach the restaurant?")
    journey_raw = tables["journey_by_campaign"]
    _takeaway(dashboard_data.journey_takeaway(journey_raw))
    long = dashboard_data.journey_intent_long(journey_raw)
    if long.empty:
        st.caption("No journey rows.")
    else:
        st.plotly_chart(charts.intent_stack(long), width="stretch",
                        key="ctx_journey_chart")
    with st.expander("Journey table"):
        journey = dashboard_data.display_table(
            dashboard_data.journey_display(journey_raw)).rename(columns={
                "directions share": "directions share (%)",
                "calls share": "calls share (%)",
                "store visits share": "store visits share (%)"})
        _table(journey, "journey.csv", key="ctx_journey", column_config={
            "campaign": WIDE("Campaign", width="large", pinned=True)})
    break_even = ctx["break_even"]
    if break_even is not None:
        with st.expander("Break-even (illustration: tracked actions are "
                         "not visits)"):
            _table(dashboard_data.display_table(break_even),
                   "break_even.csv", key="ctx_break_even", column_config={
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
    """Can we trust this? Four tabs, then method and definitions."""
    _title("Context: can we trust this?",
           "Checks to read before acting on a label. Each tab answers "
           "one question.", level=1)
    _context(ctx)
    recent, weekdays, completeness, journey = st.tabs([
        "Recent change", "Weekdays and spend", "Data completeness",
        "How people reach us"])
    with recent:
        _context_trend(ctx)
    with weekdays:
        _context_weekday(ctx)
    with completeness:
        _context_completeness(ctx)
    with journey:
        _context_journey(ctx)
    _context_method(ctx)


# --- Campaign detail ----------------------------------------------

def _period_slider(values, label, key):
    """A from-to slider over the sorted periods; returns (start, end)."""
    options = sorted(set(str(value) for value in values))
    if len(options) < 2:
        return None, None
    return st.select_slider(label, options=options,
                            value=(options[0], options[-1]), key=key)


def _detail_trend(ctx, campaign):
    """Monthly or weekly cost per tracked action for one campaign.

    The period slider limits the rows shown (a filter, not a
    recalculation). Partial and lagged months are marked.
    """
    tables = ctx["tables"]
    currency = ctx["currency"]
    view = st.radio("View", ["Monthly", "Weekly"], horizontal=True,
                    key="detail_view")
    if view == "Monthly":
        table = dashboard_data.trend_with_flags(
            tables["timeline_by_campaign"], campaign)
        x_field, x_title, key = "month", "Month", "month"
    else:
        table = dashboard_data.weekly_for_campaign(
            tables["weekly_by_campaign"], campaign)
        x_field, x_title, key = "week_start", "Week starting", "week"
    if table.empty:
        st.caption("No monthly or weekly rows: the trend tables cover "
                   "the time groups in the config.")
        return
    start, end = _period_slider(table[x_field], "Period",
                                f"detail_period_{key}")
    table = dashboard_data.filter_period(table, x_field, start, end)
    st.plotly_chart(charts.trend_line(table, x_field, x_title, currency),
                    width="stretch", key=f"detail_trend_{key}")
    if "month_note" in table.columns:
        st.caption("Hollow ring = partial or lagged month. Monthly "
                   "source: day is the daily export, month is the "
                   "monthly-history export.")
    with st.expander(f"{view} table"):
        _table(dashboard_data.display_table(table),
               f"{key}ly_{campaign}.csv", key=f"detail_trend_table_{key}",
               column_config={"month note": WIDE("Month note",
                                                 width="medium")})


def _page_detail(ctx):
    """One campaign: cards, action and reasons, runs, trend, weekday,
    journey."""
    _title("Campaign detail",
           "Everything behind one campaign's label. Open it from the "
           "ranked table on the Act page, or pick a campaign here.",
           level=1)
    _context(ctx)
    tables = ctx["tables"]
    currency = ctx["currency"]
    recs = ctx["all_recommendations"]
    ranked = list(dashboard_data.action_table(recs)["campaign"])
    options = ranked + sorted(set(recs["campaign"]) - set(ranked))
    if not options:
        st.info("No campaigns.")
        return
    if st.session_state.get(DETAIL_KEY) not in options:
        st.session_state[DETAIL_KEY] = options[0]
    campaign = st.selectbox(
        "Campaign", options, key=DETAIL_KEY,
        help="Ordered as in the Act ranking; not-comparable last.")
    detail = dashboard_data.campaign_detail(
        recs, tables["recent_trend"], campaign)
    row = recs.set_index("campaign").loc[campaign]
    ratio = row.get("label_ratio")

    cards = st.columns(4)
    with cards[0].container(border=True):
        st.markdown("Final label")
        st.markdown(_badge(detail["label"]), unsafe_allow_html=True)
        st.caption(f"From {detail['label_from'].replace('_', ' ')}"
                   + (f", {detail['label_period']}"
                      if detail["label_period"] else ""))
    _card(cards[1], "Status now",
          (detail["status_now"] or "—").replace("_", " "),
          "Active if it ran in the last days of the data.")
    _card(cards[2], "Recent trend",
          (detail["recent_trend"] or "—").replace("_", " "),
          "Recent window against the prior window.")
    _card(cards[3], "Ratio to benchmark",
          f"{ratio:.2f}x" if ratio is not None and not pd.isna(ratio)
          else "—",
          "Cost per tracked action in the label period / its benchmark.")

    with st.container(border=True):
        st.markdown(f"**Action:** {detail['action']}")
        st.markdown("**Why this label**")
        st.write(detail["reason"])
        if detail["trend_window"]:
            st.markdown(f"**Trend** (recent window {detail['trend_window']}"
                        f", prior window {detail['prior_window']})")
            st.write(detail["trend_reason"])
        else:
            st.caption("No recent trend: the campaign is not active or "
                       "its group is not judged.")

    st.write("")
    _title("Runs", "Each run judged on its own; the final label comes "
           "from the latest run with enough volume or the recent "
           "window.", level=3)
    runs = dashboard_data.run_recommendations_for_campaign(
        tables["recommendations_by_run"], campaign)
    if runs.empty:
        st.caption("No runs: runs are built only for the run groups in "
                   "the config.")
    else:
        runs["run_label"] = runs["run_label"].map(
            dashboard_data.label_text)
        order = [column for column in (
            "run_number", "run_label", "start", "end", "active_days",
            "spend", "conversions", "cost_per_conversion",
            "ratio_to_benchmark") if column in runs.columns]
        runs = runs[order]
        # Number formats live in the Styler, not column_config, so
        # missing values show as "—" (column_config formats would win
        # over na_rep and show "None"). Values stay numeric for sorting.
        styled = _styled(runs, ["run_label"]).format({
            "run_number": "{:d}", "active_days": "{:.0f}",
            "spend": "{:,.0f}", "conversions": "{:,.0f}",
            "cost_per_conversion": "{:,.2f}",
            "ratio_to_benchmark": "{:.2f}x",
        }, na_rep="—", subset=list(runs.columns))
        st.dataframe(styled, hide_index=True,
                     width="stretch", key="detail_runs", column_config={
                         "run_number": NUM("Run"),
                         "run_label": WIDE("Run label"),
                         "start": WIDE("Start"),
                         "end": WIDE("End"),
                         "active_days": NUM("Days"),
                         "spend": NUM(f"Spend ({currency})"),
                         "conversions": NUM("Tracked actions"),
                         "cost_per_conversion": NUM(
                             f"Cost per action ({currency})"),
                         "ratio_to_benchmark": NUM("Ratio")})
        st.download_button("Download CSV",
                           dashboard_data.csv_bytes(
                               dashboard_data.display_table(runs)),
                           file_name=f"runs_{campaign}.csv",
                           mime="text/csv", key="detail_runs_download")

    st.write("")
    _title("Trend", "Cost per tracked action over time.", level=3)
    _detail_trend(ctx, campaign)

    st.write("")
    _title("Weekday pattern", "This campaign's cost per tracked action "
           "by weekday.", level=3)
    by_campaign = tables["weekday_by_campaign"]
    if campaign not in set(by_campaign["campaign"]):
        st.caption("No weekday rows: weekday tables cover the time "
                   "groups in the config.")
    else:
        weekday = dashboard_data.weekday_campaign_table(
            by_campaign, campaign)
        st.plotly_chart(charts.weekday_bar(weekday, currency),
                        width="stretch", key="detail_weekday")
        with st.expander("Weekday table"):
            _table(dashboard_data.display_table(weekday),
                   f"weekday_{campaign}.csv", key="detail_weekday_table")

    st.write("")
    _title("Acquisition journey", "How this campaign's tracked actions "
           "split into directions, calls and store visits.", level=3)
    journey = dashboard_data.journey_row(
        tables["journey_by_campaign"], campaign)
    if journey.empty:
        st.caption("No journey row: the journey covers the time groups "
                   "in the config.")
    else:
        long = dashboard_data.journey_intent_long(journey)
        st.plotly_chart(charts.intent_stack(long), width="stretch",
                        key="detail_journey_chart")
        keep = [column for column in (
            "spend", "clicks", "tracked_actions", "engagement_actions",
            "tracked_actions_per_click", "cost_per_tracked_action")
            if column in journey.columns]
        _table(journey[keep], key="detail_journey", column_config={
            "spend": NUM(f"Spend ({currency})", format="%.0f"),
            "clicks": NUM("Clicks", format="%.0f"),
            "tracked_actions": NUM("Tracked actions", format="%.0f"),
            "engagement_actions": NUM("Engagement actions",
                                      format="%.0f"),
            "tracked_actions_per_click": NUM("Actions / click",
                                             format="%.3f"),
            "cost_per_tracked_action": NUM(
                f"Cost per action ({currency})", format="%.2f")})


PAGES = {
    "Act": _page_act,
    "Context": _page_context,
    "Campaign detail": _page_detail,
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
    if st.session_state.get("_client") != client:
        for key in CLIENT_WIDGETS:
            st.session_state.pop(key, None)
        st.session_state["_client"] = client
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
