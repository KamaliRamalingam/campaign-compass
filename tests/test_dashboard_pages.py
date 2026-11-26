"""Tests for the PR 4 dashboard data functions (dashboard/data.py).

All data is tiny and made up. No real data, no real campaign
names. Only dashboard/data.py is imported, never app.py, so no
test needs streamlit.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import data as dd  # noqa: E402


def _recs():
    """Final labels (after the trend override)."""
    rows = [
        ("Alpha", "core", "test", "active", "worsening",
         "keep running, but test changes", "recent_window",
         "2026-08-12", "2026-11-09", "alpha reason"),
        ("Beta", "core", "continue", "ended", "not_active",
         "worked well when it ran; candidate to restart",
         "latest_run", "2025-01-01", "2025-06-30", "beta reason"),
        ("Gamma", "core", "insufficient_data", "ended", "not_active",
         "not enough data to judge", "latest_run", None, None,
         "gamma reason"),
        ("Delta", "other", "not_judged", "ended", "not_judged",
         "not evaluated: group not judged", "fixed", None, None,
         "group other not evaluated"),
        ("Pmax", "core_pmax", "not_comparable", "active", "stable",
         "judge against its own history, not the benchmark", "fixed",
         "2025-01-01", "2026-11-12", "pmax reason"),
    ]
    return pd.DataFrame([{
        "campaign": c, "group": g, "label": label, "status_now": s,
        "recent_trend": trend, "action_text": action,
        "label_basis": basis, "label_period_start": start,
        "label_period_end": end, "reason": reason,
        "trend_reason": "trend text"}
        for c, g, label, s, trend, action, basis, start, end, reason
        in rows])


def _recent_trend():
    return pd.DataFrame([
        {"campaign": "Alpha", "recent_window_start": "2026-10-13",
         "recent_window_end": "2026-11-09",
         "prior_window_start": "2026-09-15",
         "prior_window_end": "2026-10-12"},
        {"campaign": "Pmax", "recent_window_start": "2026-10-13",
         "recent_window_end": "2026-11-09",
         "prior_window_start": "2026-09-15",
         "prior_window_end": "2026-10-12"},
    ])


def test_final_label_counts():
    counts = dd.final_label_counts(_recs()).set_index("label")
    assert counts.loc["test", "campaigns"] == 1
    assert counts["campaigns"].sum() == 5


def test_summary_rows_hide_and_show():
    rows = dd.summary_rows(_recs(), _recent_trend())
    # not_comparable never; not_judged / insufficient hidden.
    assert list(rows["campaign"]) == ["Alpha", "Beta"]
    alpha = rows.set_index("campaign").loc["Alpha"]
    assert alpha["label"] == "test"
    assert alpha["label_period"] == "2026-08-12 to 2026-11-09"
    assert alpha["trend_period"] == "2026-10-13 to 2026-11-09"
    assert rows.set_index("campaign").loc["Beta", "trend_period"] == ""
    shown = dd.summary_rows(_recs(), _recent_trend(), show_hidden=True)
    assert set(shown["campaign"]) == {"Alpha", "Beta", "Gamma", "Delta"}
    assert "Pmax" not in set(shown["campaign"])


def test_summary_rows_group_filter():
    rows = dd.summary_rows(_recs(), _recent_trend(), show_hidden=True,
                           group="other")
    assert list(rows["campaign"]) == ["Delta"]
    assert dd.campaigns_in_group(_recs(), "core") == [
        "Alpha", "Beta", "Gamma"]
    assert dd.campaigns_in_group(_recs(), dd.ALL_GROUPS)[0] == "Alpha"
    assert dd.group_options(_recs())[0] == dd.ALL_GROUPS


def test_kpi_values_read_from_benchmarks():
    benchmarks = pd.DataFrame([
        {"variant": "benchmark", "groups": "core", "leave_one_out": True,
         "campaigns": 5, "spend": 400.0, "tracked_actions": 80.0,
         "cost_per_tracked_action": 5.0, "loo_min": 4.0,
         "loo_max": 6.0},
        {"variant": "judged_campaigns", "groups": "core+sep",
         "leave_one_out": None, "campaigns": 11, "spend": 500.0,
         "tracked_actions": 90.0, "cost_per_tracked_action": 500 / 90,
         "loo_min": None, "loo_max": None},
    ])
    kpi = dd.kpi_values(benchmarks)
    assert kpi["judged_campaigns"] == 11
    assert kpi["judged_groups"] == "core+sep"
    assert kpi["spend"] == 500.0
    assert kpi["cost_per_tracked_action"] == pytest.approx(500 / 90)
    assert kpi["benchmark"] == 5.0
    assert (kpi["loo_min"], kpi["loo_max"]) == (4.0, 6.0)
    benchmarks.loc[0, "leave_one_out"] = False
    assert dd.kpi_values(benchmarks)["loo_min"] is None


def test_too_little_data_count_only_in_kpi_groups():
    recs = pd.DataFrame([
        {"campaign": "A", "group": "core", "label": "continue"},
        {"campaign": "B", "group": "core", "label": "insufficient_data"},
        {"campaign": "C", "group": "sep", "label": "insufficient_data"},
        {"campaign": "D", "group": "other", "label": "insufficient_data"},
    ])
    assert dd.too_little_data_count(recs, "core+sep") == 2
    assert dd.too_little_data_count(recs, "core") == 1
    assert dd.too_little_data_count(recs, ["core", "sep"]) == 2


def test_scope_groups_from_config_with_fallbacks():
    config = {"analysis": {"recommendation_rules": {
        "judged_groups": ["core", "sep"],
        "benchmark": {"groups": ["core"]}}}}
    assert dd.scope_groups(config) == (["core", "sep"], ["core"])
    benchmarks = pd.DataFrame([{"variant": "judged_campaigns",
                                "groups": "core+late"}])
    assert dd.scope_groups({}, benchmarks) == (["core", "late"], ["core"])
    assert dd.scope_groups({}) == ([], ["core"])


def _recs_with_ended_pauses():
    """_recs plus two ended pause_or_review campaigns."""
    recs = _recs()
    extra = recs.iloc[[1, 1]].copy()
    extra["campaign"] = ["Epsilon", "Zeta"]
    extra["label"] = "pause_or_review"
    extra["action_text"] = "do not restart without changes"
    recs = pd.concat([recs, extra], ignore_index=True)
    recs["label_ratio"] = [1.5, 0.8, None, None, None, 3.0, 9.0]
    return recs


def test_act_summary_tile_counts_in_label_order():
    summary = dd.act_summary(_recs_with_ended_pauses())
    assert [(tile["label"], tile["count"]) for tile in summary["tiles"]] \
        == [("pause_or_review", 2), ("test", 1), ("continue", 1)]
    # Ranked order inside a tile: highest ratio first.
    pause = summary["tiles"][0]
    assert [line["campaign"] for line in pause["lines"]] == [
        "Zeta", "Epsilon"]
    assert pause["more"] == 0


def test_act_summary_caps_three_names_then_more():
    recs = _recs()
    extra = recs.iloc[[1] * 5].copy()
    extra["campaign"] = ["E1", "E2", "E3", "E4", "E5"]
    recs = pd.concat([recs, extra], ignore_index=True)
    recs["label_ratio"] = [1.5, 0.1, None, None, None,
                           0.9, 0.8, 0.7, 0.6, 0.5]
    tile = dd.act_summary(recs)["tiles"][2]
    assert tile["label"] == "continue"
    assert tile["count"] == 6
    assert [line["campaign"] for line in tile["lines"]] == [
        "E1", "E2", "E3"]
    assert tile["more"] == 3


def test_act_summary_running_marker_and_first_clause():
    summary = dd.act_summary(_recs_with_ended_pauses())
    test_line = summary["tiles"][1]["lines"][0]
    assert test_line == {"campaign": "Alpha", "label": "test",
                         "status": "active", "running": True,
                         "action": "keep running, but test changes"}
    continue_line = summary["tiles"][2]["lines"][0]
    # Cut at the semicolon, never reworded.
    assert continue_line["action"] == "worked well when it ran"
    assert continue_line["running"] is False
    assert continue_line["status"] == "ended"
    # Running now: every active campaign, not_comparable last.
    assert [(line["campaign"], line["label"])
            for line in summary["running"]] == [
        ("Alpha", "test"), ("Pmax", "not_comparable")]


def test_tile_title_has_count_in_brackets():
    assert dd.tile_title("Pause or review", 1) == "Pause or review (1)"
    assert dd.tile_title("Running now", 0) == "Running now (0)"


def test_tile_detail_status_then_advice_capitalised():
    summary = dd.act_summary(_recs_with_ended_pauses())
    pause_line = summary["tiles"][0]["lines"][0]
    assert dd.tile_detail(pause_line) == (
        "Ended · Do not restart without changes")
    test_line = summary["tiles"][1]["lines"][0]
    assert dd.tile_detail(test_line) == (
        "Running · Keep running, but test changes")
    # Running now: the label first, then the advice.
    running = summary["running"][0]
    assert dd.tile_detail(running, with_label=True) == (
        "Test · Keep running, but test changes")


def test_tile_detail_only_first_letter_changes():
    line = {"campaign": "A", "label": "test", "status": "ended",
            "running": False, "action": "restart only with changes"}
    assert dd.tile_detail(line) == "Ended · Restart only with changes"
    line["action"] = ""
    assert dd.tile_detail(line) == "Ended"
    line["label"] = None
    assert dd.tile_detail(line, with_label=True) == "—"
    assert dd.capitalise_first("keep running, But") == "Keep running, But"


def test_act_summary_no_active_campaigns():
    recs = _recs()
    recs["status_now"] = "ended"
    summary = dd.act_summary(recs)
    assert summary["running"] == []
    assert all(not line["running"] for tile in summary["tiles"]
               for line in tile["lines"])


def test_act_summary_empty_label_is_in_no_tile():
    recs = _recs()
    recs.loc[recs["campaign"] == "Alpha", "label"] = None
    summary = dd.act_summary(recs)
    assert summary["tiles"][1]["count"] == 0
    names = [line["campaign"] for tile in summary["tiles"]
             for line in tile["lines"]]
    assert "Alpha" not in names
    # Still active, so still listed under Running now, label empty.
    assert summary["running"][0]["campaign"] == "Alpha"
    assert summary["running"][0]["label"] is None


def test_first_clause():
    assert dd.first_clause("a, b; c") == "a, b"
    assert dd.first_clause("First part. Second part.") == "First part"
    assert dd.first_clause("no cut here") == "no cut here"
    assert dd.first_clause("restart only with changes; best run was run "
                           "2 (2025-06-06 to 2025-10-04)") == \
        "restart only with changes"
    assert dd.first_clause(None) == ""
    assert dd.first_clause(float("nan")) == ""


def test_campaign_detail_has_both_periods():
    detail = dd.campaign_detail(_recs(), _recent_trend(), "Alpha")
    assert detail["label"] == "test"
    assert detail["label_period"] == "2026-08-12 to 2026-11-09"
    assert detail["trend_window"] == "2026-10-13 to 2026-11-09"
    assert detail["prior_window"] == "2026-09-15 to 2026-10-12"
    ended = dd.campaign_detail(_recs(), _recent_trend(), "Gamma")
    assert ended["label_period"] == "" and ended["trend_window"] == ""


def test_run_recommendations_for_campaign():
    runs = pd.DataFrame([
        {"campaign": "Alpha", "run_number": 2, "start": "b", "end": "c",
         "label": "test", "ratio_to_benchmark": 1.2},
        {"campaign": "Alpha", "run_number": 1, "start": "a", "end": "b",
         "label": "continue", "ratio_to_benchmark": 0.8},
        {"campaign": "Beta", "run_number": 1, "start": "a", "end": "b",
         "label": "continue", "ratio_to_benchmark": 0.5},
    ])
    table = dd.run_recommendations_for_campaign(runs, "Alpha")
    assert list(table["run_number"]) == [1, 2]
    assert list(table["run_label"]) == ["continue", "test"]


def test_filter_period_months_and_dates():
    monthly = pd.DataFrame({"month": ["2025-12", "2026-01", "2026-02"]})
    assert list(dd.filter_period(monthly, "month", "2026-01")["month"]) \
        == ["2026-01", "2026-02"]
    weekly = pd.DataFrame({"week_start": ["2026-01-05", "2026-01-12",
                                          "2026-01-19"]})
    kept = dd.filter_period(weekly, "week_start", "2026-01-06",
                            "2026-01-19")
    assert list(kept["week_start"]) == ["2026-01-12", "2026-01-19"]
    assert len(dd.filter_period(weekly, "week_start")) == 3


def test_weekday_focus_and_leave_one_out():
    mix = pd.DataFrame([
        {"campaign": c, "weekday": "Fri", "clicks": k,
         "share_of_weekday_clicks": s, "share_of_campaign_clicks": 0.2,
         "share_vs_even": 1.4, "actions_per_click": 0.1,
         "baseline_actions_per_click": 0.2,
         "actions_per_click_vs_baseline": 0.5}
        for c, k, s in (("Alpha", 10, 0.25), ("Pmax", 30, 0.75))])
    focus = dd.weekday_focus_table(mix, "Fri")
    assert list(focus["campaign"]) == ["Pmax", "Alpha"]
    loo = pd.DataFrame([
        {"left_out": "(none)", "weekday": "Fri",
         "actions_per_click_vs_baseline": 0.7},
        {"left_out": "Alpha", "weekday": "Fri",
         "actions_per_click_vs_baseline": 0.4},
        {"left_out": "Pmax", "weekday": "Fri",
         "actions_per_click_vs_baseline": 1.03},
        {"left_out": "Pmax", "weekday": "Mon",
         "actions_per_click_vs_baseline": 1.0},
    ])
    table = dd.leave_one_out_for_weekday(loo, "Fri")
    assert list(table["left_out"]) == ["(none)", "Pmax", "Alpha"]


def test_what_if_parts():
    single = pd.DataFrame([{"scenario": "s", "delta": 5.0}])
    rows, span = dd.what_if_parts(single)
    assert len(rows) == 1 and span is None
    variants = pd.DataFrame([
        {"variant": "core_only", "delta": 2.0},
        {"variant": "core_and_pmax", "delta": 3.0},
        {"variant": "range", "delta": None, "display": "+2 to +3"}])
    rows, span = dd.what_if_parts(variants)
    assert list(rows["variant"]) == ["core_only", "core_and_pmax"]
    assert span["display"] == "+2 to +3"


def test_lag_check_summary():
    lag = pd.DataFrame([
        {"lag": 3, "measure": "recent_trend_changes_total",
         "value": "vs lag 3", "campaigns": 0},
        {"lag": 3, "measure": "label_changes_total",
         "value": "vs lag 3", "campaigns": 0},
        {"lag": 14, "measure": "recent_trend_changes_total",
         "value": "vs lag 3", "campaigns": 1},
        {"lag": 14, "measure": "label_changes_total",
         "value": "vs lag 3", "campaigns": 1},
        {"lag": 14, "measure": "label", "value": "test",
         "campaigns": 2},
    ])
    table = dd.lag_check_summary(lag).set_index("lag")
    assert table.loc[14, "trend_changes"] == 1
    assert table.loc[3, "label_changes"] == 0


def test_rules_table_reads_config():
    config = {"analysis": {
        "volume_rule": {"min_conversions": 10, "min_days_active": 14},
        "recommendation_rules": {"continue_max_ratio": 1.0,
                                 "benchmark": {"groups": ["core"]}},
        "recent_trend": {"conversion_lag_days": 3},
        "run_gap_days": 14}}
    table = dd.rules_table(config).set_index("setting")
    assert table.loc["volume_rule.min_conversions", "value"] == "10"
    assert table.loc["recommendation_rules.benchmark.groups",
                     "value"] == "['core']"
    assert table.loc["run_gap_days", "value"] == "14"


def test_csv_bytes():
    assert dd.csv_bytes(pd.DataFrame({"a": [1]})) == b"a\n1\n"


def test_client_config_and_output_root(tmp_path):
    (tmp_path / "restaurant.yaml").write_text("x: 1\n")
    (tmp_path / "synthetic_b.yaml").write_text("x: 1\n")
    assert dd.client_config_path("synthetic_b", tmp_path).name == \
        "synthetic_b.yaml"
    with pytest.raises(FileNotFoundError, match="No config"):
        dd.client_config_path("unknown", tmp_path)
    assert dd.client_output_root("restaurant", {}, tmp_path) is None
    config = {"analysis": {"output_root": "outputs/synthetic_b"}}
    assert dd.client_output_root("synthetic_b", config, tmp_path) == \
        tmp_path / "outputs" / "synthetic_b"
    assert dd.client_output_root("other", {}, tmp_path) == \
        tmp_path / "outputs" / "other"


def test_optional_tables_are_none_when_missing(tmp_path):
    results = tmp_path / "outputs" / "results"
    results.mkdir(parents=True)
    (results / "lag_check.csv").write_text("lag\n3\n")
    tables = dd.load_optional_tables({"analysis": {}}, root=tmp_path)
    assert list(tables["lag_check"]["lag"]) == [3]
    assert tables["weekday_top_days"] is None
    assert set(tables) == set(dd.OPTIONAL_PATHS)


def test_trend_takeaway_counts_trends():
    rows = pd.DataFrame({"campaign": ["A", "B", "C"],
                         "recent_trend": ["worsening", "stable",
                                          "worsening"]})
    assert dd.trend_takeaway(rows) == (
        "3 active campaigns with a recent trend: 2 worsening, 1 stable.")
    assert dd.trend_takeaway(rows.iloc[:1]) == (
        "1 active campaign with a recent trend: 1 worsening.")
    assert dd.trend_takeaway(rows.iloc[:0]) == (
        "No active campaign has a recent trend.")


def test_weekday_takeaway_low_high_and_what_if():
    pooled = pd.DataFrame({"weekday": ["Mon", "Tue", "Sat"],
                           "cost_per_tracked_action": [5.0, 6.5, 3.25]})
    text = dd.weekday_takeaway(pooled, "SEK", "+10 tracked actions",
                               "Move spend")
    assert text == ("Cost per tracked action is lowest on Sat (3.25 SEK) "
                    "and highest on Tue (6.50 SEK). Move spend: "
                    "+10 tracked actions, a linear estimate.")
    assert "linear" not in dd.weekday_takeaway(pooled, "SEK")


def test_lag_takeaway_zero_and_some_changes():
    summary = pd.DataFrame({"lag": [3, 5], "trend_changes": [0, 0],
                            "label_changes": [0, 0]})
    assert dd.lag_takeaway(summary, 3) == (
        "Configured lag: 3 days. No trend or label changes with any "
        "other lag.")
    summary.loc[1, "label_changes"] = 1
    assert "treat the most recent weeks with care" in \
        dd.lag_takeaway(summary, 3)


def test_journey_takeaway_weights_by_tracked_actions():
    journey = pd.DataFrame({"campaign": ["A", "B"],
                            "tracked_actions": [300.0, 100.0],
                            "directions_share": [1.0, 0.0],
                            "calls_share": [0.0, 1.0]})
    assert dd.journey_takeaway(journey) == (
        "Across 2 campaigns, 75% of tracked actions are directions "
        "requests and 25% are calls.")
    assert dd.journey_takeaway(journey.iloc[:0]) == (
        "No tracked actions to split by type.")


def test_format_period_same_and_different_years():
    assert dd.format_period("2026-05-31", "2026-07-13") == \
        "31 May – 13 Jul 2026"
    assert dd.format_period("2025-11-18", "2026-07-14") == \
        "18 Nov 2025 – 14 Jul 2026"
    assert dd.format_period("2026-01-05", "2026-01-09") == \
        "5 Jan – 9 Jan 2026"


def test_format_period_missing_end_uses_the_fallback():
    """A missing date gives "", as _period does (shown as "—")."""
    assert dd.format_period("2026-05-31", None) == ""
    assert dd.format_period(None, "2026-05-31") == ""
    assert dd.format_period("2026-05-31", float("nan")) == ""
    assert dd.period_text("") == ""
    assert dd.period_text(None) == ""
    assert dd.period_text("2026-05-31 to 2026-07-13") == \
        "31 May – 13 Jul 2026"


def test_split_action_headline_and_detail():
    assert dd.split_action("keep running") == ("Keep running", "")
    assert dd.split_action(
        "keep running, but test changes; cost has risen; check it") == (
        "Keep running, but test changes", "cost has risen; check it")
    assert dd.split_action(
        "restart only with changes; best run was run 2 "
        "(2025-06-06 to 2025-10-04)") == (
        "Restart only with changes",
        "best run was run 2 6 Jun – 4 Oct 2025")
    assert dd.split_action(None) == ("", "")


def test_trend_text_dash_and_capitalised():
    assert dd.trend_text("not_active") == "—"
    assert dd.trend_text("") == "—"
    assert dd.trend_text(None) == "—"
    assert dd.trend_text(float("nan")) == "—"
    assert dd.trend_text("worsening") == "Worsening"
    assert dd.trend_text("improving") == "Improving"
    assert dd.trend_text("stable") == "Stable"


def test_status_text_capitalised():
    assert dd.status_text("ended") == "Ended"
    assert dd.status_text("active") == "Active"
    assert dd.status_text(None) == "—"


KPI = {"judged_campaigns": 11, "spend": 177041.32,
       "tracked_actions": 35735.83, "cost_per_tracked_action": 4.954168,
       "benchmark": 4.879686, "leave_one_out": True, "loo_min": 4.04802,
       "loo_max": 5.157151}


def test_totals_strip_items_values_and_captions():
    items = dd.totals_strip_items(KPI, "SEK")
    assert items == [
        ("Spend", "177,041 SEK", "Total ad spend of the 11 campaigns."),
        ("Tracked actions", "35,736",
         "Directions requests and calls counted by Google Ads."),
        ("Cost per tracked action", "4.95 SEK",
         "Spend divided by tracked actions."),
        ("Benchmark", "4.88 SEK",
         "The average that campaigns are compared with (4.05 to 5.16 "
         "SEK, depending on which campaign is left out)."),
    ]


def test_totals_strip_benchmark_without_leave_one_out():
    kpi = dict(KPI, leave_one_out=False, loo_min=None, loo_max=None)
    assert dd.totals_strip_items(kpi, "SEK")[3][2] == (
        "The average that campaigns are compared with.")


def test_reason_cost_regex():
    assert dd.reason_cost(
        "group core_pmax is not comparable with the core benchmark "
        "(leave-one-out); cost per tracked action is 177.90; judge "
        "against its own history") == 177.90
    assert dd.reason_cost("cost per tracked action is 1,234.5") == 1234.5
    assert dd.reason_cost("no figure here") is None
    assert dd.reason_cost(None) is None


def _nc_recs(group, reason, cost=None):
    return pd.DataFrame([
        {"campaign": "Pm", "group": group, "label": "not_comparable",
         "status_now": "ended", "reason": reason,
         "label_cost_per_tracked_action": cost},
        {"campaign": "Other", "group": "core", "label": "test",
         "status_now": "active", "reason": "x",
         "label_cost_per_tracked_action": 5.0}])


def test_not_comparable_lines_performance_max():
    names = {"core_pmax": "Performance Max", "core": "Core campaigns"}
    lines = dd.not_comparable_lines(
        _nc_recs("core_pmax", "cost per tracked action is 177.90; x"),
        names, "Core campaigns", "SEK")
    assert lines == [{
        "name": "Pm", "sub": "Performance Max · Ended",
        "cost": "177.90 SEK per tracked action. A different kind of "
                "campaign, so it isn't compared with the Core campaigns "
                "benchmark."}]
    assert "leave-one-out" not in str(lines)


def test_not_comparable_lines_other_group_field_and_no_cost():
    names = {"display": "Display", "core": "Core campaigns"}
    lines = dd.not_comparable_lines(
        _nc_recs("display", "no figure", cost=12.5), names,
        "Core campaigns", "SEK")
    assert lines[0]["cost"] == ("12.50 SEK per tracked action. Not "
                                "comparable with the Core campaigns "
                                "benchmark.")
    lines = dd.not_comparable_lines(
        _nc_recs("display", "no figure"), names, "Core campaigns", "SEK")
    assert lines[0]["cost"] == ("Not comparable with the Core campaigns "
                                "benchmark.")
    assert dd.not_comparable_lines(
        _nc_recs("display", "x").iloc[1:], names, "C", "SEK") == []


def test_names_and():
    assert dd.names_and([]) == ""
    assert dd.names_and(["A"]) == "A"
    assert dd.names_and(["A", "B"]) == "A and B"
    assert dd.names_and(["A", "B", "C"]) == "A, B and C"


def _how_config(window=90):
    rules = {"continue_max_ratio": 1.0, "test_max_ratio": 2.0,
             "judged_groups": ["core", "sep"],
             "benchmark": {"groups": ["core"]}}
    if window:
        rules["recent_label"] = {"window_days": window}
    return {"analysis": {"recommendation_rules": rules}}


HOW_NAMES = {"core": "Core campaigns", "sep": "September campaigns"}


def _how_recs():
    return pd.DataFrame({
        "campaign": list("ABCDE"),
        "group": ["core", "core", "sep", "sep", "other"],
        "label": ["test", "insufficient_data", "insufficient_data",
                  "continue", "insufficient_data"]})


def test_how_to_read_lines_restaurant_like():
    lines = dd.how_to_read_lines(_how_config(), KPI, HOW_NAMES,
                                 _how_recs(), currency="SEK")
    text = [f"{lead}: {body}" if lead else body for lead, body in lines]
    assert text == [
        "Tracked action: something Google Ads counts after an ad, mostly "
        "directions requests and calls (Google Ads calls it a "
        "conversion). It is not a booking.",
        "Benchmark: the average cost per tracked action of the Core "
        "campaigns, 4.88 SEK. Each campaign is compared with the average "
        "of the other campaigns.",
        "Labels: up to 1.0x the benchmark: Continue. Up to 2.0x: Test. "
        "Above that: Pause or review.",
        "Period: the latest run with enough data, or the last 90 days "
        "for a running campaign. The bars use the figures of that "
        "period.",
        "Totals: cover 11 campaigns (Core campaigns and September "
        "campaigns) over the whole data period; 2 of them have too "
        "little data for a label. The benchmark uses the Core campaigns "
        "only, so it differs slightly from the overall cost per tracked "
        "action.",
        "Filters only change what you see. They never change a label, a "
        "tile or a total.",
        "Labels are prompts for review, not proof of cause. They compare "
        "cost with a benchmark. They don't show why a campaign did better "
        "or worse.",
    ]


def test_how_to_read_lines_no_window_same_cost_no_leave_one_out():
    kpi = dict(KPI, cost_per_tracked_action=4.88, benchmark=4.879686,
               leave_one_out=False)
    config = _how_config(window=None)
    config["analysis"]["recommendation_rules"]["continue_max_ratio"] = 0.8
    lines = dict(dd.how_to_read_lines(config, kpi, HOW_NAMES,
                                      _how_recs().iloc[:2]))
    assert lines["Period"] == ("the latest run with enough data. The bars "
                               "use the figures of that period.")
    assert lines["Totals"].endswith(
        "1 of them has too little data for a label.")
    assert lines["Benchmark"].endswith(
        "Each campaign is compared with this average.")
    assert lines["Labels"].startswith("up to 0.8x the benchmark")


def test_readable_keys_display_only():
    table = pd.DataFrame({
        "campaign": ["A", "B"], "label": ["pause_or_review", "test"],
        "volume flag": ["insufficient_data", "ok"],
        "trend": ["not_active", "worsening"], "ratio": [1.0, 2.0]})
    shown = dd.readable_keys(table)
    assert list(shown["label"]) == ["Pause or review", "Test"]
    assert list(shown["volume flag"]) == ["Insufficient data", "ok"]
    assert list(shown["trend"]) == ["Not active", "worsening"]
    assert list(table["label"]) == ["pause_or_review", "test"]
    assert dd.label_text("not_comparable") == "Not comparable"
