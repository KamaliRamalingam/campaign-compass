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
