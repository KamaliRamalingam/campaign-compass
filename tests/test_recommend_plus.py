"""Tests for the T5b recommendation improvements.

All data is tiny and made up, in tmp_path. No real data, no real
campaign names, no real rows from the exports.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.recommend import (action_text, recommend_campaigns,
                           recommend_runs, sensitivity_table,
                           write_recommend_report)

CAVEAT = "Tracked actions only (mainly get-directions requests and phone calls), not bookings or orders. This shows campaign performance, not proof that an offer brought extra customers."

RULES = {
    "continue_max_ratio": 1.0,
    "test_max_ratio": 2.0,
    "pause_above_ratio": 2.0,
    "repeat_min_runs": 2,
    "active_window_days": 14,
    "sensitivity_continue_max_ratio": [0.75, 1.0, 1.25, 1.5],
    "sensitivity_test_max_ratio": [1.5, 2.0, 3.0],
}
VOLUME = {"min_conversions": 10, "min_days_active": 14}


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


def _day_summary():
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "spend": 100.0,
         "clicks": 200, "conversions": 20.0,
         "last_active_date": "2024-02-14"},
        {"campaign": "Beta", "group": "core", "spend": 100.0,
         "clicks": 200, "conversions": 20.0,
         "last_active_date": "2024-01-14"},
    ])


def test_status_now_at_the_window_boundary():
    # Latest date in the daily data is 2024-02-14. Exactly 14
    # days before it is active; 15 days before it is ended.
    summary = pd.DataFrame([
        {"campaign": "Edge", "group": "core", "spend": 10.0,
         "clicks": 10, "conversions": 1.0,
         "last_active_date": "2024-01-31"},
        {"campaign": "Old", "group": "core", "spend": 10.0,
         "clicks": 10, "conversions": 1.0,
         "last_active_date": "2024-01-30"},
        {"campaign": "New", "group": "core", "spend": 10.0,
         "clicks": 10, "conversions": 1.0,
         "last_active_date": "2024-02-14"},
    ])
    empty = pd.DataFrame(columns=["campaign", "label",
                                  "run_number",
                                  "ratio_to_benchmark",
                                  "cost_per_conversion",
                                  "start", "end"])
    campaigns = recommend_campaigns(empty, summary, RULES, CAVEAT)
    by_name = campaigns.set_index("campaign")
    assert by_name.loc["Edge", "status_now"] == "active"
    assert by_name.loc["Old", "status_now"] == "ended"
    assert by_name.loc["New", "status_now"] == "active"


def test_best_run_is_the_earlier_run():
    recs = recommend_runs(_runs_df(), 5.0, RULES, VOLUME, CAVEAT)
    campaigns = recommend_campaigns(recs, _day_summary(), RULES, CAVEAT)
    alpha = campaigns[campaigns["campaign"] == "Alpha"].iloc[0]
    # Latest run with volume is run 2 (test, ratio 2.0); the best
    # run is run 1 (cost per conversion 5.0, not 10.0).
    assert alpha["label"] == "test"
    assert alpha["best_run_number"] == 1
    assert alpha["best_run_cost_per_conversion"] == 5.0
    assert alpha["best_run_start"] == "2024-01-01"
    assert alpha["best_run_end"] == "2024-01-14"
    # Alpha is active, repeat eligible, best run is not latest.
    assert alpha["status_now"] == "active"
    assert alpha["action_text"] == (
        "keep running, but test changes; best run was run 1 "
        "(2024-01-01 to 2024-01-14)")
    beta = campaigns[campaigns["campaign"] == "Beta"].iloc[0]
    # Beta has one run, so best run is its only run.
    assert beta["best_run_number"] == 1
    assert beta["status_now"] == "ended"
    assert beta["action_text"] == "do not restart without changes"


def test_best_run_empty_when_no_volume():
    summary = pd.DataFrame([
        {"campaign": "Gamma", "group": "core", "spend": 10.0,
         "clicks": 10, "conversions": 1.0,
         "last_active_date": "2024-02-14"},
    ])
    empty = pd.DataFrame(columns=["campaign", "label",
                                  "run_number",
                                  "ratio_to_benchmark",
                                  "cost_per_conversion",
                                  "start", "end"])
    campaigns = recommend_campaigns(empty, summary, RULES, CAVEAT)
    gamma = campaigns.iloc[0]
    assert gamma["label"] == "insufficient_data"
    assert pd.isna(gamma["best_run_number"])
    assert pd.isna(gamma["best_run_cost_per_conversion"])
    assert gamma["action_text"] == "not enough data to judge"


def test_each_action_text_case():
    best = {"run_number": 1, "start": "2024-01-01",
            "end": "2024-01-14"}
    assert action_text("continue", "active", False, None, 1) == \
        "keep running"
    assert action_text("continue", "ended", False, None, 1) == \
        "worked well when it ran; candidate to restart"
    assert action_text("test", "active", False, None, 1) == \
        "keep running, but test changes"
    assert action_text("test", "ended", False, None, 1) == \
        "restart only with changes"
    assert action_text("pause_or_review", "active", False, None, 1) == \
        "pause or review"
    assert action_text("pause_or_review", "ended", False, None, 1) == \
        "do not restart without changes"
    assert action_text("insufficient_data", "active", False, None, 1) == \
        "not enough data to judge"
    # Best run is named only when repeat eligible and the best
    # run is not the latest run with enough volume.
    assert action_text("continue", "active", True, best, 2) == \
        "keep running; best run was run 1 (2024-01-01 to 2024-01-14)"
    assert action_text("continue", "active", True, best, 1) == \
        "keep running"
    assert action_text("continue", "active", False, best, 2) == \
        "keep running"


def _sensitivity_for_ratio(ratio):
    runs = pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "run_number": 1,
         "start": "2024-01-01", "end": "2024-01-14",
         "active_days": 14, "spend": 10.0, "clicks": 10,
         "conversions": 10.0, "cost_per_conversion": ratio * 5.0,
         "volume_flag": "ok"},
    ])
    summary = pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "spend": 10.0,
         "clicks": 10, "conversions": 10.0,
         "last_active_date": "2024-01-14"},
    ])
    recs = recommend_runs(runs, 5.0, RULES, VOLUME, CAVEAT)
    return sensitivity_table(recs, summary, RULES)


def test_sensitivity_combinations_and_stability():
    # Ratio 1.2: continue at 1.25 and 1.5, test at 0.75 and 1.0,
    # so the label is not stable.
    unstable = _sensitivity_for_ratio(1.2)
    assert len(unstable) == 12
    assert set(unstable["label"]) == {"continue", "test"}
    assert not unstable["label_stable"].any()
    # Ratio 0.5: continue under every combination -> stable.
    stable_continue = _sensitivity_for_ratio(0.5)
    assert set(stable_continue["label"]) == {"continue"}
    assert stable_continue["label_stable"].all()
    # Ratio 4.0: above every test threshold -> pause -> stable.
    stable_pause = _sensitivity_for_ratio(4.0)
    assert set(stable_pause["label"]) == {"pause_or_review"}
    assert stable_pause["label_stable"].all()
    # Every combination has continue <= test.
    for _, row in unstable.iterrows():
        assert row["continue_max_ratio"] <= row["test_max_ratio"]


def test_sensitivity_insufficient_is_stable():
    empty = pd.DataFrame(columns=["campaign", "label",
                                  "run_number",
                                  "ratio_to_benchmark",
                                  "cost_per_conversion",
                                  "start", "end"])
    summary = pd.DataFrame([
        {"campaign": "Gamma", "group": "core", "spend": 10.0,
         "clicks": 10, "conversions": 1.0,
         "last_active_date": "2024-02-14"},
    ])
    sens = sensitivity_table(empty, summary, RULES)
    assert len(sens) == 12
    assert set(sens["label"]) == {"insufficient_data"}
    assert sens["label_stable"].all()


def test_report_has_no_names(tmp_path):
    recs = recommend_runs(_runs_df(), 5.0, RULES, VOLUME, CAVEAT)
    campaigns = recommend_campaigns(recs, _day_summary(), RULES, CAVEAT)
    sens = sensitivity_table(recs, _day_summary(), RULES)
    report = tmp_path / "recommend-report.md"
    write_recommend_report(report, recs, campaigns, sens, 5.0)
    text = report.read_text()
    assert "Alpha" not in text
    assert "Beta" not in text
    assert "active: 1" in text
    assert "ended: 1" in text
    assert "unstable label: 1" in text
    assert CAVEAT not in text
