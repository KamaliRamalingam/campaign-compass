"""Tests for src/overview.py (T3a).

All data is tiny and made up, in tmp_path. No real data, no real
campaign names, no real rows from the exports.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.overview import build_overview, main


def _day_df():
    return pd.DataFrame([
        {"date": "2024-01-01", "campaign": "Alpha", "clicks": 6,
         "cost": 12.0, "conversions": 2.0},
        {"date": "2024-01-02", "campaign": "Alpha", "clicks": 4,
         "cost": 8.0, "conversions": 2.0},
        {"date": "2024-01-01", "campaign": "Beta", "clicks": 1,
         "cost": 1.0, "conversions": 0.0},
    ])


def _month_df():
    return pd.DataFrame([
        {"date": "2023-08-01", "campaign": "Alpha", "clicks": 10,
         "cost": 20.0, "conversions": 5.0},
        {"date": "2023-09-01", "campaign": "Alpha", "clicks": 5,
         "cost": 10.0, "conversions": 1.0},
        {"date": "2023-08-01", "campaign": "Gamma", "clicks": 3,
         "cost": 6.0, "conversions": 1.0},
    ])


def test_one_row_per_campaign_with_correct_totals():
    overview = build_overview(_day_df(), _month_df())
    assert len(overview) == 3
    assert list(overview.columns) == [
        "campaign", "first_active_date", "last_active_date",
        "active_days", "active_months", "total_clicks", "total_cost",
        "total_conversions", "monthly_total_cost",
        "monthly_total_conversions",
    ]
    alpha = overview[overview["campaign"] == "Alpha"].iloc[0]
    assert alpha["first_active_date"] == date(2024, 1, 1)
    assert alpha["last_active_date"] == date(2024, 1, 2)
    assert alpha["active_days"] == 2
    assert alpha["active_months"] == 2
    assert alpha["total_clicks"] == 10
    assert alpha["total_cost"] == 20.0
    assert alpha["total_conversions"] == 4.0
    assert alpha["monthly_total_cost"] == 30.0
    assert alpha["monthly_total_conversions"] == 6.0
    beta = overview[overview["campaign"] == "Beta"].iloc[0]
    assert beta["active_days"] == 1
    assert beta["active_months"] == 0
    assert beta["monthly_total_cost"] == 0
    gamma = overview[overview["campaign"] == "Gamma"].iloc[0]
    assert gamma["active_days"] == 0
    assert gamma["active_months"] == 1
    # Gamma has no daily data, so its dates come from monthly data.
    assert gamma["first_active_date"] == date(2023, 8, 1)
    assert gamma["last_active_date"] == date(2023, 8, 1)


def test_include_list_filters_correctly():
    overview = build_overview(_day_df(), _month_df(),
                              include=["Alpha"])
    assert overview["campaign"].tolist() == ["Alpha"]


def test_exclude_list_filters_correctly():
    overview = build_overview(_day_df(), _month_df(),
                              exclude=["Beta", "Gamma"])
    assert overview["campaign"].tolist() == ["Alpha"]


def test_include_then_exclude():
    overview = build_overview(_day_df(), _month_df(),
                              include=["Alpha", "Beta"],
                              exclude=["Beta"])
    assert overview["campaign"].tolist() == ["Alpha"]


def test_empty_lists_keep_everything():
    overview = build_overview(_day_df(), _month_df(),
                              include=[], exclude=[])
    assert len(overview) == 3


def test_main_writes_overview_and_prints_no_names(tmp_path, capsys):
    day = tmp_path / "clean_day.csv"
    month = tmp_path / "clean_month.csv"
    _day_df().to_csv(day, index=False)
    _month_df().to_csv(month, index=False)
    config = {
        "input": {"files": {"day": {"output": "unused"},
                            "month": {"output": "unused"}}},
        "analysis": {
            "include_campaigns": [],
            "exclude_campaigns": [],
            "outputs": {
                "day": str(day),
                "month": str(month),
                "overview": str(tmp_path / "campaign-overview.csv"),
            },
        },
    }
    config_path = tmp_path / "restaurant.yaml"
    config_path.write_text(yaml.safe_dump(config))
    assert main(["--config", str(config_path)]) == 0
    out = capsys.readouterr().out
    assert "campaigns: 3" in out
    assert "Alpha" not in out
    assert "Beta" not in out
    assert "Gamma" not in out
    written = pd.read_csv(tmp_path / "campaign-overview.csv")
    assert len(written) == 3
