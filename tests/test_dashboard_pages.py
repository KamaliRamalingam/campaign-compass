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


def test_not_comparable_rows():
    rows = dd.not_comparable_rows(_recs())
    assert list(rows["campaign"]) == ["Pmax"]
    assert rows.iloc[0]["reason"] == "pmax reason"


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
