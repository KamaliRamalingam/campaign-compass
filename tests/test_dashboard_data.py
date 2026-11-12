"""Tests for dashboard/data.py (T8).

All data is tiny and made up, in tmp_path. No real data, no real
campaign names. No test needs streamlit to be installed: only
dashboard/data.py is imported, never dashboard/app.py.
"""

import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import data as dashboard_data  # noqa: E402

CAVEAT = ("Tracked actions only (mainly get-directions requests "
          "and phone calls), not bookings or orders. This shows "
          "campaign performance, not proof that an offer brought "
          "extra customers.")


def _summary_day():
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core",
         "first_active_date": "2026-01-01",
         "last_active_date": "2026-02-14",
         "active_days": 10, "spend": 100.0, "clicks": 100,
         "conversions": 20.0, "cost_per_conversion": 5.0,
         "volume_flag": "ok"},
        {"campaign": "Beta", "group": "core",
         "first_active_date": "2026-01-05",
         "last_active_date": "2026-01-20",
         "active_days": 5, "spend": 210.0, "clicks": 100,
         "conversions": 10.0, "cost_per_conversion": 21.0,
         "volume_flag": "insufficient_data"},
    ])


def _recommendations():
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "label": "continue",
         "status_now": "active", "action_text": "keep running",
         "best_run_number": 1, "best_run_start": "2026-01-01",
         "best_run_end": "2026-01-14",
         "reason": "latest run with enough volume is labelled continue",
         "latest_run_number": 1, "runs_with_volume": 1,
         "repeat_eligible": False},
        {"campaign": "Beta", "group": "core",
         "label": "insufficient_data", "status_now": "ended",
         "action_text": "not enough data to judge",
         "best_run_number": None, "best_run_start": None,
         "best_run_end": None,
         "reason": "no run had enough volume to judge",
         "latest_run_number": None, "runs_with_volume": 0,
         "repeat_eligible": False},
    ])


def _mix():
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core",
         "action_group": "high_intent",
         "action": "Local actions - Directions",
         "conversions": 10.0, "all_conversions": 100.0},
        {"campaign": "Alpha", "group": "core",
         "action_group": "engagement",
         "action": "Local actions - Menu views",
         "conversions": 30.0, "all_conversions": 300.0},
        {"campaign": "Beta", "group": "core",
         "action_group": "high_intent", "action": "Store visits",
         "conversions": 5.0, "all_conversions": 50.0},
    ])


def test_caveat_text_comes_from_config():
    config = {"analysis": {"caveat_text": CAVEAT}}
    assert dashboard_data.caveat_text(config) == CAVEAT


def test_conversion_shares_and_engagement():
    shares = dashboard_data.conversion_shares(_mix())
    # Menu views is the biggest action: 30 of 45 conversions.
    assert shares.iloc[0]["action"] == "Local actions - Menu views"
    assert shares.iloc[0]["share"] == pytest.approx(30.0 / 45.0)
    assert dashboard_data.engagement_share(_mix()) == \
        pytest.approx(30.0 / 45.0)


def test_core_campaigns_table():
    core = dashboard_data.core_campaigns(
        _summary_day(), _recommendations())
    assert list(core["campaign"]) == ["Beta", "Alpha"]
    alpha = core[core["campaign"] == "Alpha"].iloc[0]
    assert alpha["tracked_actions"] == 20.0
    assert alpha["cost_per_tracked_action"] == 5.0
    assert alpha["label"] == "continue"
    assert alpha["action_text"] == "keep running"


def test_comparison_marks_insufficient_and_does_not_rank():
    table = dashboard_data.comparison_data(
        _summary_day(), _recommendations())
    alpha = table[table["campaign"] == "Alpha"].iloc[0]
    beta = table[table["campaign"] == "Beta"].iloc[0]
    assert alpha["rank"] == 1
    assert beta["volume_flag"] == "insufficient_data"
    assert pd.isna(beta["rank"])


def test_runs_for_campaign():
    runs = pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "run_number": 2,
         "start": "2026-02-01", "end": "2026-02-14",
         "active_days": 14, "spend": 100.0, "clicks": 100,
         "conversions": 10.0, "cost_per_conversion": 10.0,
         "volume_flag": "ok"},
        {"campaign": "Alpha", "group": "core", "run_number": 1,
         "start": "2026-01-01", "end": "2026-01-14",
         "active_days": 14, "spend": 50.0, "clicks": 100,
         "conversions": 10.0, "cost_per_conversion": 5.0,
         "volume_flag": "ok"},
    ])
    table = dashboard_data.runs_for_campaign(runs, "Alpha")
    assert list(table["run_number"]) == [1, 2]
    assert table.iloc[0]["cost_per_tracked_action"] == 5.0


def test_weekday_tables_ordered_monday_to_sunday():
    weekday = pd.DataFrame([
        {"weekday": "Friday", "active_days": 1, "spend": 10.0,
         "clicks": 10, "conversions": 2.0,
         "cost_per_conversion": 5.0, "conversion_rate": 0.2,
         "share_of_campaign_conversions": 0.5,
         "volume_flag": "ok"},
        {"weekday": "Monday", "active_days": 1, "spend": 20.0,
         "clicks": 10, "conversions": 4.0,
         "cost_per_conversion": 5.0, "conversion_rate": 0.4,
         "share_of_campaign_conversions": 0.5,
         "volume_flag": "ok"},
    ])
    table = dashboard_data.weekday_core_table(weekday)
    assert list(table["weekday"]) == ["Monday", "Friday"]
    assert table.iloc[0]["tracked_actions"] == 4.0


def test_trend_for_campaign_keeps_source():
    timeline = pd.DataFrame([
        {"campaign": "Alpha", "month": "2025-12", "source": "month",
         "active_days": 1, "spend": 20.0, "clicks": 10,
         "conversions": 5.0, "cost_per_conversion": 4.0,
         "conversion_rate": 0.5},
        {"campaign": "Alpha", "month": "2026-01", "source": "day",
         "active_days": 2, "spend": 30.0, "clicks": 10,
         "conversions": 5.0, "cost_per_conversion": 6.0,
         "conversion_rate": 0.5},
    ])
    table = dashboard_data.trend_for_campaign(timeline, "Alpha")
    assert list(table["month"]) == ["2025-12", "2026-01"]
    assert list(table["source"]) == ["month", "day"]
    assert table.iloc[1]["cost_per_tracked_action"] == 6.0


def test_recommendations_view():
    table = dashboard_data.recommendations_view(_recommendations())
    assert list(table["campaign"]) == ["Alpha", "Beta"]
    assert table.iloc[0]["action_text"] == "keep running"


def test_data_date_range_and_last_updated(tmp_path):
    first, last = dashboard_data.data_date_range(_summary_day())
    assert first == date(2026, 1, 1)
    assert last == date(2026, 2, 14)
    first_file = tmp_path / "a.csv"
    second_file = tmp_path / "b.csv"
    first_file.write_text("a")
    time.sleep(0.01)
    second_file.write_text("b")
    updated = dashboard_data.last_updated([first_file, second_file])
    assert isinstance(updated, datetime)
    assert updated >= datetime.fromtimestamp(
        first_file.stat().st_mtime)


def test_missing_file_raises_clear_error(tmp_path):
    root = tmp_path / "project"
    (root / "outputs" / "results").mkdir(parents=True)
    (root / "config").mkdir()
    config = {"analysis": {
        "caveat_text": CAVEAT,
        "outputs": {
            "recommendations_by_campaign":
                "outputs/results/recommendations_by_campaign.csv",
        },
    }}
    with pytest.raises(FileNotFoundError,
                       match="Run bash run.sh first"):
        dashboard_data.load_tables(config, root=root)


def test_load_tables_reads_all_tables(tmp_path):
    root = tmp_path / "project"
    results = root / "outputs" / "results"
    results.mkdir(parents=True)
    for key, path in dashboard_data.DEFAULT_PATHS.items():
        (results / Path(path).name).write_text("campaign\nAlpha\n")
    config = {"analysis": {"caveat_text": CAVEAT, "outputs": {}}}
    tables = dashboard_data.load_tables(config, root=root)
    assert set(tables) == set(dashboard_data.REQUIRED_TABLES)
    assert list(tables["runs"]["campaign"]) == ["Alpha"]
