"""Tests for src/time_patterns.py (T4).

All data is tiny and made up, in tmp_path. No real data, no real
campaign names, no real rows from the exports.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.time_patterns import (monthly_table, pooled_weekday_table,
                               resolve_run_groups,
                               runs_table, split_runs, timeline_table,
                               weekday_table, write_time_report, main)

GROUPS = {
    "core": ["Alpha"],
    "sep_2026_group": {"exact": ["Super Sales"], "prefix": "The S"},
}
VOLUME = {"min_conversions": 10, "min_days_active": 14}


def _day_df(rows):
    return pd.DataFrame(rows, columns=[
        "date", "campaign", "clicks", "cost", "conversions",
    ])


def test_weekday_assignment_correct():
    # 2024-01-01 is a Monday, 2024-01-02 a Tuesday.
    df = _day_df([
        ("2024-01-01", "Alpha", 10, 10.0, 6.0),
        ("2024-01-02", "Alpha", 10, 10.0, 4.0),
        ("2024-01-08", "Alpha", 10, 10.0, 5.0),  # also Monday
    ])
    table = weekday_table(df, GROUPS, ["core"], 5)
    monday = table[table["weekday"] == "Mon"].iloc[0]
    tuesday = table[table["weekday"] == "Tue"].iloc[0]
    assert monday["active_days"] == 2
    assert monday["conversions"] == 11.0
    assert monday["share_of_campaign_conversions"] == (
        11.0 / 15.0 * 100)
    assert tuesday["active_days"] == 1
    assert tuesday["conversions"] == 4.0
    # Only Monday and Tuesday appear: no rows are invented for
    # weekdays with no activity.
    assert len(table) == 2


def test_active_day_counts_correct_and_no_days_filled():
    df = _day_df([
        ("2024-01-01", "Alpha", 10, 10.0, 6.0),
        ("2024-01-10", "Alpha", 10, 10.0, 6.0),
    ])
    table = weekday_table(df, GROUPS, ["core"], 5)
    # Two active days only; the 8 missing days in between are
    # not filled in as rows.
    assert table["active_days"].sum() == 2
    monthly = monthly_table(df, GROUPS, ["core"])
    assert monthly.iloc[0]["active_days"] == 2


def test_weekday_flags_work_both_ways():
    df = _day_df([
        ("2024-01-01", "Alpha", 10, 10.0, 6.0),  # Mon, 6 >= 5 -> ok
        ("2024-01-02", "Alpha", 10, 10.0, 4.0),  # Tue, 4 < 5 -> flag
    ])
    table = weekday_table(df, GROUPS, ["core"], 5)
    monday = table[table["weekday"] == "Mon"].iloc[0]
    tuesday = table[table["weekday"] == "Tue"].iloc[0]
    assert monday["volume_flag"] == "ok"
    assert tuesday["volume_flag"] == "insufficient_data"


def test_run_gap_20_splits_and_10_does_not():
    # 2024-01-01 -> 2024-01-11 is a 9-day gap (no split);
    # 2024-01-11 -> 2024-02-01 is a 20-day gap (split).
    dates = ["2024-01-01", "2024-01-11", "2024-02-01"]
    runs = split_runs(dates, 14)
    assert len(runs) == 2
    assert runs[0][0] == date(2024, 1, 1)
    assert runs[0][1] == date(2024, 1, 11)
    assert runs[1][0] == date(2024, 2, 1)
    assert runs[1][1] == date(2024, 2, 1)


def test_runs_table_counts_and_flags():
    df = _day_df([
        ("2024-01-01", "Alpha", 10, 10.0, 6.0),
        ("2024-01-02", "Alpha", 10, 10.0, 6.0),
        ("2024-02-01", "Alpha", 10, 10.0, 6.0),
        ("2024-02-02", "Alpha", 10, 10.0, 6.0),
    ])
    table = runs_table(df, GROUPS, ["core"], 14, VOLUME)
    assert len(table) == 2
    assert table["run_number"].tolist() == [1, 2]
    assert table["active_days"].tolist() == [2, 2]
    assert table["conversions"].tolist() == [12.0, 12.0]
    # 12 conversions >= 10 but only 2 active days < 14 -> flagged.
    assert table["volume_flag"].tolist() == [
        "insufficient_data", "insufficient_data"]


def test_runs_include_sep_2026_group():
    df = _day_df([
        ("2024-01-01", "Super Sales", 10, 10.0, 6.0),
        ("2024-01-01", "Other", 10, 10.0, 6.0),
    ])
    # Without analysis.run_groups the default still adds
    # sep_2026_group to the time groups (old behaviour).
    run_groups = resolve_run_groups({"time_groups": ["core"]})
    table = runs_table(df, GROUPS, run_groups, 14, VOLUME)
    assert table["campaign"].tolist() == ["Super Sales"]


def test_timeline_appends_monthly_data_with_right_source():
    day = _day_df([
        ("2024-01-01", "Alpha", 10, 10.0, 6.0),
    ])
    month = _day_df([
        ("2023-08-01", "Alpha", 10, 10.0, 6.0),
        ("2023-09-01", "Alpha", 10, 10.0, 6.0),
    ])
    table = timeline_table(day, month, GROUPS, ["core"])
    assert len(table) == 3
    assert table["source"].tolist() == ["month", "month", "day"]
    assert table["month"].tolist() == ["2023-08", "2023-09", "2024-01"]


def test_report_has_no_names(tmp_path):
    df = _day_df([
        ("2024-01-01", "Alpha", 10, 10.0, 6.0),
    ])
    weekday = weekday_table(df, GROUPS, ["core"], 5)
    runs = runs_table(df, GROUPS, ["core"], 14, VOLUME)
    report = tmp_path / "time-report.md"
    write_time_report(report, [
        ("Weekday rows per campaign", weekday),
        ("Run rows", runs),
    ], runs, 0)
    text = report.read_text()
    assert "Alpha" not in text
    assert "Runs: 1" in text


def test_main_writes_all_tables(tmp_path, capsys):
    day = tmp_path / "clean_day.csv"
    month = tmp_path / "clean_month.csv"
    _day_df([
        ("2024-01-01", "Alpha", 10, 10.0, 6.0),
        ("2024-01-02", "Alpha", 10, 10.0, 4.0),
    ]).to_csv(day, index=False)
    _day_df([
        ("2023-08-01", "Alpha", 10, 10.0, 6.0),
    ]).to_csv(month, index=False)
    config = {
        "analysis": {
            "campaign_groups": GROUPS,
            "volume_rule": VOLUME,
            "time_groups": ["core"],
            "weekday_min_conversions": 5,
            "run_gap_days": 14,
            "outputs": {
                "day": str(day),
                "month": str(month),
                "weekday_by_campaign": str(tmp_path / "weekday.csv"),
                "weekday_core": str(tmp_path / "weekday_core.csv"),
                "monthly_by_campaign": str(tmp_path / "monthly.csv"),
                "timeline_by_campaign": str(tmp_path / "timeline.csv"),
                "runs": str(tmp_path / "runs.csv"),
                "time_report": str(tmp_path / "time-report.md"),
            },
        },
    }
    config_path = tmp_path / "restaurant.yaml"
    config_path.write_text(yaml.safe_dump(config))
    assert main(["--config", str(config_path)]) == 0
    out = capsys.readouterr().out
    assert "Alpha" not in out
    for name in ("weekday.csv", "weekday_core.csv", "monthly.csv",
                 "timeline.csv", "runs.csv", "time-report.md"):
        assert (tmp_path / name).is_file()
