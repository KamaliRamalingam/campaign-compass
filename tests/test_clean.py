"""Tests for src/clean.py (T2).

All data is tiny and made up, in tmp_path. No real data, no real
campaign names, no real rows from the exports.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.clean import clean_day, clean_month, detect_gaps, main

DAILY_START = "2023-10-13"
DAILY_END = "2026-11-12"
MONTHLY_END = "2023-09-30"


def _day_df(rows):
    return pd.DataFrame(rows, columns=[
        "date", "campaign", "clicks", "cost", "conversions",
    ])


def test_range_filter_works():
    df = _day_df([
        ("2023-10-12", "Alpha", 1, 1.0, 1.0),   # before daily_start
        ("2023-10-13", "Alpha", 2, 2.0, 1.0),   # first day in range
        ("2026-11-12", "Alpha", 3, 3.0, 1.0),   # last day in range
        ("2026-11-13", "Alpha", 4, 4.0, 1.0),   # after daily_end
    ])
    cleaned, stats = clean_day(df, DAILY_START, DAILY_END)
    assert stats["rows_before"] == 4
    assert stats["rows_outside_range"] == 2
    assert stats["rows_after"] == 2
    assert cleaned["date"].tolist() == [date(2023, 10, 13),
                                        date(2026, 11, 12)]


def test_monthly_end_filter_works():
    df = _day_df([
        ("2023-09-01", "Alpha", 1, 1.0, 1.0),
        ("2023-10-01", "Alpha", 2, 2.0, 1.0),
    ])
    cleaned, stats = clean_month(df, MONTHLY_END)
    assert stats["rows_outside_range"] == 1
    assert stats["rows_after"] == 1


def test_duplicates_removed_and_counted():
    df = _day_df([
        ("2024-01-01", "Alpha", 6, 12.0, 2.0),
        ("2024-01-01", "Alpha", 6, 12.0, 2.0),   # exact duplicate
        ("2024-01-01", "Beta", 1, 1.0, 0.0),     # same date, other campaign
        ("2024-01-02", "Alpha", 4, 8.0, 2.0),
    ])
    cleaned, stats = clean_day(df, DAILY_START, DAILY_END)
    assert stats["duplicates_removed"] == 1
    assert stats["rows_after"] == 3
    # First copy kept, in order.
    assert cleaned["clicks"].tolist() == [6, 1, 4]


def test_flags_counted_and_rows_kept():
    df = _day_df([
        ("2024-01-01", "Alpha", 6, 12.0, 2.0),    # clean
        ("2024-01-02", "Alpha", -1, 8.0, 2.0),    # negative clicks
        ("2024-01-03", "Alpha", 2, -5.0, 2.0),    # negative cost
        ("2024-01-04", "Alpha", 2, 8.0, 5.0),     # conversions > clicks
        ("2024-01-05", "Alpha", None, 8.0, 1.0),  # missing clicks
    ])
    cleaned, stats = clean_day(df, DAILY_START, DAILY_END)
    assert stats["flagged_rows"] == 4
    assert stats["rows_after"] == 5  # flagged rows are kept, not deleted
    assert cleaned["flags"].tolist()[0] == ""
    assert "negative_clicks" in cleaned["flags"].tolist()[1]
    assert "negative_cost" in cleaned["flags"].tolist()[2]
    assert "conversions_gt_clicks" in cleaned["flags"].tolist()[3]
    assert "missing_clicks" in cleaned["flags"].tolist()[4]


def test_per_campaign_activity_columns():
    df = _day_df([
        ("2024-01-01", "Alpha", 6, 12.0, 2.0),
        ("2024-01-03", "Alpha", 4, 8.0, 2.0),
        ("2024-01-02", "Beta", 1, 1.0, 0.0),
    ])
    cleaned, stats = clean_day(df, DAILY_START, DAILY_END)
    alpha = cleaned[cleaned["campaign"] == "Alpha"]
    assert alpha["active_days"].tolist() == [2, 2]
    assert alpha["first_active_date"].tolist() == [
        date(2024, 1, 1), date(2024, 1, 1)]
    assert alpha["last_active_date"].tolist() == [
        date(2024, 1, 3), date(2024, 1, 3)]
    assert stats["first_active_date"] == date(2024, 1, 1)
    assert stats["last_active_date"] == date(2024, 1, 3)


def test_gap_detection_finds_40_day_gap_and_ignores_10_day_gap():
    dates = ["2024-01-01", "2024-01-11", "2024-02-21"]
    gaps = detect_gaps(dates)
    # 2024-01-01 -> 2024-01-11 is a 9-day gap (ignored);
    # 2024-01-11 -> 2024-02-21 is a 40-day gap.
    assert len(gaps) == 1
    start, end, days = gaps[0]
    assert start == date(2024, 1, 12)
    assert end == date(2024, 2, 20)
    assert days == 40


def test_gap_detection_no_gaps():
    assert detect_gaps(["2024-01-01", "2024-01-02", "2024-01-03"]) == []


def test_main_writes_report_with_no_campaign_names(tmp_path):
    # Tiny made-up interim tables, as T1 would write them.
    day = tmp_path / "day.csv"
    month = tmp_path / "month.csv"
    day.write_text(
        "date,campaign,clicks,cost,conversions\n"
        "2024-01-01,Alpha,6,12.0,2.0\n"
        "2024-01-01,Alpha,6,12.0,2.0\n"
        "2024-03-01,Beta,1,1.0,0.0\n"
    )
    month.write_text(
        "date,campaign,clicks,cost,conversions\n"
        "2023-08-01,Alpha,10,20.0,5.0\n"
        "2023-10-01,Alpha,10,20.0,5.0\n"
    )
    config = {
        "input": {
            "files": {
                "day": {"output": str(day)},
                "month": {"output": str(month)},
            },
        },
        "analysis": {
            "daily_start": DAILY_START,
            "daily_end": DAILY_END,
            "monthly_end": MONTHLY_END,
            "outputs": {
                "day": str(tmp_path / "clean_day.csv"),
                "month": str(tmp_path / "clean_month.csv"),
                "report": str(tmp_path / "cleaning-report.md"),
            },
        },
    }
    config_path = tmp_path / "restaurant.yaml"
    config_path.write_text(yaml.safe_dump(config))
    assert main(["--config", str(config_path)]) == 0
    report = (tmp_path / "cleaning-report.md").read_text()
    assert "Alpha" not in report
    assert "Beta" not in report
    assert "Rows before: 3" in report
    assert "Duplicates removed: 1" in report
    assert (tmp_path / "clean_day.csv").is_file()
    assert (tmp_path / "clean_month.csv").is_file()
