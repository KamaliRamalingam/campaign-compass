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

import base64
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
DETAIL_KEY = "detail_campaign"
# Widgets whose options depend on the client: reset on a switch.
CLIENT_WIDGETS = ("act_group", "act_status", "act_pick", DETAIL_KEY,
                  "ctx_trend_campaign", "ctx_weekday")

# Warm spice theme (redesign). Colours: text #3B2F2A, secondary
# #7A6B5F (#6B5E54 inside tinted tiles, for 4.5:1), card border
# #EADFCF, brand green #254C31 only for the header line, the active
# tab and buttons. Open Sans from Google Fonts; Helvetica / Arial
# when offline.
GREEN = "#254C31"
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap');
html, body, .stApp, .stApp p, .stApp div, .stApp label, .stApp input,
.stApp button, .stApp td, .stApp th, .stApp li, .stApp a {
  font-family: 'Open Sans', Helvetica, Arial, sans-serif;}
[data-testid="stIconMaterial"], .material-symbols-rounded {
  font-family: 'Material Symbols Rounded' !important;}
.stApp {background: #FBF6EE; color: #3B2F2A;}
.block-container {padding: 80px 24px 3rem; max-width: 1600px;}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"]
  {display: none;}
[data-testid="stVerticalBlock"] {gap: 16px;}
[data-testid="stHorizontalBlock"] {gap: 16px;}
h1, h2, h3, h4 {color: #3B2F2A !important;}
p, li, td, th {font-size: 14px;}

/* Header: white, 3px green line. */
[data-testid="stHeader"], [data-testid="stAppHeader"]
  {background: #FFFFFF; border-bottom: 3px solid #254C31;}
/* Our header row sits over Streamlit's header bar: brand at the
   left, client picker at the far right; the page links (in the bar)
   are pushed right, next to the picker. */
.st-key-cc_header {position: fixed; top: 0; left: 0; right: 0;
  height: 60px; z-index: 1000000; padding: 0 24px; background: transparent;
  pointer-events: none; display: flex; justify-content: center;}
.st-key-cc_header > div {pointer-events: none;}
.st-key-cc_header img, .st-key-cc_header [data-testid="stSelectbox"],
.st-key-cc_header [data-baseweb] {pointer-events: auto;}
[data-testid="stHeader"] {height: 60px;}
[data-testid="stToolbar"] {height: 60px; align-items: center;}
[data-testid="stTopNav"] {justify-content: flex-end; padding-right: 230px;}
.cc-brand {display: flex; align-items: center; gap: 16px;}
.cc-logo {height: 40px; width: auto; display: block;}
.cc-divider {width: 1px; height: 36px; background: #D9CFC0;}
.cc-wordmark {font-size: 14px; font-weight: 600; letter-spacing: 0.25em;
  text-transform: uppercase; color: #7A6B5F;}
[data-testid="stTopNavLink"] {font-size: 13px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em; color: #3B2F2A;
  border-radius: 4px; padding: 4px 14px;}
[data-testid="stTopNavLink"] p {font-size: 13px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em; color: inherit;}
[data-testid="stTopNavLink"][aria-current="page"]
  {background: #254C31; color: #FFFFFF;}
[data-testid="stTopNavLink"][aria-current="page"] *
  {color: #FFFFFF;}

/* Heading block. */
.stApp .cc-page {font-size: 12px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.08em; color: #254C31; margin: 0;}
.stApp .cc-q {font-size: 26px; font-weight: 600; color: #3B2F2A; margin: 2px 0;
  line-height: 1.25;}
.stApp .cc-data {font-size: 13px; font-weight: 400; color: #7A6B5F; margin: 0;}

/* Caveat banner: white, warm border, charcoal text. */
[data-testid="stAlert"] > div {background: #FFFFFF; color: #3B2F2A;
  border: 1px solid #EADFCF;}
[data-testid="stAlert"] p {color: #3B2F2A;}

/* Cards. */
[data-testid="stVerticalBlockBorderWrapper"],
.st-key-cc_card, div[class*="st-key-card_"]
  {background: #FFFFFF; border-color: #EADFCF !important;}
[data-testid="stExpander"] details {background: #FFFFFF;
  border-color: #EADFCF;}
.cc-card-title {font-size: 18px; font-weight: 600; margin: 0 0 4px;
  color: #3B2F2A;}

/* Buttons. */
.stButton button[kind="primary"], .stDownloadButton button,
.stButton button {background: #254C31; color: #FFFFFF;
  border-color: #254C31;}
.stButton button:hover, .stDownloadButton button:hover
  {background: #1C3A25; color: #FFFFFF; border-color: #1C3A25;}

/* Labels: soft tint, coloured left border, symbol and dark text. */
.cc-pill {display: inline-block; padding: 2px 10px; border-radius: 4px;
  font-weight: 600; font-size: 13px; color: #3B2F2A; white-space: nowrap;
  border-left: 3px solid;}
.cc-badge {display: inline-block; padding: 6px 14px; border-radius: 6px;
  font-weight: 600; font-size: 20px; color: #3B2F2A; border-left: 5px solid;}
.cc-foot {color: #7A6B5F; font-size: 13px; line-height: 1.5;}
.cc-take {font-size: 14px; color: #3B2F2A; margin: 0 0 8px;}
.cc-muted {color: #7A6B5F; font-size: 13px;}

/* Tables. */
.cc-table {width: 100%; border-collapse: collapse; font-size: 14px;
  margin: 0 0 8px;}
.cc-table th {text-align: left; color: #7A6B5F; font-size: 12px;
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
  border-bottom: 1px solid #EADFCF; padding: 8px 8px; background: #FBF6EE;}
.cc-table td {border-bottom: 1px solid #EADFCF; padding: 8px 8px;
  vertical-align: top;}
.cc-table .n {text-align: right; white-space: nowrap;}
.cc-table .nw {white-space: nowrap;}
.cc-table .per {font-size: 13px;}
.cc-table .cmp {min-width: 9em;}
.cc-table .act {width: 100%;}
.cc-clamp {display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;}

/* Decision tiles. */
.cc-tiles {display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 16px; align-items: stretch;}
.cc-tile {border-radius: 8px; padding: 14px 16px; border-left: 5px solid;
  color: #3B2F2A; min-height: 150px;}
.cc-tile-head {display: flex; align-items: baseline; gap: 12px;}
.cc-tile-count {font-size: 36px; font-weight: 300; line-height: 1;}
.cc-tile-label {font-size: 15px; font-weight: 600;}
.cc-tile-line {font-size: 13px; font-weight: 400; line-height: 1.4;
  margin-top: 6px;}
.cc-tile-more {font-size: 13px; color: #6B5E54; margin-top: 6px;}
.cc-run {color: #6B5E54; white-space: nowrap;}
@media (max-width: 900px) {.cc-tiles {grid-template-columns: 1fr 1fr;}}

/* Context: recent-window rows, what-if tile, tags. */
.cc-tag {display: inline-block; border: 1px solid #3B2F2A;
  border-radius: 4px; padding: 0 6px; font-size: 12px; font-weight: 600;
  color: #3B2F2A; background: #FFFFFF; white-space: nowrap;}
.cc-big {background: #FBF6EE; border-radius: 8px; padding: 20px;
  text-align: center;}
.cc-big-n {font-size: 36px; font-weight: 300; line-height: 1.2;}
.cc-rt {width: 100%; border-collapse: collapse; font-size: 13px;}
.cc-rt td {padding: 4px 6px; vertical-align: middle;
  border-bottom: 1px solid #EADFCF;}
.cc-bar {display: inline-block; height: 12px; vertical-align: middle;
  border-radius: 2px;}
</style>
"""


def _heading(page, question, ctx):
    """The heading block: page label, question, data line."""
    first, last = ctx["date_range"]
    line = dashboard_data.data_line((first, last), ctx["updated"])
    st.markdown(
        f"<div class='cc-page'>{html.escape(page)}</div>"
        f"<div class='cc-q'>{html.escape(question)}</div>"
        f"<div class='cc-data'>{html.escape(line)}</div>",
        unsafe_allow_html=True)


def _caveat(ctx):
    """The client's caveat banner (on every page)."""
    st.info(ctx["caveat"], icon="ℹ️")


def _card_title(text):
    """A card's question title."""
    st.markdown(f"<p class='cc-card-title'>{html.escape(text)}</p>",
                unsafe_allow_html=True)


def _pill(label):
    """A label pill: tint, strong left border, symbol and text."""
    text = html.escape(dashboard_data.label_text(label) or "—")
    return (f"<span class='cc-pill' style='background:"
            f"{dashboard_data.label_tint(label)};border-color:"
            f"{dashboard_data.label_colour(label)}'>{text}</span>")


def _title(question, subtitle, level=2):
    """A question heading with a grey subtitle under it."""
    st.markdown(f"{'#' * level} {question}")
    st.markdown(f"<p class='cc-muted'>{html.escape(subtitle)}</p>",
                unsafe_allow_html=True)


def _card(column, label, value, definition):
    """A bordered KPI card with a one-line definition."""
    with column.container(border=True):
        st.metric(label, value)
        st.caption(definition)


LABEL_CELL = {dashboard_data.label_text(label): label
              for label in dashboard_data.LABEL_STYLE}


def _label_cell(value):
    """Cell style for a label shown as text: tint, border, dark text."""
    label = LABEL_CELL.get(value)
    if label is None:
        return ""
    return (f"background-color: {dashboard_data.label_tint(label)}; "
            f"border-left: 3px solid {dashboard_data.label_colour(label)};"
            f" color: #3B2F2A; font-weight: 600")


def _styled(table, columns):
    """A Styler that colours the given label-text columns."""
    present = [column for column in columns if column in table.columns]
    return table.style.map(_label_cell, subset=present)


def _badge(label):
    """A large label badge: tint, strong left border, symbol and text."""
    text = html.escape(dashboard_data.label_text(label) or "—")
    return (f"<span class='cc-badge' style='background:"
            f"{dashboard_data.label_tint(label)};border-color:"
            f"{dashboard_data.label_colour(label)}'>{text}</span>")


def _footnotes(lines):
    """Small grey footnotes under a page."""
    items = "".join(f"<li>{line}</li>" for line in lines)
    st.markdown(f"<div class='cc-foot'><ul>{items}</ul></div>",
                unsafe_allow_html=True)


def _open_detail(campaign):
    """Drill-through: open the Campaign detail page on a campaign."""
    st.session_state[DETAIL_KEY] = campaign
    st.switch_page(PAGE_OBJECTS["Campaign detail"])


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
    """The ranked action table as HTML.

    The label cell is a pill (tint, left border, symbol and text).
    The Action column takes the spare width and wraps to at most two
    lines; its full text is in an escaped tooltip.
    """
    head = ("<tr><th>#</th><th>Campaign</th><th>Final label</th>"
            "<th>Status</th><th class='n'>Ratio</th>"
            "<th class='n'>Tracked actions</th><th>Trend</th>"
            "<th class='act'>Action</th><th>Label period</th></tr>")
    body = []
    for _, row in table.iterrows():
        action = html.escape(_readable(row["action"], keep=True),
                             quote=True)
        body.append(
            "<tr>"
            f"<td class='n'>{int(row['rank'])}</td>"
            f"<td class='cmp'><b>{html.escape(str(row['campaign']))}</b></td>"
            f"<td>{_pill(row['label'])}</td>"
            f"<td>{html.escape(_readable(row['status_now']))}</td>"
            f"<td class='n'>{_fmt(row['ratio_to_benchmark'], '{:.2f}x')}</td>"
            f"<td class='n'>{_fmt(row['tracked_actions'], '{:,.0f}')}</td>"
            f"<td>{html.escape(_readable(row['recent_trend']))}</td>"
            f"<td class='act'><span class='cc-clamp' title=\"{action}\">"
            f"{action}</span></td>"
            f"<td class='per'>{_period_html(row['label_period'])}</td>"
            "</tr>")
    return (f"<table class='cc-table'><thead>{head}</thead>"
            f"<tbody>{''.join(body)}</tbody></table>")


def _period_html(period):
    """"start to end" on two lines, so dates never break inside."""
    if not period:
        return "—"
    return "<br>".join(f"<span class='nw'>{html.escape(part)}</span>"
                       for part in str(period).split(" to ", 1))


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
           if window else "") + ". Bars use that period's figures.",
        "<b>Filters</b> only hide table rows and bars; they never "
        "change a label, a tile or a KPI card.",
        f"<b>{html.escape(dashboard_data.footnote_text(config))}</b>",
    ]
    return lines


def _tile_line(line, with_label=False):
    """One campaign line in a tile: name, status or label, action."""
    parts = [f"<b>{html.escape(line['campaign'])}</b>"]
    if with_label:
        parts.append(html.escape(
            f"({dashboard_data.label_text(line['label']) or '—'})"))
    elif line["running"]:
        parts.append("<span class='cc-run'>● running</span>")
    elif line["status"]:
        parts.append(html.escape(line["status"]))
    text = " · ".join(parts)
    if line["action"]:
        text += f": {html.escape(line['action'])}"
    return f"<div class='cc-tile-line'>{text}</div>"


def _tiles_html(summary):
    """The four decision tiles: three labels, then Running now."""
    tiles = []
    for tile in summary["tiles"]:
        label = tile["label"]
        lines = "".join(_tile_line(line) for line in tile["lines"])
        if tile["more"]:
            lines += (f"<div class='cc-tile-more'>+{tile['more']} more, "
                      "see the table</div>")
        tiles.append(
            "<div class='cc-tile' style='background:"
            f"{dashboard_data.label_tint(label)};border-left-color:"
            f"{dashboard_data.label_colour(label)}'>"
            "<div class='cc-tile-head'><span class='cc-tile-count'>"
            f"{tile['count']}</span><span class='cc-tile-label'>"
            f"{html.escape(dashboard_data.label_text(label))}</span></div>"
            f"{lines}</div>")
    running = summary["running"]
    lines = "".join(_tile_line(line, with_label=True) for line in running)
    if not running:
        lines = "<div class='cc-tile-more'>No campaign is active.</div>"
    tiles.append(
        "<div class='cc-tile' style='background:#FFFFFF;"
        "border:1px solid #D9CFC0;border-left:5px solid #D9CFC0'>"
        "<div class='cc-tile-head'><span class='cc-tile-count'>"
        f"{len(running)}</span><span class='cc-tile-label'>Running now"
        f"</span></div>{lines}</div>")
    return f"<div class='cc-tiles'>{''.join(tiles)}</div>"


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
    _heading("Act", "Which campaigns should we continue, test or pause?",
             ctx)
    tables = ctx["tables"]
    currency = ctx["currency"]
    recs = ctx["all_recommendations"]

    # Filters: display only, they hide table rows and bars.
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

    # Decision tiles: all campaigns, never filtered.
    st.markdown(_tiles_html(dashboard_data.act_summary(recs)),
                unsafe_allow_html=True)

    kpi = dashboard_data.kpi_values(tables["benchmarks"])
    table = dashboard_data.action_table(view, tables["recent_trend"])
    left, right = st.columns([1.45, 1])
    with left.container(border=True):
        show_hidden = st.checkbox(
            "Also show insufficient data / not judged campaigns",
            value=False, key="act_show_hidden")
        if not show_hidden:
            table = table.loc[table["label"].isin(
                dashboard_data.JUDGED_LABELS)].reset_index(drop=True)
        if table.empty:
            st.info("No campaign matches the filters.")
        else:
            st.markdown(_action_html(table), unsafe_allow_html=True)
            st.caption("Pause or review first, then test, then continue; "
                       "within a label, the highest ratio to the "
                       "benchmark first.")
            picks = st.columns([3, 1, 1], vertical_alignment="bottom")
            campaign = picks[0].selectbox(
                "Campaign", list(table["campaign"]), key="act_pick")
            if picks[1].button("Open detail", type="primary",
                               key="act_open", width="stretch"):
                _open_detail(campaign)
            picks[2].download_button(
                "Download CSV",
                dashboard_data.csv_bytes(table.drop(columns=["label"])),
                file_name="actions.csv", mime="text/csv",
                key="act_download", width="stretch")
    with right.container(border=True):
        _card_title("Ratio to benchmark (cost per tracked action)")
        bars = dashboard_data.ratio_bar_rows(table, recs,
                                             cap=charts.RATIO_CAP)
        if bars.empty:
            st.info("No judged campaign with a ratio matches the "
                    "filters.")
        else:
            lines = dashboard_data.reference_lines(
                ctx["config"], kpi["benchmark"])
            st.plotly_chart(charts.ratio_bar(bars, lines, currency),
                            width="stretch", key="act_ratio")
            st.caption("Same order as the table. Dashed lines: the "
                       "continue and test limits from the config. A bar "
                       "past the edge (▶) has its value written. "
                       "\"worsening\": the label comes from the trend "
                       "override.")

    below = st.columns(3)
    with below[0]:
        not_comparable = dashboard_data.not_comparable_rows(recs)
        with st.expander(f"Not comparable ({len(not_comparable)})"):
            st.caption("Judged against their own history, not the "
                       "benchmark, so they are not in the chart or the "
                       "ranking.")
            for _, row in not_comparable.iterrows():
                st.markdown(
                    f"<b>{html.escape(str(row['campaign']))}</b> · "
                    f"{html.escape(str(row['group']))} · "
                    f"{html.escape(str(row['status_now']))}<br>"
                    f"{html.escape(str(row['reason']))}<br>"
                    f"<i>Action:</i> {html.escape(str(row['action_text']))}",
                    unsafe_allow_html=True)
    with below[1]:
        with st.expander("Totals and benchmark"):
            scope = _totals_scope(ctx, kpi)
            cards = st.columns(2)
            _card(cards[0], "Spend", f"{kpi['spend']:,.0f} {currency}",
                  "Total spend of the campaigns in the totals.")
            _card(cards[1], "Tracked actions",
                  f"{kpi['tracked_actions']:,.0f}",
                  "Directions requests and calls the account counts.")
            cards = st.columns(2)
            _card(cards[0], "Cost per tracked action",
                  f"{kpi['cost_per_tracked_action']:,.2f} {currency}",
                  "Spend divided by tracked actions.")
            bench_note = (f"Leave-one-out range {kpi['loo_min']:,.2f} to "
                          f"{kpi['loo_max']:,.2f}." if kpi["leave_one_out"]
                          else "Pooled over the benchmark group(s).")
            _card(cards[1], "Benchmark",
                  f"{kpi['benchmark']:,.2f} {currency}",
                  f"What a campaign is compared with. {bench_note}")
            st.caption(f"{scope} Totals use the whole daily range "
                       f"(benchmarks.csv); the filters do not change "
                       f"them.")
    with below[2]:
        with st.expander("How to read this"):
            _footnotes(_act_definitions(ctx, kpi))


# --- Context ------------------------------------------------------

BENCHMARK_NAMES = {
    "benchmark": "Benchmark (pooled, the one used)",
    "with_not_comparable": "Including not-comparable groups",
    "judged_campaigns": "Judged campaigns (KPI cards)",
}


def _takeaway(text):
    """The one-sentence takeaway under a card's question."""
    st.markdown(f"<p class='cc-take'>{html.escape(text)}</p>",
                unsafe_allow_html=True)


def _money(value, currency):
    return _fmt(value, "{:,.2f}") + (f" {currency}"
                                     if value is not None
                                     and not pd.isna(value) else "")


def _recent_html(rows, currency):
    """Prior vs recent window per active campaign, as small bars.

    Bar lengths are relative to the largest value shown. A rise
    (recent / prior above 1) gets a warning tag with the trend as
    named in the data; label colours are never used here.
    """
    values = pd.concat([rows["prior_cost_per_tracked_action"],
                        rows["recent_cost_per_tracked_action"]])
    top = float(values.max()) if values.notna().any() else 0.0
    out = []
    for _, row in rows.iterrows():
        def bar(value, colour):
            if top <= 0 or value is None or pd.isna(value):
                return ""
            width = max(2.0, 100.0 * float(value) / top)
            return (f"<span class='cc-bar' style='width:{width:.0f}px;"
                    f"background:{colour}'></span>")
        ratio = row["recent_vs_prior_ratio"]
        trend = _readable(row["recent_trend"])
        if ratio is not None and not pd.isna(ratio) and ratio > 1:
            flag = f"<span class='cc-tag'>⚠ {html.escape(trend)}</span>"
        else:
            flag = f"<span class='cc-muted'>{html.escape(trend)}</span>"
        out.append(
            "<tr>"
            f"<td rowspan='2' style='width:30%'><b>"
            f"{html.escape(str(row['campaign']))}</b></td>"
            f"<td>Prior window<br><span class='cc-muted'>"
            f"{html.escape(str(row['prior_window'] or '—'))}</span></td>"
            f"<td class='nw'>{bar(row['prior_cost_per_tracked_action'], charts.NEUTRAL_LIGHT)} "
            f"{html.escape(_money(row['prior_cost_per_tracked_action'], currency))}</td>"
            f"<td rowspan='2' class='nw' style='text-align:right'>"
            f"<span class='cc-muted'>Recent / prior</span><br>"
            f"<span style='font-size:22px;font-weight:600'>"
            f"{_fmt(ratio, '{:.2f}x')}</span><br>{flag}</td></tr>"
            "<tr>"
            f"<td>Recent window<br><span class='cc-muted'>"
            f"{html.escape(str(row['recent_window'] or '—'))}</span></td>"
            f"<td class='nw'>{bar(row['recent_cost_per_tracked_action'], charts.NEUTRAL)} "
            f"{html.escape(_money(row['recent_cost_per_tracked_action'], currency))}</td>"
            "</tr>")
    return f"<table class='cc-rt'>{''.join(out)}</table>"


def _trend_campaign(ctx):
    """The campaign for the monthly trend: first active, or chosen."""
    tables = ctx["tables"]
    campaigns = sorted(set(tables["timeline_by_campaign"]["campaign"]))
    if not campaigns:
        return None
    rows = dashboard_data.recent_trend_rows(
        tables["recent_trend"], ctx["all_recommendations"])
    active = [name for name in rows["campaign"] if name in campaigns]
    default = active[0] if active else campaigns[0]
    return st.selectbox("Campaign for the monthly trend", campaigns,
                        index=campaigns.index(default),
                        key="ctx_trend_campaign")


def _card_recent(ctx):
    """(a) Has performance changed recently?"""
    tables = ctx["tables"]
    currency = ctx["currency"]
    _card_title("Has performance changed recently?")
    rows = dashboard_data.recent_trend_rows(
        tables["recent_trend"], ctx["all_recommendations"])
    _takeaway(dashboard_data.trend_takeaway(rows))
    if not rows.empty:
        shown, more = dashboard_data.recent_rows_capped(rows, 5)
        st.markdown(_recent_html(shown, currency), unsafe_allow_html=True)
        if more:
            st.caption(f"+{more} more, see the recent trend table.")
    campaign = _trend_campaign(ctx)
    if campaign is not None:
        table = dashboard_data.trend_with_flags(
            tables["timeline_by_campaign"], campaign)
        st.plotly_chart(charts.trend_line(table, "month", "Month",
                                          currency, height=280),
                        width="stretch", key="ctx_trend_chart")
        st.caption("Monthly cost per tracked action. Hollow ring = "
                   "partial month (the campaign ran only part of it) or "
                   "lagged month (days still being reported). Do not "
                   "read a jump in those months as a change.")
    if not rows.empty:
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
    return campaign


def _weekday_parts(ctx):
    """(pooled weekday table or None, what-if rows, what-if range)."""
    tables = ctx["tables"]
    try:
        pooled = dashboard_data.weekday_core_table(tables["weekday_core"])
    except ValueError as exc:
        st.error(str(exc))
        pooled = None
    rows, span = dashboard_data.what_if_parts(
        tables["what_if_weekday_shift"])
    return pooled, rows, span


def _card_weekday(ctx, pooled):
    """(b) Do weekdays differ?"""
    currency = ctx["currency"]
    _card_title("Do weekdays differ?")
    if pooled is None:
        return
    _takeaway(dashboard_data.weekday_takeaway(pooled, currency))
    busiest = dashboard_data.most_clicks_weekday(pooled)
    st.plotly_chart(charts.weekday_bar(pooled, currency,
                                       highlight=busiest,
                                       note="most pooled clicks"),
                    width="stretch", key="ctx_weekday_chart")
    if busiest is not None:
        st.caption(f"Outlined: {busiest}, the weekday with the most "
                   "pooled clicks. Pooled over the time groups in the "
                   "config.")
    with st.expander("Pooled weekday table"):
        _table(dashboard_data.display_table(pooled), "weekday_pooled.csv",
               key="ctx_weekday_pooled")


def _card_what_if(ctx, rows, span):
    """(c) What would moving spend do?"""
    currency = ctx["currency"]
    _card_title("What would moving spend do?")

    def first(column):
        if column in rows.columns and not rows.empty:
            return rows[column].iloc[0]
        return None

    change = span["display"] if span is not None else first("display")
    scenario = (span or {}).get("scenario") or first("scenario")
    note = (span or {}).get("note") or first("note")
    if change is None or (not isinstance(change, str) and pd.isna(change)):
        st.info("No what-if rows for this client.")
        return
    change = str(change)
    head, _, tail = change.partition(" (")
    sub = f"({tail}" if tail else ""
    st.markdown(
        "<div class='cc-big'><div class='cc-big-n'>"
        f"{html.escape(head)}</div>"
        + (f"<div style='font-size:20px'>{html.escape(sub)}</div>"
           if sub else "") + "</div>", unsafe_allow_html=True)
    if scenario and not pd.isna(scenario):
        st.markdown(f"<p class='cc-take' style='margin-top:12px'>"
                    f"{html.escape(str(scenario))}.</p>",
                    unsafe_allow_html=True)
    if note and not pd.isna(note):
        st.markdown(f"<p class='cc-take'>⚠️ {html.escape(str(note))}.</p>",
                    unsafe_allow_html=True)
    with st.expander("What-if by variant"):
        _what_if(rows, None, currency)


def _card_journey(ctx):
    """(d) How do people reach the restaurant?"""
    tables = ctx["tables"]
    _card_title("How do people reach the restaurant?")
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


def _completeness(ctx, campaign):
    """Data completeness: lag check and the monthly trend table."""
    tables = ctx["tables"]
    config = ctx["config"]
    configured = (config.get("analysis", {}).get("recent_trend", {})
                  .get("conversion_lag_days"))
    lag_check = ctx["optional"]["lag_check"]
    if lag_check is None:
        st.info("The lag check is not turned on for this client "
                "(recent_trend.lag_check_days in its config).")
    else:
        summary = dashboard_data.lag_check_summary(lag_check)
        _takeaway(dashboard_data.lag_takeaway(summary, configured))
        st.markdown("**Lag check by lag**")
        st.caption("Tracked actions can arrive days late. The lag check "
                   "reruns the recent signals with other lags and counts "
                   "what changes.")
        _table(summary, "lag_check_summary.csv", key="ctx_lag",
               column_config={
                   "lag": NUM("Lag (days)", format="%d"),
                   "trend_changes": NUM("Trend changes", format="%d"),
                   "label_changes": NUM("Label changes", format="%d")})
        st.markdown("**All lag-check counts**")
        _table(lag_check, "lag_check.csv", key="ctx_lag_all")
    if campaign is not None:
        st.markdown(f"**Monthly trend: {campaign}**")
        st.caption("month note: partial (the campaign ran only part of "
                   "the month) or lagged (days still being reported).")
        table = dashboard_data.trend_with_flags(
            tables["timeline_by_campaign"], campaign)
        _table(dashboard_data.display_table(table),
               f"monthly_{campaign}.csv", key="ctx_month_table",
               column_config={"month note": WIDE("Month note")})


def _distorting(ctx):
    """Is one campaign distorting a weekday? (inside an expander)."""
    optional = ctx["optional"]
    mix = optional["weekday_mix_by_campaign"]
    loo = optional["weekday_leave_one_out"]
    top = optional["weekday_top_days"]
    focus = (top["weekday"].iloc[0]
             if top is not None and not top.empty else None)
    full = {day[:3]: day for day in dashboard_data.WEEKDAYS}
    label = full.get(focus, focus) if focus else "one weekday"
    with st.expander(f"Is one campaign distorting {label}?"):
        if mix is None or loo is None:
            st.info("The weekday decomposition is not turned on for "
                    "this client (analysis.weekday_decomposition in its "
                    "config).")
        else:
            _weekday_breakdown(mix, loo, top, focus)


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
    """Can we trust these labels, and when should we run campaigns?

    A 2x2 grid of cards, each a question, a takeaway and a chart;
    then data completeness, the weekday breakdown and the method.
    """
    _heading("Context", "Can we trust these labels, and when should we "
             "run campaigns?", ctx)
    pooled, rows, span = _weekday_parts(ctx)
    top = st.columns(2)
    with top[0].container(border=True):
        campaign = _card_recent(ctx)
    with top[1].container(border=True):
        _card_weekday(ctx, pooled)
    bottom = st.columns(2)
    with bottom[0].container(border=True):
        _card_what_if(ctx, rows, span)
    with bottom[1].container(border=True):
        _card_journey(ctx)
    below = st.columns(2)
    with below[0]:
        with st.expander("Data completeness (lag check, monthly trend)"):
            _completeness(ctx, campaign)
    with below[1]:
        _distorting(ctx)
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
    _heading("Campaign detail", "How has this campaign performed?", ctx)
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


PAGE_TITLES = ("Act", "Context", "Campaign detail")
PAGE_OBJECTS = {}
_CTX = {}


def act():
    """Act page (st.navigation entry)."""
    _page_act(_CTX)
    _caveat(_CTX)


def context():
    """Context page (st.navigation entry)."""
    _page_context(_CTX)
    _caveat(_CTX)


def campaign_detail():
    """Campaign detail page (st.navigation entry)."""
    _page_detail(_CTX)
    _caveat(_CTX)


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


LOGO_TYPES = {".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
              ".webp": "image/webp"}


def _logo_img(path):
    """The logo as an inline <img> (read locally, never uploaded)."""
    kind = LOGO_TYPES.get(path.suffix.lower(), "image/png")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (f"<img class='cc-logo' alt='Logo' "
            f"src='data:{kind};base64,{data}'>")


def _header(clients):
    """White header: optional logo, divider, wordmark, client picker.

    The logo comes from branding.logo_path in the client config; when
    the key or the file is missing, only the wordmark shows.
    """
    with st.container(key="cc_header"):
        brand, picker = st.columns([6, 1], vertical_alignment="center")
        client = picker.selectbox("Client", clients, index=0,
                                  key="client",
                                  label_visibility="collapsed")
        try:
            config = dashboard_data.load_config(
                dashboard_data.client_config_path(client))
        except FileNotFoundError:
            config = {}
        logo = dashboard_data.logo_path(config)
        wordmark = "<span class='cc-wordmark'>CampaignCompass</span>"
        if logo is not None:
            brand.markdown(
                f"<div class='cc-brand'>{_logo_img(logo)}"
                f"<span class='cc-divider'></span>{wordmark}</div>",
                unsafe_allow_html=True)
        else:
            brand.markdown(f"<div class='cc-brand'>{wordmark}</div>",
                           unsafe_allow_html=True)
    return client


def main():
    """Top navigation, header and client, load the tables, run a page."""
    st.set_page_config(page_title="CampaignCompass", layout="wide",
                       initial_sidebar_state="collapsed")
    st.markdown(STYLE, unsafe_allow_html=True)
    pages = [st.Page(act, title="Act", default=True),
             st.Page(context, title="Context"),
             st.Page(campaign_detail, title="Campaign detail")]
    PAGE_OBJECTS.update(zip(PAGE_TITLES, pages))
    page = st.navigation(pages, position="top")
    client = _header(dashboard_data.list_clients())
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
    _CTX.clear()
    _CTX.update(ctx)
    page.run()


if __name__ == "__main__":
    main()
