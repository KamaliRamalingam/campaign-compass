"""Tests for PR 2 in the recent-trend stage: idempotent reruns
(M7), trend_overrides (M2), periods in the reasons (M2) and the
run average that excludes the trend windows (S2).

All data is tiny and made up. No real data, no real campaign
names, no real rows from the exports.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import recent_trend
from src.recent_trend import WORSENING_SUFFIX

SETTINGS = {
    "recent_window_days": 28,
    "conversion_lag_days": 3,
    "worsening_ratio": 1.5,
    "improving_ratio": 0.67,
    "worsening_vs_prior_ratio": 1.3,
    "improving_vs_prior_ratio": 0.77,
    "min_tracked_actions_in_window": 30,
}

# Last data date 2026-02-14; lag 3 -> recent window 2026-01-15
# to 2026-02-11, prior window 2025-12-18 to 2026-01-14.
LAST = date(2026, 2, 14)


def _days(campaign, start, count, spend, actions):
    return [{"date": (start + timedelta(days=i)).isoformat(),
             "campaign": campaign, "clicks": 10, "cost": spend,
             "conversions": actions} for i in range(count)]


def _day_df(early_days=0):
    """Alpha: optional early days at 1.00, prior window at 5.00
    per action, recent window at 10.00 per action (worsening)."""
    rows = []
    if early_days:
        rows += _days("Alpha", date(2025, 12, 18)
                      - timedelta(days=early_days), early_days,
                      2.0, 2.0)
    rows += _days("Alpha", date(2025, 12, 18), 28, 10.0, 2.0)
    rows += _days("Alpha", date(2026, 1, 15), 28, 20.0, 2.0)
    rows += _days("Alpha", date(2026, 2, 12), 3, 20.0, 2.0)
    return pd.DataFrame(rows)


def _runs_df(start="2025-12-18"):
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "run_number": 1,
         "start": start, "end": LAST.isoformat(),
         "cost_per_conversion": 7.0, "volume_flag": "ok"},
    ])


def _recs(label="continue", action="keep running"):
    return pd.DataFrame([{
        "campaign": "Alpha", "group": "core", "status_now": "active",
        "label": label, "action_text": action,
        "reason": "made-up reason", "latest_run_number": 1,
        "repeat_eligible": False, "best_run_number": 1,
        "best_run_start": "2025-12-18",
        "best_run_end": LAST.isoformat(),
        "base_label": label, "base_action_text": action,
        "base_reason": "made-up reason",
    }])


def _write_config(tmp_path, settings=None):
    day = tmp_path / "clean_day.csv"
    runs = tmp_path / "runs.csv"
    recs = tmp_path / "recs.csv"
    _day_df().to_csv(day, index=False)
    _runs_df().to_csv(runs, index=False)
    _recs().to_csv(recs, index=False)
    config = {"analysis": {
        "recent_trend": settings or SETTINGS,
        "outputs": {
            "day": str(day), "runs": str(runs),
            "recommendations_by_campaign": str(recs),
            "recent_trend": str(tmp_path / "trend.csv"),
            "weekly_by_campaign": str(tmp_path / "weekly.csv"),
            "recent_trend_report": str(tmp_path / "trend.md"),
        }}}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    return path, recs


# --- M7: idempotent ---------------------------------------------

def test_running_twice_gives_the_same_file(tmp_path):
    path, recs = _write_config(tmp_path)
    assert recent_trend.main(["--config", str(path)]) == 0
    first = recs.read_text()
    assert recent_trend.main(["--config", str(path)]) == 0
    assert recs.read_text() == first
    text = pd.read_csv(recs)["action_text"].iloc[0]
    assert text.count(WORSENING_SUFFIX) == 1


def test_old_file_with_duplicated_suffix_is_cleaned():
    old = _recs().drop(columns=["base_label", "base_action_text",
                                "base_reason"])
    old["action_text"] = "keep running" + WORSENING_SUFFIX * 2
    trend = recent_trend.compute_recent_trend(
        _day_df(), _runs_df(), old, SETTINGS)
    updated = recent_trend.apply_to_recommendations(old, trend)
    assert updated["action_text"].iloc[0] == \
        "keep running" + WORSENING_SUFFIX


def test_recommend_writes_base_columns():
    from src.recommend import recommend_campaigns, recommend_runs
    rules = {"continue_max_ratio": 1.0, "test_max_ratio": 2.0,
             "repeat_min_runs": 2, "active_window_days": 14}
    runs = _runs_df().assign(active_days=59, spend=413.0, clicks=590,
                             conversions=118.0)
    summary = pd.DataFrame([{
        "campaign": "Alpha", "group": "core", "spend": 413.0,
        "clicks": 590, "conversions": 118.0,
        "last_active_date": LAST.isoformat()}])
    run_recs = recommend_runs(runs, 5.0, rules, "caveat")
    recs = recommend_campaigns(run_recs, summary, rules, "caveat")
    for column in ("label", "action_text", "reason"):
        assert (recs[f"base_{column}"] == recs[column]).all()


# --- M2: every reason states its period ------------------------

def test_trend_reason_states_both_windows_and_run_period():
    trend = recent_trend.compute_recent_trend(
        _day_df(), _runs_df(), _recs(), SETTINGS)
    reason = trend["trend_reason"].iloc[0]
    assert "recent window (2026-01-15 to 2026-02-11)" in reason
    assert "prior window (2025-12-18 to 2026-01-14)" in reason
    assert "run 1 average (2025-12-18 to 2026-02-14)" in reason
    assert "28 days" not in reason


def test_recommendation_reasons_state_the_run_period():
    from src.recommend import recommend_campaigns, recommend_runs
    rules = {"continue_max_ratio": 1.0, "test_max_ratio": 2.0,
             "repeat_min_runs": 2, "active_window_days": 14}
    runs = _runs_df().assign(active_days=59, spend=413.0, clicks=590,
                             conversions=118.0)
    summary = pd.DataFrame([{
        "campaign": "Alpha", "group": "core", "spend": 413.0,
        "clicks": 590, "conversions": 118.0,
        "last_active_date": LAST.isoformat()}])
    run_recs = recommend_runs(runs, 5.0, rules, "caveat")
    assert "(2025-12-18 to 2026-02-14)" in run_recs["reason"].iloc[0]
    recs = recommend_campaigns(run_recs, summary, rules, "caveat")
    assert ("latest run with enough volume (run 1, 2025-12-18 to "
            "2026-02-14)") in recs["reason"].iloc[0]
