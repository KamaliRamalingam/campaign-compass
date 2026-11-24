"""Tests for the PR 5 dashboard data functions (dashboard/data.py):
the three-page report (Act, Context, Campaign detail).

All data is tiny and made up. No real data, no real campaign
names. Only dashboard/data.py is imported, never app.py or
charts.py, so no test needs streamlit or plotly.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import data as dd  # noqa: E402

NAN = float("nan")


def _recs():
    """Final labels with label-period figures (made up)."""
    rows = [
        # campaign, group, label, status, ratio, spend, actions, cost,
        # benchmark
        ("Alpha", "core", "test", "active", 1.5, 300.0, 20.0, 15.0, 10.0),
        ("Beta", "core", "continue", "ended", 0.8, 160.0, 20.0, 8.0, 10.0),
        ("Gamma", "sep", "pause_or_review", "ended", 2.5, 250.0, 10.0,
         25.0, 10.0),
        ("Delta", "sep", "test", "ended", 1.9, 190.0, 10.0, 19.0, 10.0),
        ("Eps", "core", "insufficient_data", "ended", NAN, NAN, NAN, NAN,
         NAN),
        ("Zeta", "other", "not_judged", "ended", NAN, NAN, NAN, NAN, NAN),
        ("Pmax", "core_pmax", "not_comparable", "active", NAN, NAN, NAN,
         NAN, NAN),
    ]
    return pd.DataFrame([{
        "campaign": c, "group": g, "label": label, "status_now": s,
        "label_ratio": ratio, "label_spend": spend,
        "label_tracked_actions": actions,
        "label_cost_per_tracked_action": cost, "label_benchmark": bench,
        "label_basis": "latest_run", "label_period_start": "2026-01-01",
        "label_period_end": "2026-03-31", "recent_trend": "not_active",
        "action_text": f"{label} action"}
        for c, g, label, s, ratio, spend, actions, cost, bench in rows])


def test_every_label_has_text_and_a_distinct_judged_colour():
    for label, style in dd.LABEL_STYLE.items():
        assert style["text"] and style["symbol"] and style["colour"]
    colours = {dd.LABEL_STYLE[label]["colour"]
               for label in dd.JUDGED_LABELS}
    assert len(colours) == 3
    assert dd.label_text("continue") == "✓ Continue"
    assert dd.label_text("something_new") == "something_new"


def test_judged_label_counts_leave_out_unjudged():
    judged, others = dd.judged_label_counts(_recs())
    assert list(judged["label"]) == ["continue", "test",
                                     "pause_or_review"]
    assert list(judged["campaigns"]) == [1, 2, 1]
    assert judged["campaigns"].sum() == 4
    assert others == {"insufficient_data": 1, "not_judged": 1,
                      "not_comparable": 1}


def test_judged_label_counts_keep_zero_rows():
    recs = _recs().loc[lambda r: r["label"] != "continue"]
    judged, _ = dd.judged_label_counts(recs)
    assert judged.set_index("label").loc["continue", "campaigns"] == 0


def test_status_options():
    assert dd.status_options(_recs()) == ["All", "active", "ended"]


def test_filter_view_is_display_only():
    recs = _recs()
    before = recs.copy()
    assert len(dd.filter_view(recs)) == 7
    assert set(dd.filter_view(recs, group="sep")["campaign"]) == {
        "Gamma", "Delta"}
    assert set(dd.filter_view(recs, status="active")["campaign"]) == {
        "Alpha", "Pmax"}
    shown = dd.filter_view(recs, min_tracked_actions=15)
    assert set(shown["campaign"]) == {"Alpha", "Beta"}
    # Labels and the input table are unchanged.
    assert list(shown["label"]) == ["test", "continue"]
    pd.testing.assert_frame_equal(recs, before)


def test_bubble_rows_only_judged_with_figures():
    rows = dd.bubble_rows(_recs())
    assert list(rows["campaign"]) == ["Alpha", "Beta", "Delta", "Gamma"]
    assert set(rows["label"]) <= set(dd.JUDGED_LABELS)
    alpha = rows.set_index("campaign").loc["Alpha"]
    assert alpha["label_text"] == "◆ Test"
    assert alpha["label_period"] == "2026-01-01 to 2026-03-31"


def test_bubble_rows_without_figure_columns_is_empty():
    recs = _recs().drop(columns=["label_spend"])
    assert dd.bubble_rows(recs).empty


def test_reference_lines_from_config():
    config = {"analysis": {"recommendation_rules": {
        "continue_max_ratio": 1.0, "test_max_ratio": 2.0}}}
    lines = dd.reference_lines(config, 12.5)
    assert lines[0] == ("Benchmark", 1.0, 12.5)
    assert [line[1] for line in lines[1:]] == [1.0, 2.0]
    assert lines[2][2] == pytest.approx(25.0)
    assert lines[2][0] == "Test up to 2.0x"
    assert dd.reference_lines({}, 5.0) == [("Benchmark", 1.0, 5.0)]


def test_action_table_is_ranked_most_urgent_first():
    table = dd.action_table(_recs())
    assert list(table["campaign"]) == [
        "Gamma", "Delta", "Alpha", "Beta", "Eps", "Zeta"]
    assert list(table["rank"]) == list(range(1, 7))
    assert "Pmax" not in set(table["campaign"])
    assert table.loc[0, "final_label"] == "✕ Pause or review"
    assert table.loc[0, "ratio_to_benchmark"] == 2.5


def test_action_table_adds_trend_window():
    trend = pd.DataFrame([{"campaign": "Alpha",
                           "recent_window_start": "2026-03-01",
                           "recent_window_end": "2026-03-28"}])
    table = dd.action_table(_recs(), trend).set_index("campaign")
    assert table.loc["Alpha", "trend_window"] == \
        "2026-03-01 to 2026-03-28"
    assert table.loc["Beta", "trend_window"] == ""


def test_trend_with_flags_marks_partial_and_lagged_months():
    timeline = pd.DataFrame([
        {"campaign": "Alpha", "month": month, "source": "day",
         "active_days": 10, "spend": 100.0, "conversions": 10.0,
         "cost_per_conversion": 10.0, "is_partial": partial,
         "is_lagged": lagged}
        for month, partial, lagged in (
            ("2026-01", True, False), ("2026-02", False, False),
            ("2026-03", True, True))])
    table = dd.trend_with_flags(timeline, "Alpha")
    assert list(table["month_note"]) == ["partial", "", "partial, lagged"]
    assert "is_partial" not in table.columns


def test_trend_with_flags_without_flag_columns():
    timeline = pd.DataFrame([{
        "campaign": "Alpha", "month": "2026-01", "source": "month",
        "active_days": 31, "spend": 1.0, "conversions": 1.0,
        "cost_per_conversion": 1.0}])
    assert list(dd.trend_with_flags(timeline, "Alpha")["month_note"]) \
        == [""]


def test_recent_trend_rows():
    trend = pd.DataFrame([{
        "campaign": "Alpha", "recent_trend": "worsening",
        "recent_window_start": "2026-03-01",
        "recent_window_end": "2026-03-28",
        "prior_window_start": "2026-02-01",
        "prior_window_end": "2026-02-28",
        "recent_cost_per_tracked_action": 15.0,
        "prior_cost_per_tracked_action": 10.0,
        "recent_vs_prior_ratio": 1.5, "recent_tracked_actions": 20}])
    rows = dd.recent_trend_rows(trend, _recs())
    assert rows.loc[0, "final_label"] == "◆ Test"
    assert rows.loc[0, "prior_window"] == "2026-02-01 to 2026-02-28"
    assert dd.recent_trend_rows(None, _recs()).empty


def test_journey_intent_long():
    journey = pd.DataFrame([
        {"campaign": "Alpha", "directions_share": 0.6,
         "calls_share": 0.3, "store_visits_share": 0.1},
        {"campaign": "core group", "directions_share": 0.5,
         "calls_share": 0.5, "store_visits_share": 0.0},
    ])
    long = dd.journey_intent_long(journey)
    assert set(long["campaign"]) == {"Alpha"}
    assert set(long["intent"]) == {"Directions", "Calls", "Store visits"}
    assert long["share"].sum() == pytest.approx(1.0)


def test_footnote_text_from_config_or_default():
    assert dd.footnote_text({"analysis": {"footnote_text": "x"}}) == "x"
    assert dd.footnote_text({}) == dd.DEFAULT_FOOTNOTE


# --- Redesign: theme, header helpers --------------------------------

def test_label_colours_match_the_redesign_palette():
    assert dd.label_colour("pause_or_review") == "#C8452D"
    assert dd.label_colour("test") == "#D9961A"
    assert dd.label_colour("continue") == "#2E9E5B"
    for label in ("not_comparable", "insufficient_data", "not_judged"):
        assert dd.label_colour(label) == "#8C8C8C"
    assert dd.label_tint("pause_or_review") == "#FBE3DD"
    assert dd.label_tint("test") == "#FFF0CC"
    assert dd.label_tint("continue") == "#DDF0E2"
    assert dd.label_tint("something_new") == dd.GREY_TINT


def test_data_line_format():
    from datetime import date, datetime
    line = dd.data_line((date(2024, 7, 1), date(2026, 11, 12)),
                        datetime(2026, 11, 24, 10, 48, 31))
    assert line == "Data 1 Jul 2024 – 12 Nov 2026 · Updated 24 Nov 2026 10:48"


def test_logo_path_missing_key_missing_file_and_file(tmp_path):
    assert dd.logo_path({}) is None
    assert dd.logo_path({"branding": {}}) is None
    assert dd.logo_path({"branding": {"logo_path": "nope.png"}},
                        repo_root=tmp_path) is None
    (tmp_path / "local").mkdir()
    logo = tmp_path / "local" / "logo.png"
    logo.write_bytes(b"png")
    assert dd.logo_path({"branding": {"logo_path": "local/logo.png"}},
                        repo_root=tmp_path) == logo


def test_ratio_bar_rows_keep_table_order_cap_and_worsening():
    recs = _recs()
    recs["trend_override"] = [
        "continue -> test", None, None, None, None, None, None]
    recs.loc[recs["campaign"] == "Gamma", "label_ratio"] = 25.4
    table = dd.action_table(recs)
    rows = dd.ratio_bar_rows(table, recs, cap=2.5)
    judged = table.loc[table["label"].isin(dd.JUDGED_LABELS)]
    assert list(rows["campaign"]) == list(judged["campaign"])
    gamma = rows.set_index("campaign").loc["Gamma"]
    assert gamma["over"] and gamma["shown"] == 2.5
    assert gamma["ratio"] == 25.4
    assert rows.set_index("campaign").loc["Alpha", "worsening"]
    assert not rows.set_index("campaign").loc["Beta", "worsening"]
    assert not rows.set_index("campaign").loc["Beta", "over"]


def test_ratio_bar_rows_without_override_column_or_rows():
    rows = dd.ratio_bar_rows(dd.action_table(_recs()), _recs())
    assert not rows["worsening"].any()
    empty = dd.ratio_bar_rows(dd.action_table(_recs().iloc[4:]),
                              _recs())
    assert empty.empty


def test_recent_rows_capped_and_most_clicks_weekday():
    rows = pd.DataFrame({"campaign": list("ABCDEFG")})
    shown, more = dd.recent_rows_capped(rows, 5)
    assert list(shown["campaign"]) == list("ABCDE") and more == 2
    shown, more = dd.recent_rows_capped(rows.head(3), 5)
    assert len(shown) == 3 and more == 0
    empty, more = dd.recent_rows_capped(rows.iloc[0:0], 5)
    assert empty.empty and more == 0
    assert dd.most_clicks_weekday(pd.DataFrame(
        {"weekday": ["Mon"], "tracked_actions": [1]})) is None
