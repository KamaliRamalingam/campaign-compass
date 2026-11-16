"""Tests for PR 1: config-driven benchmark, leave-one-out,
not_comparable and not_judged groups, run_groups, and the
config hygiene (S8).

All data is tiny and made up. No real data, no real campaign
names, no real rows from the exports.
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import recommend

CAVEAT = "Made-up caveat for tests."

RULES = {
    "continue_max_ratio": 1.0,
    "test_max_ratio": 2.0,
    "repeat_min_runs": 2,
    "active_window_days": 14,
    "sensitivity_continue_max_ratio": [0.75, 1.0, 1.25, 1.5],
    "sensitivity_test_max_ratio": [1.5, 2.0, 3.0],
}


def _day_summary():
    """Alpha and Beta core, Pmax core_pmax, Gamma not judged."""
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "spend": 100.0,
         "clicks": 200, "conversions": 20.0,
         "last_active_date": "2024-02-14"},
        {"campaign": "Beta", "group": "core", "spend": 300.0,
         "clicks": 200, "conversions": 20.0,
         "last_active_date": "2024-02-14"},
        {"campaign": "Pmax", "group": "core_pmax", "spend": 400.0,
         "clicks": 900, "conversions": 40.0,
         "last_active_date": "2024-02-14"},
        {"campaign": "Gamma", "group": "monthly_history_only",
         "spend": 500.0, "clicks": 100, "conversions": 50.0,
         "last_active_date": "2024-02-14"},
    ])


def _run(campaign, group, number, spend, conversions,
         volume_flag="ok"):
    return {"campaign": campaign, "group": group,
            "run_number": number, "start": "2024-01-01",
            "end": "2024-02-14", "active_days": 45,
            "spend": spend, "clicks": 100,
            "conversions": conversions,
            "cost_per_conversion": spend / conversions,
            "volume_flag": volume_flag}


def _runs_df():
    return pd.DataFrame([
        _run("Alpha", "core", 1, 100.0, 20.0),
        _run("Beta", "core", 1, 300.0, 20.0),
        _run("Pmax", "core_pmax", 1, 400.0, 40.0),
        _run("Gamma", "monthly_history_only", 1, 500.0, 50.0),
    ])


def _write_main_config(tmp_path, rules):
    runs = tmp_path / "runs.csv"
    day = tmp_path / "campaign_summary_day.csv"
    _runs_df().to_csv(runs, index=False)
    _day_summary().to_csv(day, index=False)
    config = {
        "analysis": {
            "caveat_text": CAVEAT,
            "recommendation_rules": rules,
            "outputs": {
                "runs": str(runs),
                "campaign_summary_day": str(day),
                "recommendations_by_run": str(tmp_path / "rec_run.csv"),
                "recommendations_by_campaign": str(
                    tmp_path / "rec_campaign.csv"),
                "recommendation_sensitivity": str(
                    tmp_path / "rec_sensitivity.csv"),
                "recommend_report": str(
                    tmp_path / "recommend-report.md"),
            },
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


# --- S8: pause_above_ratio is not used -------------------------

def test_main_warns_when_pause_above_ratio_is_set(tmp_path, capsys):
    rules = dict(RULES, pause_above_ratio=2.0)
    path = _write_main_config(tmp_path, rules)
    assert recommend.main(["--config", str(path)]) == 0
    assert "pause_above_ratio is not used" in capsys.readouterr().out


def test_main_has_no_warning_without_pause_above_ratio(
        tmp_path, capsys):
    path = _write_main_config(tmp_path, RULES)
    assert recommend.main(["--config", str(path)]) == 0
    assert "WARNING" not in capsys.readouterr().out


# --- M1: run_groups replaces the hard-coded extra group ---------

def test_run_groups_from_config():
    from src.time_patterns import resolve_run_groups
    analysis = {"time_groups": ["core"],
                "run_groups": ["core", "core_pmax"]}
    assert resolve_run_groups(analysis) == ["core", "core_pmax"]


def test_run_groups_default_keeps_old_behaviour():
    from src.time_patterns import resolve_run_groups
    assert resolve_run_groups({"time_groups": ["core"]}) == [
        "core", "sep_2026_group"]


def test_runs_table_covers_only_run_groups():
    from src.time_patterns import runs_table
    groups = {"core": ["Alpha"], "core_pmax": ["Pmax"],
              "other": ["Gamma"]}
    rows = [{"date": f"2024-01-{day:02d}", "campaign": name,
             "clicks": 1, "cost": 1.0, "conversions": 1.0}
            for day in range(1, 4) for name in ("Alpha", "Pmax", "Gamma")]
    table = runs_table(pd.DataFrame(rows), groups,
                       ["core", "core_pmax"], 14, {})
    assert sorted(table["campaign"]) == ["Alpha", "Pmax"]


# --- M1: benchmark groups and leave-one-out ---------------------
# Alpha 100/20, Beta 300/20, Pmax 400/40, Gamma 500/50.

PR1_RULES = dict(
    RULES,
    benchmark={"groups": ["core"], "leave_one_out": True},
    not_comparable_groups=["core_pmax"],
    judged_groups=["core"],
)


def test_benchmark_default_is_core_pooled():
    # (100 + 300) / (20 + 20) = 10.00
    assert recommend.compute_benchmark(_day_summary()) == 10.0


def test_benchmark_with_and_without_pmax():
    summary = _day_summary()
    assert recommend.compute_benchmark(summary, ["core"]) == 10.0
    # Make PMax dearer (800 / 40 = 20.00) so including it moves
    # the benchmark.
    summary.loc[summary["campaign"] == "Pmax", "spend"] = 800.0
    # (100 + 300 + 800) / 80 = 15.00
    assert recommend.compute_benchmark(
        summary, ["core", "core_pmax"]) == 15.0


def test_benchmark_leave_one_out_by_hand():
    summary = _day_summary()
    # Alpha left out: Beta only, 300 / 20 = 15.00.
    assert recommend.compute_benchmark(
        summary, ["core"], exclude="Alpha") == 15.0
    # Beta left out: Alpha only, 100 / 20 = 5.00.
    assert recommend.compute_benchmark(
        summary, ["core"], exclude="Beta") == 5.0


def test_benchmarks_by_campaign_loo_and_pooled():
    result = recommend.benchmarks_by_campaign(
        _day_summary(), ["core"], True)
    assert result["Alpha"] == (15.0, "leave_one_out")
    assert result["Beta"] == (5.0, "leave_one_out")
    # Outside the benchmark groups: the pooled benchmark.
    assert result["Gamma"] == (10.0, "pooled")
    assert result["Pmax"] == (10.0, "pooled")


def test_benchmarks_by_campaign_without_loo_is_pooled():
    result = recommend.benchmarks_by_campaign(
        _day_summary(), ["core"], False)
    assert set(result.values()) == {(10.0, "pooled")}


def test_leave_one_out_falls_back_when_alone():
    summary = _day_summary().loc[lambda d: d["campaign"] != "Beta"]
    result = recommend.benchmarks_by_campaign(summary, ["core"], True)
    assert result["Alpha"] == (
        5.0, "pooled (leave-one-out not possible)")


def test_recommend_runs_uses_loo_benchmark():
    summary = _day_summary()
    per_campaign = recommend.benchmarks_by_campaign(
        summary, ["core"], True)
    recs = recommend.recommend_runs(
        _runs_df(), 10.0, PR1_RULES, CAVEAT, per_campaign)
    by_name = recs.set_index("campaign")
    # Alpha: 5.00 / 15.00 = 0.33 -> continue.
    assert round(by_name.loc["Alpha", "ratio_to_benchmark"], 4) == \
        round(5.0 / 15.0, 4)
    assert by_name.loc["Alpha", "benchmark"] == 15.0
    assert by_name.loc["Alpha", "benchmark_basis"] == "leave_one_out"
    assert by_name.loc["Alpha", "label"] == "continue"
    # Beta: 15.00 / 5.00 = 3.00 -> pause_or_review.
    assert by_name.loc["Beta", "ratio_to_benchmark"] == 3.0
    assert by_name.loc["Beta", "label"] == "pause_or_review"
    assert "core benchmark (leave-one-out)" in \
        by_name.loc["Beta", "reason"]


def test_recommend_runs_default_keeps_old_reason():
    recs = recommend.recommend_runs(_runs_df(), 10.0, RULES, CAVEAT)
    alpha = recs.set_index("campaign").loc["Alpha"]
    assert alpha["benchmark"] == 10.0
    assert alpha["benchmark_basis"] == "pooled"
    assert "times the core benchmark; run" in alpha["reason"]


# --- M1: Performance Max is not_comparable ---------------------

def test_pmax_is_not_comparable():
    summary = _day_summary()
    per_campaign = recommend.benchmarks_by_campaign(
        summary, ["core"], True)
    recs = recommend.recommend_runs(
        _runs_df(), 10.0, PR1_RULES, CAVEAT, per_campaign)
    pmax_run = recs.set_index("campaign").loc["Pmax"]
    assert pmax_run["label"] == "not_comparable"
    assert pd.isna(pmax_run["ratio_to_benchmark"])
    assert "times the" not in pmax_run["reason"]
    assert "own history" in pmax_run["reason"]
    campaigns = recommend.recommend_campaigns(
        recs, summary, PR1_RULES, CAVEAT).set_index("campaign")
    pmax = campaigns.loc["Pmax"]
    assert pmax["label"] == "not_comparable"
    assert not pmax["repeat_eligible"]
    assert pmax["action_text"] == (
        "judge against its own history, not the benchmark")


# --- M4: campaigns outside judged groups are not_judged --------

def test_outside_judged_groups_is_not_judged():
    summary = _day_summary()
    # Gamma has plenty of volume but no runs (its group gets no
    # runs), the case that used to say insufficient_data.
    runs = _runs_df().loc[lambda d: d["campaign"] != "Gamma"]
    recs = recommend.recommend_runs(runs, 10.0, PR1_RULES, CAVEAT)
    campaigns = recommend.recommend_campaigns(
        recs, summary, PR1_RULES, CAVEAT).set_index("campaign")
    gamma = campaigns.loc["Gamma"]
    assert gamma["label"] == "not_judged"
    assert gamma["reason"] == "group monthly_history_only not evaluated"
    assert gamma["action_text"] == "not evaluated: group not judged"


def test_not_judged_runs_are_labelled_not_judged():
    recs = recommend.recommend_runs(
        _runs_df(), 10.0, PR1_RULES, CAVEAT)
    gamma = recs.set_index("campaign").loc["Gamma"]
    assert gamma["label"] == "not_judged"
    assert gamma["reason"].startswith(
        "group monthly_history_only not evaluated")


def test_without_new_keys_old_labels_are_kept():
    # No judged_groups / not_comparable_groups: Gamma with no
    # runs is insufficient_data and Pmax is judged, as before.
    runs = _runs_df().loc[lambda d: d["campaign"] != "Gamma"]
    recs = recommend.recommend_runs(runs, 10.0, RULES, CAVEAT)
    campaigns = recommend.recommend_campaigns(
        recs, _day_summary(), RULES, CAVEAT).set_index("campaign")
    assert campaigns.loc["Gamma", "label"] == "insufficient_data"
    assert campaigns.loc["Pmax", "label"] == "continue"


def test_fixed_labels_are_stable_in_sensitivity():
    recs = recommend.recommend_runs(
        _runs_df(), 10.0, PR1_RULES, CAVEAT)
    sens = recommend.sensitivity_table(
        recs, _day_summary(), PR1_RULES).set_index("campaign")
    assert set(sens.loc["Pmax", "label"]) == {"not_comparable"}
    assert set(sens.loc["Gamma", "label"]) == {"not_judged"}
    assert sens.loc["Pmax", "label_stable"].all()
    assert sens.loc["Gamma", "label_stable"].all()


# --- Report: both benchmarks, no names -------------------------

def test_report_lists_both_benchmarks(tmp_path):
    summary = _day_summary()
    summary.loc[summary["campaign"] == "Pmax", "spend"] = 800.0
    recs = recommend.recommend_runs(
        _runs_df(), 10.0, PR1_RULES, CAVEAT)
    campaigns = recommend.recommend_campaigns(
        recs, summary, PR1_RULES, CAVEAT)
    sens = recommend.sensitivity_table(recs, summary, PR1_RULES)
    report = tmp_path / "recommend-report.md"
    recommend.write_recommend_report(
        report, recs, campaigns, sens, 10.0,
        recommend.benchmark_summary(summary, PR1_RULES))
    text = report.read_text()
    assert "## Benchmarks" in text
    assert "leave-one-out: on" in text
    assert "- Pooled (core): 10.00" in text
    assert "- Leave-one-out (core): 5.00 to 15.00" in text
    # With PMax: (100 + 300 + 800) / 80 = 15.00.
    assert "- Pooled (core+core_pmax): 15.00" in text
    for name in ("Alpha", "Beta", "Pmax", "Gamma"):
        assert name not in text
