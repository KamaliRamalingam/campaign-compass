"""Tests for the break-even visit rate (T12).

All data is tiny and made up. No real data, no real campaign
names.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import break_even  # noqa: E402


def _journey():
    return pd.DataFrame([
        {"campaign": "Alpha", "spend": 100.0, "clicks": 50,
         "cost_per_click": 2.0, "tracked_actions": 10.0,
         "engagement_actions": 40.0, "directions_share": 0.5,
         "calls_share": 0.5, "store_visits_share": 0.0,
         "tracked_actions_per_click": 0.2,
         "engagement_per_tracked_action": 4.0,
         "cost_per_tracked_action": 10.0},
        {"campaign": "Beta", "spend": 300.0, "clicks": 50,
         "cost_per_click": 6.0, "tracked_actions": 10.0,
         "engagement_actions": 40.0, "directions_share": 0.5,
         "calls_share": 0.5, "store_visits_share": 0.0,
         "tracked_actions_per_click": 0.2,
         "engagement_per_tracked_action": 4.0,
         "cost_per_tracked_action": 30.0},
        {"campaign": "core group", "spend": 400.0, "clicks": 100,
         "cost_per_click": 4.0, "tracked_actions": 20.0,
         "engagement_actions": 80.0, "directions_share": 0.5,
         "calls_share": 0.5, "store_visits_share": 0.0,
         "tracked_actions_per_click": 0.2,
         "engagement_per_tracked_action": 4.0,
         "cost_per_tracked_action": 20.0},
    ])


def _what_if_row():
    return {"scenario": "Move 10% of Mon-Fri spend to Sat-Sun",
            "spend_moved": 50.0,
            "tracked_actions_before": 90.0,
            "tracked_actions_after": 95.0,
            "delta": 5.0, "delta_pct": 5.56,
            "note": "upper bound: assumes weekend efficiency "
                    "holds at the moved spend"}


def test_break_even_rate_and_above_one_text():
    table = break_even.break_even_table(_journey(), 20.0)
    # The core-group row is not a campaign and is left out.
    assert list(table["campaign"]) == ["Alpha", "Beta"]
    alpha = table[table["campaign"] == "Alpha"].iloc[0]
    assert alpha["break_even_visit_rate"] == pytest.approx(0.5)
    assert alpha["avg_revenue_per_visit"] == 20.0
    assert "cannot pay for itself" not in alpha["note"]
    assert "illustration: tracked actions are not visits" in \
        alpha["note"]
    beta = table[table["campaign"] == "Beta"].iloc[0]
    assert beta["break_even_visit_rate"] == pytest.approx(1.5)
    assert "cannot pay for itself at this cost" in beta["note"]
    assert "illustration: tracked actions are not visits" in \
        beta["note"]


def test_break_even_rate_exactly_one_is_not_above():
    journey = _journey()
    journey.loc[journey["campaign"] == "Beta",
                "cost_per_tracked_action"] = 20.0
    table = break_even.break_even_table(journey, 20.0)
    beta = table[table["campaign"] == "Beta"].iloc[0]
    assert beta["break_even_visit_rate"] == pytest.approx(1.0)
    assert "cannot pay for itself" not in beta["note"]


def test_journey_report_has_no_campaign_names(tmp_path):
    report = tmp_path / "journey-report.md"
    break_even.write_journey_report(
        report, _journey(), _what_if_row(),
        "2026-01-05", "2026-01-06", skipped=True,
        break_even_rows=pd.DataFrame())
    text = report.read_text()
    assert "Alpha" not in text
    assert "Beta" not in text
    assert "core group" not in text
    assert "Skipped: avg_revenue_per_visit is not set" in text
    assert "Move 10% of Mon-Fri spend to Sat-Sun" in text
    break_even.write_journey_report(
        report, _journey(), _what_if_row(),
        "2026-01-05", "2026-01-06", skipped=False,
        break_even_rows=break_even.break_even_table(
            _journey(), 20.0))
    text = report.read_text()
    assert "Alpha" not in text
    assert "Beta" not in text
    assert "Break-even rows: 2" in text
    assert "Campaigns above 1" in text
    assert "illustration: tracked actions are not visits" in text


def test_journey_report_counts_shares_above_one(tmp_path):
    # A share above 1 means the monthly export counted more
    # conversions than the daily file for that campaign. The
    # report counts such rows instead of hiding them.
    report = tmp_path / "journey-report.md"
    break_even.write_journey_report(
        report, _journey(), _what_if_row(),
        "2026-01-05", "2026-01-06", skipped=True,
        break_even_rows=pd.DataFrame())
    assert ("Journey rows with an intent share above 1: 0"
            in report.read_text())
    journey = _journey()
    journey.loc[journey["campaign"] == "Beta",
                "directions_share"] = 15.8
    break_even.write_journey_report(
        report, journey, _what_if_row(),
        "2026-01-05", "2026-01-06", skipped=True,
        break_even_rows=pd.DataFrame())
    assert ("Journey rows with an intent share above 1: 1"
            in report.read_text())


def _write_inputs(tmp_path, revenue):
    (tmp_path / "outputs" / "results").mkdir(parents=True)
    (tmp_path / "outputs" / "interim").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    _journey().to_csv(
        tmp_path / "outputs" / "results"
        / "journey_by_campaign.csv", index=False)
    pd.DataFrame([_what_if_row()]).to_csv(
        tmp_path / "outputs" / "results"
        / "what_if_weekday_shift.csv", index=False)
    pd.DataFrame([
        {"date": "2026-01-05", "campaign": "Alpha", "cost": 1.0,
         "clicks": 1, "conversions": 1.0},
    ]).to_csv(tmp_path / "outputs" / "interim" / "clean_day.csv",
              index=False)
    revenue_text = "null" if revenue is None else str(revenue)
    (tmp_path / "config" / "test.yaml").write_text(
        "analysis:\n"
        "  break_even:\n"
        f"    avg_revenue_per_visit: {revenue_text}\n"
        "  outputs:\n"
        "    day: outputs/interim/clean_day.csv\n"
        "    journey_by_campaign: outputs/results/journey_by_campaign.csv\n"
        "    what_if_weekday_shift: outputs/results/what_if_weekday_shift.csv\n"
        "    break_even: outputs/results/break_even.csv\n"
        "    journey_report: outputs/reports/journey-report.md\n"
    )
    return tmp_path / "config" / "test.yaml"


def test_main_skips_when_revenue_is_null(tmp_path, capsys,
                                         monkeypatch):
    config = _write_inputs(tmp_path, None)
    # run.sh runs each stage from the project root, so the
    # relative config paths resolve there.
    monkeypatch.chdir(tmp_path)
    # A stale break-even file from an earlier run must go.
    stale = (tmp_path / "outputs" / "results" / "break_even.csv")
    stale.write_text("campaign\nAlpha\n")
    assert break_even.main(["--config", str(config)]) == 0
    assert not stale.is_file()
    report = tmp_path / "outputs" / "reports" / "journey-report.md"
    assert report.is_file()
    assert "Alpha" not in report.read_text()
    out = capsys.readouterr().out
    assert "Break-even skipped" in out
    assert "Alpha" not in out


def test_main_writes_table_when_revenue_is_set(tmp_path,
                                              monkeypatch):
    config = _write_inputs(tmp_path, 20.0)
    monkeypatch.chdir(tmp_path)
    assert break_even.main(["--config", str(config)]) == 0
    table = pd.read_csv(tmp_path / "outputs" / "results"
                        / "break_even.csv")
    assert list(table["campaign"]) == ["Alpha", "Beta"]
    beta = table[table["campaign"] == "Beta"].iloc[0]
    assert beta["break_even_visit_rate"] == pytest.approx(1.5)
