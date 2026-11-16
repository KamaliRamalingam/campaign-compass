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
    # Menu views is the biggest action: 30 of 45 tracked actions.
    assert shares.iloc[0]["action"] == "Local actions - Menu views"
    assert shares.iloc[0]["tracked_actions"] == 30.0
    assert shares.iloc[0]["share"] == pytest.approx(30.0 / 45.0)
    assert shares.iloc[0]["share_pct"] == pytest.approx(66.67, abs=0.01)
    assert dashboard_data.engagement_share(_mix()) == \
        pytest.approx(30.0 / 45.0)
    # Engagement is 300 of 450 All conv.
    assert dashboard_data.engagement_share_all(_mix()) == \
        pytest.approx(300.0 / 450.0)


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


def _weekday_row(weekday):
    return {"weekday": weekday, "active_days": 1, "spend": 10.0,
            "clicks": 10, "conversions": 2.0,
            "cost_per_conversion": 5.0, "conversion_rate": 0.2,
            "share_of_campaign_conversions": 0.5,
            "volume_flag": "ok"}


def test_weekday_number_accepts_every_format():
    assert dashboard_data.weekday_number("Monday") == 0
    assert dashboard_data.weekday_number("monday") == 0
    assert dashboard_data.weekday_number("MONDAY") == 0
    assert dashboard_data.weekday_number("Mon") == 0
    assert dashboard_data.weekday_number("mon") == 0
    assert dashboard_data.weekday_number("Tue") == 1
    assert dashboard_data.weekday_number("Tues") == 1
    assert dashboard_data.weekday_number("tuesday") == 1
    assert dashboard_data.weekday_number("Wed") == 2
    assert dashboard_data.weekday_number("Thu") == 3
    assert dashboard_data.weekday_number("Thurs") == 3
    assert dashboard_data.weekday_number("Fri") == 4
    assert dashboard_data.weekday_number("Sat") == 5
    assert dashboard_data.weekday_number("Sun") == 6
    assert dashboard_data.weekday_number("sunday") == 6
    assert dashboard_data.weekday_number(0) == 0
    assert dashboard_data.weekday_number(6) == 6
    assert dashboard_data.weekday_number(7) == 6
    assert dashboard_data.weekday_number("3") == 3


def test_weekday_table_accepts_short_names():
    weekday = pd.DataFrame([
        _weekday_row("Fri"),
        _weekday_row("Mon"),
        _weekday_row("sun"),
    ])
    table = dashboard_data.weekday_core_table(weekday)
    assert list(table["weekday"]) == ["Mon", "Fri", "sun"]


def test_weekday_table_accepts_numbers():
    weekday = pd.DataFrame([
        _weekday_row(5),
        _weekday_row(0),
        _weekday_row(7),
    ])
    table = dashboard_data.weekday_core_table(weekday)
    assert list(table["weekday"]) == [0, 5, 7]


def test_weekday_table_unknown_value_lists_only_unknown():
    weekday = pd.DataFrame([
        _weekday_row("Mon"),
        _weekday_row("Funday"),
        _weekday_row("Someday"),
        _weekday_row("Funday"),
    ])
    with pytest.raises(ValueError) as exc_info:
        dashboard_data.weekday_core_table(weekday)
    message = str(exc_info.value)
    assert "Funday" in message
    assert "Someday" in message
    assert "Mon" not in message
    assert "Monday" not in message


def test_weekday_campaign_table_accepts_short_names():
    by_campaign = pd.DataFrame([
        {**_weekday_row("Fri"), "campaign": "Alpha"},
        {**_weekday_row("Mon"), "campaign": "Alpha"},
    ])
    table = dashboard_data.weekday_campaign_table(
        by_campaign, "Alpha")
    assert list(table["weekday"]) == ["Mon", "Fri"]


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


def test_weekly_for_campaign_returns_one_campaign():
    weekly = pd.DataFrame([
        {"campaign": "Alpha", "week_start": "2026-01-12",
         "active_days": 3, "spend": 30.0, "tracked_actions": 6.0,
         "cost_per_tracked_action": 5.0},
        {"campaign": "Alpha", "week_start": "2026-01-05",
         "active_days": 2, "spend": 20.0, "tracked_actions": 4.0,
         "cost_per_tracked_action": 5.0},
        {"campaign": "Beta", "week_start": "2026-01-05",
         "active_days": 1, "spend": 10.0, "tracked_actions": 2.0,
         "cost_per_tracked_action": 5.0},
    ])
    table = dashboard_data.weekly_for_campaign(weekly, "Alpha")
    assert list(table["week_start"]) == ["2026-01-05", "2026-01-12"]
    assert list(table["tracked_actions"]) == [4.0, 6.0]


def test_recommendations_display_hides_group_and_runs():
    recs = _recommendations()
    recs["recent_trend"] = ["worsening", "not_active"]
    recs["ratio_vs_run_average"] = [1.5, None]
    recs["recent_vs_prior_ratio"] = [1.3, None]
    recs["trend_reason"] = [
        "cost per tracked action is 1.30 times the prior 28 days "
        "and 1.50 times the run average", ""]
    table = dashboard_data.recommendations_display(recs)
    assert list(table.columns) == [
        "campaign", "label", "status_now", "recent_trend",
        "ratio_vs_run_average", "recent_vs_prior_ratio",
        "trend_reason", "action_text", "reason"]
    assert list(table["recent_trend"]) == ["worsening", "not_active"]
    assert table.iloc[0]["ratio_vs_run_average"] == 1.5
    assert pd.isna(table.iloc[1]["ratio_vs_run_average"])


def test_recommendations_display_without_recent_trend():
    table = dashboard_data.recommendations_display(
        _recommendations())
    assert list(table["recent_trend"]) == ["", ""]


def test_display_table_renames_only_the_copy(tmp_path):
    original = pd.DataFrame([
        {"campaign": "Alpha", "conversions": 20.0,
         "cost_per_conversion": 5.0, "conversion_rate": 0.2,
         "share_of_campaign_conversions": 50.0,
         "all_conversions": 100.0},
    ])
    display = dashboard_data.display_table(original)
    assert list(display.columns) == [
        "campaign", "tracked actions",
        "cost per tracked action",
        "tracked actions per click (%)",
        "share of campaign tracked actions (%)",
        "all tracked actions"]
    # Rates are percentages with two decimals: 0.2 is 20.00%.
    assert display.iloc[0]["tracked actions per click (%)"] == 20.0
    assert display.iloc[0][
        "share of campaign tracked actions (%)"] == 50.0
    # The input table is unchanged.
    assert list(original.columns) == [
        "campaign", "conversions", "cost_per_conversion",
        "conversion_rate", "share_of_campaign_conversions",
        "all_conversions"]
    assert original.iloc[0]["conversion_rate"] == 0.2
    # Writing the original table to a CSV keeps the file format.
    path = tmp_path / "table.csv"
    original.to_csv(path, index=False)
    header = path.read_text().splitlines()[0]
    assert header == ("campaign,conversions,cost_per_conversion,"
                      "conversion_rate,share_of_campaign_conversions,"
                      "all_conversions")


def test_weekday_display_keeps_tracked_columns():
    # T11b: the Weekday page lost the tracked actions and cost
    # per tracked action columns. They must survive the display
    # renaming, in either order, with no duplicate column name.
    weekday = pd.DataFrame([
        _weekday_row("Mon"),
        _weekday_row("Fri"),
    ])
    display = dashboard_data.display_table(
        dashboard_data.weekday_core_table(weekday))
    assert "tracked actions" in list(display.columns)
    assert "cost per tracked action" in list(display.columns)
    assert len(display.columns) == len(set(display.columns))
    # They come right after the weekday, so they stay visible.
    assert list(display.columns)[:3] == [
        "weekday", "tracked actions", "cost per tracked action"]
    by_campaign = pd.DataFrame([
        {**_weekday_row("Mon"), "campaign": "Alpha"},
        {**_weekday_row("Fri"), "campaign": "Alpha"},
    ])
    display = dashboard_data.display_table(
        dashboard_data.weekday_campaign_table(
            by_campaign, "Alpha"))
    assert "tracked actions" in list(display.columns)
    assert "cost per tracked action" in list(display.columns)
    assert len(display.columns) == len(set(display.columns))


def test_display_table_never_makes_duplicate_names():
    # A table with both conversions and tracked_actions holds
    # the same numbers twice; renaming both would make two
    # columns called "tracked actions", and one would disappear
    # from the dashboard. The duplicate is dropped instead.
    original = pd.DataFrame([
        {"campaign": "Alpha", "conversions": 20.0,
         "tracked_actions": 20.0, "cost_per_conversion": 5.0},
    ])
    display = dashboard_data.display_table(original)
    assert list(display.columns).count("tracked actions") == 1
    assert len(display.columns) == len(set(display.columns))
    assert list(original.columns) == [
        "campaign", "conversions", "tracked_actions",
        "cost_per_conversion"]


def test_format_ratio():
    assert dashboard_data.format_ratio(1.5) == "1.50"
    assert dashboard_data.format_ratio(1.0) == "1.00"
    assert dashboard_data.format_ratio(None) == "—"
    import math
    assert dashboard_data.format_ratio(math.nan) == "—"


def test_share_pct_has_two_decimals():
    shares = dashboard_data.conversion_shares(_mix())
    assert shares.iloc[0]["share_pct"] == pytest.approx(66.67, abs=0.01)
    assert shares.iloc[0]["share_pct"] == round(
        shares.iloc[0]["share_pct"], 2)


def _journey():
    return pd.DataFrame([
        {"campaign": "Alpha", "spend": 100.0, "clicks": 50,
         "cost_per_click": 2.0, "tracked_actions": 10.0,
         "engagement_actions": 40.0, "directions_share": 0.4,
         "calls_share": 0.1, "store_visits_share": 0.0,
         "tracked_actions_per_click": 0.2,
         "engagement_per_tracked_action": 4.0,
         "cost_per_tracked_action": 10.0},
        {"campaign": "core group", "spend": 100.0, "clicks": 50,
         "cost_per_click": 2.0, "tracked_actions": 10.0,
         "engagement_actions": 40.0, "directions_share": 0.4,
         "calls_share": 0.1, "store_visits_share": 0.0,
         "tracked_actions_per_click": 0.2,
         "engagement_per_tracked_action": 4.0,
         "cost_per_tracked_action": 10.0},
    ])


def test_journey_display_shows_shares_as_percentages():
    display = dashboard_data.journey_display(_journey())
    assert display.iloc[0]["directions_share"] == pytest.approx(
        40.0)
    assert display.iloc[0]["calls_share"] == pytest.approx(10.0)
    assert display.iloc[0]["store_visits_share"] == pytest.approx(
        0.0)
    # The input table is unchanged (shares stay fractions).
    assert _journey().iloc[0]["directions_share"] == pytest.approx(
        0.4)


def test_journey_campaigns_excludes_core_group():
    campaigns = dashboard_data.journey_campaigns(_journey())
    assert list(campaigns["campaign"]) == ["Alpha"]


def test_load_break_even_none_when_missing(tmp_path):
    root = tmp_path / "project"
    (root / "outputs" / "results").mkdir(parents=True)
    config = {"analysis": {"caveat_text": CAVEAT, "outputs": {}}}
    assert dashboard_data.load_break_even(
        config, root=root) is None


def test_load_break_even_reads_when_present(tmp_path):
    root = tmp_path / "project"
    results = root / "outputs" / "results"
    results.mkdir(parents=True)
    (results / "break_even.csv").write_text(
        "campaign,break_even_visit_rate\nAlpha,0.5\n")
    config = {"analysis": {"caveat_text": CAVEAT, "outputs": {}}}
    table = dashboard_data.load_break_even(config, root=root)
    assert list(table["campaign"]) == ["Alpha"]
    assert table.iloc[0]["break_even_visit_rate"] == 0.5
