"""Tests for src/metrics.py (T3).

All data is tiny and made up, in tmp_path. No real data, no real
campaign names, no real rows from the exports.
"""

import math
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.metrics import (compute_campaign_metrics,
                         compute_group_summary, compute_monthly_metrics,
                         main, write_metrics_report)

GROUPS = {
    "core": ["Alpha", "Beta"],
    "monthly_history_only": ["Gamma"],
}
VOLUME = {"min_conversions": 10, "min_days_active": 14}


def _day_df():
    return pd.DataFrame([
        {"date": "2024-01-01", "campaign": "Alpha", "clicks": 100,
         "cost": 50.0, "conversions": 10.0, "impressions": 1000},
        {"date": "2024-01-02", "campaign": "Alpha", "clicks": 100,
         "cost": 50.0, "conversions": 10.0, "impressions": 1000},
        {"date": "2024-01-01", "campaign": "Beta", "clicks": 0,
         "cost": 5.0, "conversions": 0.0, "impressions": 0},
    ])


def test_metrics_correct():
    summary = compute_campaign_metrics(_day_df(), GROUPS, VOLUME)
    alpha = summary[summary["campaign"] == "Alpha"].iloc[0]
    assert alpha["group"] == "core"
    assert alpha["spend"] == 100.0
    assert alpha["clicks"] == 200
    assert alpha["conversions"] == 20.0
    assert alpha["active_days"] == 2
    assert alpha["cost_per_conversion"] == 5.0
    assert alpha["conversion_rate"] == 0.1
    assert alpha["ctr"] == 0.1
    assert str(alpha["first_active_date"]) == "2024-01-01"
    assert str(alpha["last_active_date"]) == "2024-01-02"


def test_divide_by_zero_is_empty():
    summary = compute_campaign_metrics(_day_df(), GROUPS, VOLUME)
    beta = summary[summary["campaign"] == "Beta"].iloc[0]
    # Conversions 0 -> cost per conversion empty; clicks 0 ->
    # conversion rate empty; impressions 0 -> ctr empty.
    assert pd.isna(beta["cost_per_conversion"])
    assert pd.isna(beta["conversion_rate"])
    assert pd.isna(beta["ctr"])


def test_volume_flag_works_both_ways():
    # Alpha: 20 conversions but only 2 active days -> insufficient.
    # A campaign with 20 conversions over 14 days -> ok.
    rows = [
        {"date": f"2024-01-{day:02d}", "campaign": "Busy",
         "clicks": 10, "cost": 1.0, "conversions": 2.0,
         "impressions": 100}
        for day in range(1, 15)
    ]
    rows += [
        {"date": "2024-01-01", "campaign": "Small", "clicks": 10,
         "cost": 1.0, "conversions": 1.0, "impressions": 100},
    ]
    df = pd.DataFrame(rows)
    summary = compute_campaign_metrics(
        df, {"core": ["Busy", "Small"]}, VOLUME)
    busy = summary[summary["campaign"] == "Busy"].iloc[0]
    small = summary[summary["campaign"] == "Small"].iloc[0]
    assert busy["volume_flag"] == "ok"
    assert busy["conversions"] == 28.0
    assert busy["active_days"] == 14
    assert small["volume_flag"] == "insufficient_data"


def test_gap_days_are_not_filled():
    # Active on 2024-01-01 and 2024-03-01 only: active_days is 2,
    # not the 60 calendar days in between.
    df = pd.DataFrame([
        {"date": "2024-01-01", "campaign": "Alpha", "clicks": 10,
         "cost": 1.0, "conversions": 5.0},
        {"date": "2024-03-01", "campaign": "Alpha", "clicks": 10,
         "cost": 1.0, "conversions": 5.0},
    ])
    summary = compute_campaign_metrics(df, GROUPS, VOLUME)
    alpha = summary.iloc[0]
    assert alpha["active_days"] == 2
    assert alpha["conversions"] == 10.0


def test_group_summary_shares_add_up_to_100():
    summary = compute_campaign_metrics(_day_df(), GROUPS, VOLUME)
    group_summary = compute_group_summary(summary)
    assert group_summary["share_of_spend"].sum() == pytest.approx(100.0)
    assert group_summary["share_of_conversions"].sum() == pytest.approx(
        100.0)
    core = group_summary[group_summary["group"] == "core"].iloc[0]
    assert core["campaigns"] == 2
    assert core["spend"] == 105.0


def test_monthly_metrics_only_core_and_history():
    month_df = pd.DataFrame([
        {"date": "2023-08-01", "campaign": "Alpha", "clicks": 10,
         "cost": 20.0, "conversions": 5.0},
        {"date": "2023-08-01", "campaign": "Gamma", "clicks": 10,
         "cost": 20.0, "conversions": 5.0},
        {"date": "2023-08-01", "campaign": "Other", "clicks": 10,
         "cost": 20.0, "conversions": 5.0},
    ])
    summary = compute_monthly_metrics(month_df, GROUPS, VOLUME)
    assert summary["campaign"].tolist() == ["Alpha", "Gamma"]
    assert summary["active_months"].tolist() == [1, 1]
    assert "volume_flag" not in summary.columns
    assert "ctr" not in summary.columns


def test_report_has_no_campaign_names(tmp_path):
    summary = compute_campaign_metrics(_day_df(), GROUPS, VOLUME)
    group_summary = compute_group_summary(summary)
    report = tmp_path / "metrics-report.md"
    write_metrics_report(report, summary, group_summary)
    text = report.read_text()
    assert "Alpha" not in text
    assert "Beta" not in text
    assert "insufficient_data" in text
    assert "Campaigns in daily data: 2" in text


def test_main_writes_result_tables(tmp_path):
    day = tmp_path / "clean_day.csv"
    month = tmp_path / "clean_month.csv"
    _day_df().to_csv(day, index=False)
    pd.DataFrame([
        {"date": "2023-08-01", "campaign": "Alpha", "clicks": 10,
         "cost": 20.0, "conversions": 5.0},
    ]).to_csv(month, index=False)
    config = {
        "analysis": {
            "campaign_groups": GROUPS,
            "volume_rule": VOLUME,
            "outputs": {
                "day": str(day),
                "month": str(month),
                "campaign_summary_day": str(tmp_path / "day.csv"),
                "campaign_summary_month": str(tmp_path / "month.csv"),
                "group_summary": str(tmp_path / "group.csv"),
                "metrics_report": str(tmp_path / "metrics-report.md"),
            },
        },
    }
    config_path = tmp_path / "restaurant.yaml"
    config_path.write_text(yaml.safe_dump(config))
    assert main(["--config", str(config_path)]) == 0
    for name in ("day.csv", "month.csv", "group.csv",
                 "metrics-report.md"):
        assert (tmp_path / name).is_file()
    day_summary = pd.read_csv(tmp_path / "day.csv")
    assert len(day_summary) == 2
