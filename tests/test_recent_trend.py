"""Tests for the recent trend and weekly tables (T11).

All data is tiny and made up. No real data. No streamlit.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recent_trend import (  # noqa: E402
    TREND_INSUFFICIENT,
    TREND_STABLE,
    WORSENING_SUFFIX,
    apply_to_recommendations,
    compute_recent_trend,
    current_run_average,
    weekly_table,
    window_bounds,
)

SETTINGS = {
    "recent_window_days": 28,
    "conversion_lag_days": 3,
    "worsening_ratio": 1.5,
    "improving_ratio": 0.67,
    "worsening_vs_prior_ratio": 1.3,
    "improving_vs_prior_ratio": 0.77,
    "min_tracked_actions_in_window": 30,
}


def _day_rows(campaign, start, days, spend_per_day,
              actions_per_day):
    """One row per day for a campaign, made-up numbers."""
    rows = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        rows.append({
            "date": day.isoformat(),
            "campaign": campaign,
            "cost": spend_per_day,
            "clicks": 10,
            "conversions": actions_per_day,
        })
    return rows


def _setup(recent_actions=40, recent_spend=200.0,
           prior_actions=40, prior_spend=200.0, run_average=5.0):
    """Made-up data with last data date 2026-02-14.

    Recent window 2026-01-15 to 2026-02-11, prior window
    2025-12-18 to 2026-01-14. Alpha is active, Beta ended.
    """
    rows = _day_rows("Alpha", date(2025, 12, 18), 28,
                     prior_spend / 28, prior_actions / 28)
    rows += _day_rows("Alpha", date(2026, 1, 15), 28,
                      recent_spend / 28, recent_actions / 28)
    # Three more days at the recent rate, so the last data date
    # is 2026-02-14 (the lag then ends the recent window on
    # 2026-02-11). These days fall outside both windows.
    rows += _day_rows("Alpha", date(2026, 2, 12), 3,
                      recent_spend / 28, recent_actions / 28)
    day_df = pd.DataFrame(rows)
    runs_df = pd.DataFrame([
        {"campaign": "Alpha", "run_number": 1,
         "start": "2025-12-18", "end": "2026-02-14",
         "cost_per_conversion": run_average},
        {"campaign": "Beta", "run_number": 1,
         "start": "2025-12-18", "end": "2026-02-14",
         "cost_per_conversion": 4.0},
    ])
    recommendations = pd.DataFrame([
        {"campaign": "Alpha", "group": "core",
         "status_now": "active", "action_text": "keep running"},
        {"campaign": "Beta", "group": "core",
         "status_now": "ended", "action_text": "pause or review"},
    ])
    return day_df, runs_df, recommendations


def test_window_bounds_apply_the_lag():
    recent_start, recent_end, prior_start, prior_end = \
        window_bounds(date(2026, 2, 14), 28, 3)
    # Last data date minus 3 lag days ends the recent window.
    assert recent_end == date(2026, 2, 11)
    assert recent_start == date(2026, 1, 15)
    assert prior_end == date(2026, 1, 14)
    assert prior_start == date(2025, 12, 18)


def test_recent_trend_stable_when_ratio_is_one():
    day_df, runs_df, recs = _setup()
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    assert len(table) == 1  # only the active campaign
    row = table.iloc[0]
    assert row["campaign"] == "Alpha"
    assert row["recent_tracked_actions"] == pytest.approx(40.0)
    assert row["prior_tracked_actions"] == pytest.approx(40.0)
    assert row["recent_cost_per_tracked_action"] == pytest.approx(5.0)
    assert row["prior_cost_per_tracked_action"] == pytest.approx(5.0)
    assert row["ratio_vs_run_average"] == pytest.approx(1.0)
    assert row["recent_trend"] == TREND_STABLE


def test_recent_trend_worsening_at_the_threshold():
    # Recent cost 7.50 is 1.50 times the run average 5.00.
    day_df, runs_df, recs = _setup(recent_spend=300.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    assert table.iloc[0]["recent_trend"] == "worsening"
    assert table.iloc[0]["ratio_vs_run_average"] == pytest.approx(1.5)


def test_recent_trend_improving_at_the_threshold():
    # Recent cost 3.35 is 0.67 times the run average 5.00.
    day_df, runs_df, recs = _setup(recent_spend=134.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    assert table.iloc[0]["recent_trend"] == "improving"
    assert table.iloc[0]["ratio_vs_run_average"] == pytest.approx(0.67)


def test_recent_trend_insufficient_when_a_window_is_small():
    # Recent window has 20 tracked actions, below the minimum 30.
    day_df, runs_df, recs = _setup(recent_actions=20)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    assert table.iloc[0]["recent_trend"] == TREND_INSUFFICIENT
    # Prior window too small is also insufficient.
    day_df, runs_df, recs = _setup(prior_actions=20)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    assert table.iloc[0]["recent_trend"] == TREND_INSUFFICIENT


def test_recent_trend_worsening_by_prior_only():
    # Recent cost 6.50 is 1.30 times the prior window but only
    # 1.30 times the run average, so the prior rule fires.
    day_df, runs_df, recs = _setup(recent_spend=260.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == "worsening"
    assert row["recent_vs_prior_ratio"] == pytest.approx(1.3)
    assert row["ratio_vs_run_average"] == pytest.approx(1.3)
    assert row["trend_reason"] == (
        "cost per tracked action in the recent window (2026-01-15 to 2026-02-11) is "
        "1.30 times the prior window (2025-12-18 to 2026-01-14) "
        "and 1.30 times the run 1 average (2025-12-18 to 2026-02-14)")


def test_recent_trend_worsening_by_run_average_only():
    # Recent cost 7.50 is 1.50 times the run average but only
    # 1.25 times the prior window, so the run rule fires.
    day_df, runs_df, recs = _setup(
        recent_spend=300.0, prior_spend=240.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == "worsening"
    assert row["recent_vs_prior_ratio"] == pytest.approx(1.25)
    assert row["ratio_vs_run_average"] == pytest.approx(1.5)


def test_recent_trend_worsening_by_both():
    day_df, runs_df, recs = _setup(recent_spend=300.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == "worsening"
    assert row["recent_vs_prior_ratio"] == pytest.approx(1.5)
    assert row["ratio_vs_run_average"] == pytest.approx(1.5)


def test_recent_trend_worsening_wins_over_improving():
    # Prior ratio 1.30 is worsening, run ratio 0.65 is
    # improving; worsening wins.
    day_df, runs_df, recs = _setup(
        recent_spend=260.0, run_average=10.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == "worsening"
    assert row["recent_vs_prior_ratio"] == pytest.approx(1.3)
    assert row["ratio_vs_run_average"] == pytest.approx(0.65)


def test_recent_trend_improving_by_prior_only():
    # Recent cost 3.85 is 0.77 times the prior window but 0.77
    # times the run average, so the prior rule fires.
    day_df, runs_df, recs = _setup(recent_spend=154.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == "improving"
    assert row["recent_vs_prior_ratio"] == pytest.approx(0.77)
    assert row["ratio_vs_run_average"] == pytest.approx(0.77)


def test_recent_trend_improving_by_run_average_only():
    # Recent cost 3.35 is 0.67 times the run average but 0.84
    # times the prior window, so the run rule fires.
    day_df, runs_df, recs = _setup(
        recent_spend=134.0, prior_spend=160.0)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == "improving"
    assert row["recent_vs_prior_ratio"] == pytest.approx(0.84, abs=0.01)
    assert row["ratio_vs_run_average"] == pytest.approx(0.67)


def test_recent_trend_example_from_the_task():
    # 1.52 times the prior 28 days and 1.34 times the run
    # average gives worsening, with that exact reason.
    day_df, runs_df, recs = _setup(
        recent_spend=268.0, prior_spend=176.4)
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == "worsening"
    assert row["recent_vs_prior_ratio"] == pytest.approx(1.52, abs=0.01)
    assert row["ratio_vs_run_average"] == pytest.approx(1.34)
    assert row["trend_reason"] == (
        "cost per tracked action in the recent window (2026-01-15 to 2026-02-11) is "
        "1.52 times the prior window (2025-12-18 to 2026-01-14) "
        "and 1.34 times the run 1 average (2025-12-18 to 2026-02-14)")


def test_recent_trend_prior_window_empty():
    # No rows in the prior window: the prior ratio is empty
    # and the trend is insufficient_data.
    rows = _day_rows("Alpha", date(2026, 1, 15), 28,
                     200.0 / 28, 40.0 / 28)
    rows += _day_rows("Alpha", date(2026, 2, 12), 3,
                      200.0 / 28, 40.0 / 28)
    day_df = pd.DataFrame(rows)
    runs_df = pd.DataFrame([
        {"campaign": "Alpha", "run_number": 1,
         "start": "2026-01-15", "end": "2026-02-14",
         "cost_per_conversion": 5.0},
    ])
    recommendations = pd.DataFrame([
        {"campaign": "Alpha", "group": "core",
         "status_now": "active", "action_text": "keep running"},
    ])
    table = compute_recent_trend(
        day_df, runs_df, recommendations, SETTINGS)
    row = table.iloc[0]
    assert row["prior_tracked_actions"] == 0.0
    assert pd.isna(row["recent_vs_prior_ratio"])
    assert row["recent_trend"] == TREND_INSUFFICIENT
    assert "not enough data" in row["trend_reason"]


def test_recent_trend_without_a_current_run_uses_prior_only():
    # No run average: the prior window alone decides. Here the
    # prior ratio is 1.00, so the trend is stable.
    day_df, runs_df, recs = _setup()
    runs_df = runs_df.loc[runs_df["campaign"] == "Beta"]
    table = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    row = table.iloc[0]
    assert row["recent_trend"] == TREND_STABLE
    assert pd.isna(row["ratio_vs_run_average"])
    assert row["recent_vs_prior_ratio"] == pytest.approx(1.0)
    assert row["trend_reason"] == (
        "cost per tracked action in the recent window (2026-01-15 to 2026-02-11) is "
        "1.00 times the prior window (2025-12-18 to 2026-01-14)")


def test_current_run_average_uses_the_latest_run():
    runs_df = pd.DataFrame([
        {"campaign": "Alpha", "run_number": 1,
         "start": "2026-01-01", "end": "2026-01-14",
         "cost_per_conversion": 9.0},
        {"campaign": "Alpha", "run_number": 2,
         "start": "2026-02-01", "end": "2026-02-14",
         "cost_per_conversion": 5.0},
    ])
    assert current_run_average(runs_df, "Alpha") == 5.0
    assert current_run_average(runs_df, "Nobody") is None


def test_weekly_table_starts_weeks_on_monday():
    day_df = pd.DataFrame([
        {"date": "2026-01-07", "campaign": "Alpha", "cost": 10.0,
         "clicks": 10, "conversions": 2.0},
        {"date": "2026-01-08", "campaign": "Alpha", "cost": 20.0,
         "clicks": 10, "conversions": 4.0},
        {"date": "2026-01-12", "campaign": "Alpha", "cost": 30.0,
         "clicks": 10, "conversions": 6.0},
    ])
    table = weekly_table(day_df)
    # 2026-01-07 is a Wednesday, 2026-01-12 is a Monday.
    assert list(table["week_start"].astype(str)) == [
        "2026-01-05", "2026-01-12"]
    assert list(table["active_days"]) == [2, 1]
    assert list(table["tracked_actions"]) == [6.0, 6.0]
    assert list(table["cost_per_tracked_action"]) == [
        pytest.approx(5.0), pytest.approx(5.0)]


def test_action_text_suffix_only_when_worsening():
    day_df, runs_df, recs = _setup(recent_spend=300.0)
    trend = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    updated = apply_to_recommendations(recs, trend)
    alpha = updated.loc[updated["campaign"] == "Alpha"].iloc[0]
    assert alpha["recent_trend"] == "worsening"
    assert alpha["action_text"].endswith(WORSENING_SUFFIX)
    beta = updated.loc[updated["campaign"] == "Beta"].iloc[0]
    assert beta["recent_trend"] == "not_active"
    assert WORSENING_SUFFIX not in beta["action_text"]

    day_df, runs_df, recs = _setup()
    trend = compute_recent_trend(day_df, runs_df, recs, SETTINGS)
    updated = apply_to_recommendations(recs, trend)
    alpha = updated.loc[updated["campaign"] == "Alpha"].iloc[0]
    assert alpha["recent_trend"] == TREND_STABLE
    assert alpha["action_text"] == "keep running"
    assert alpha["ratio_vs_run_average"] == pytest.approx(1.0)
