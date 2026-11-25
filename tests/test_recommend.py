"""Tests for src/recommend.py (T5).

All data is tiny and made up, in tmp_path. No real data, no real
campaign names, no real rows from the exports.
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.recommend import (action_text, compute_benchmark,
                           label_run, main, recommend_campaigns,
                           recommend_runs, sensitivity_table,
                           write_recommend_report)

CAVEAT = "Tracked actions only (mainly get-directions requests and phone calls), not bookings or orders. This shows campaign performance, not proof that an offer brought extra customers."

RULES = {
    "continue_max_ratio": 1.0,
    "test_max_ratio": 2.0,
    "repeat_min_runs": 2,
    "active_window_days": 14,
    "sensitivity_continue_max_ratio": [0.75, 1.0, 1.25, 1.5],
    "sensitivity_test_max_ratio": [1.5, 2.0, 3.0],
}
VOLUME = {"min_conversions": 10, "min_days_active": 14}


def _day_summary():
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "spend": 100.0,
         "clicks": 200, "conversions": 20.0,
         "last_active_date": "2024-02-14"},
        {"campaign": "Beta", "group": "core", "spend": 100.0,
         "clicks": 200, "conversions": 20.0,
         "last_active_date": "2024-01-14"},
        {"campaign": "Gamma", "group": "monthly_history_only",
         "spend": 50.0, "clicks": 100, "conversions": 5.0,
         "last_active_date": "2023-12-01"},
    ])


def _runs_df():
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "run_number": 1,
         "start": "2024-01-01", "end": "2024-01-14",
         "active_days": 14, "spend": 50.0, "clicks": 100,
         "conversions": 10.0, "cost_per_conversion": 5.0,
         "volume_flag": "ok"},
        {"campaign": "Alpha", "group": "core", "run_number": 2,
         "start": "2024-02-01", "end": "2024-02-14",
         "active_days": 14, "spend": 100.0, "clicks": 100,
         "conversions": 10.0, "cost_per_conversion": 10.0,
         "volume_flag": "ok"},
        {"campaign": "Beta", "group": "core", "run_number": 1,
         "start": "2024-01-01", "end": "2024-01-14",
         "active_days": 14, "spend": 210.0, "clicks": 100,
         "conversions": 10.0, "cost_per_conversion": 21.0,
         "volume_flag": "ok"},
    ])


def test_benchmark_calculated_correctly():
    # Core spend 200 / core conversions 40 = 5.00. Gamma is not
    # core, so its spend and conversions are not included.
    assert compute_benchmark(_day_summary()) == 5.0


def test_each_label_at_its_boundary():
    # Benchmark is 5.0: ratio 1.0 -> continue, 2.0 -> test,
    # just above 2.0 -> pause_or_review.
    assert label_run(1.0, "ok", RULES) == "continue"
    assert label_run(2.0, "ok", RULES) == "test"
    assert label_run(2.01, "ok", RULES) == "pause_or_review"
    assert label_run(0.56, "ok", RULES) == "continue"


def test_insufficient_data_always_wins():
    assert label_run(0.5, "insufficient_data", RULES) == \
        "insufficient_data"
    assert label_run(None, "ok", RULES) == "insufficient_data"


def test_recommend_runs_labels_and_reasons():
    recs = recommend_runs(_runs_df(), 5.0, RULES, CAVEAT)
    alpha1 = recs[(recs["campaign"] == "Alpha")
                  & (recs["run_number"] == 1)].iloc[0]
    alpha2 = recs[(recs["campaign"] == "Alpha")
                  & (recs["run_number"] == 2)].iloc[0]
    beta = recs[recs["campaign"] == "Beta"].iloc[0]
    assert alpha1["ratio_to_benchmark"] == 1.0
    assert alpha1["label"] == "continue"
    assert alpha2["ratio_to_benchmark"] == 2.0
    assert alpha2["label"] == "test"
    assert beta["ratio_to_benchmark"] == 4.2
    assert beta["label"] == "pause_or_review"
    for _, row in recs.iterrows():
        assert row["reason"]
        assert "tracked actions" in row["reason"] or \
            "core benchmark" in row["reason"]
        assert row["caveat"] == CAVEAT
        assert "extra customers" not in row["reason"]


def test_repeat_eligible_needs_two_runs():
    recs = recommend_runs(_runs_df(), 5.0, RULES, CAVEAT)
    campaigns = recommend_campaigns(recs, _day_summary(), RULES, CAVEAT)
    alpha = campaigns[campaigns["campaign"] == "Alpha"].iloc[0]
    beta = campaigns[campaigns["campaign"] == "Beta"].iloc[0]
    gamma = campaigns[campaigns["campaign"] == "Gamma"].iloc[0]
    # Alpha: latest run with volume is run 2 (test), 2 runs.
    assert alpha["label"] == "test"
    assert alpha["runs_with_volume"] == 2
    assert bool(alpha["repeat_eligible"]) is True
    # Beta: 1 run with volume -> not repeat eligible.
    assert beta["label"] == "pause_or_review"
    assert beta["runs_with_volume"] == 1
    assert bool(beta["repeat_eligible"]) is False
    # Gamma: no runs at all -> insufficient_data.
    assert gamma["label"] == "insufficient_data"
    assert gamma["runs_with_volume"] == 0
    assert bool(gamma["repeat_eligible"]) is False


def test_latest_run_with_volume_wins():
    runs = pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "run_number": 1,
         "start": "2024-01-01", "end": "2024-01-14",
         "active_days": 14, "spend": 50.0, "clicks": 100,
         "conversions": 10.0, "cost_per_conversion": 5.0,
         "volume_flag": "ok"},
        {"campaign": "Alpha", "group": "core", "run_number": 2,
         "start": "2024-02-01", "end": "2024-02-02",
         "active_days": 2, "spend": 1.0, "clicks": 1,
         "conversions": 1.0, "cost_per_conversion": 1.0,
         "volume_flag": "insufficient_data"},
    ])
    recs = recommend_runs(runs, 5.0, RULES, CAVEAT)
    campaigns = recommend_campaigns(
        recs, _day_summary().iloc[[0]], RULES, CAVEAT)
    alpha = campaigns.iloc[0]
    # Latest run has no volume, so the label comes from run 1.
    assert alpha["label"] == "continue"
    assert alpha["runs_with_volume"] == 1


def test_report_has_no_names(tmp_path):
    recs = recommend_runs(_runs_df(), 5.0, RULES, CAVEAT)
    campaigns = recommend_campaigns(recs, _day_summary(), RULES, CAVEAT)
    sens = sensitivity_table(recs, _day_summary(), RULES)
    report = tmp_path / "recommend-report.md"
    write_recommend_report(report, recs, campaigns, sens, 5.0)
    text = report.read_text()
    assert "Alpha" not in text
    assert "Beta" not in text
    assert "Gamma" not in text
    assert "continue: 1" in text
    assert "unstable" in text


def test_main_writes_recommendations(tmp_path, capsys):
    runs = tmp_path / "runs.csv"
    day = tmp_path / "campaign_summary_day.csv"
    _runs_df().to_csv(runs, index=False)
    _day_summary().to_csv(day, index=False)
    config = {
        "analysis": {
            "caveat_text": CAVEAT,
            "recommendation_rules": RULES,
            "volume_rule": VOLUME,
            "outputs": {
                "runs": str(runs),
                "campaign_summary_day": str(day),
                "recommendations_by_run": str(tmp_path / "rec_run.csv"),
                "recommendations_by_campaign": str(
                    tmp_path / "rec_campaign.csv"),
                "recommendation_sensitivity": str(
                    tmp_path / "rec_sensitivity.csv"),
                "recommend_report": str(tmp_path / "recommend-report.md"),
            },
        },
    }
    config_path = tmp_path / "restaurant.yaml"
    config_path.write_text(yaml.safe_dump(config))
    assert main(["--config", str(config_path)]) == 0
    out = capsys.readouterr().out
    assert "Alpha" not in out
    for name in ("rec_run.csv", "rec_campaign.csv",
                 "rec_sensitivity.csv", "recommend-report.md"):
        assert (tmp_path / name).is_file()
    run_recs = pd.read_csv(tmp_path / "rec_run.csv")
    assert len(run_recs) == 3
    assert (run_recs["caveat"] == CAVEAT).all()
