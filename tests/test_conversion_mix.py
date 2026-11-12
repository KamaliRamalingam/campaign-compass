"""Tests for src/conversion_mix.py (T10).

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

from src.conversion_mix import (UNMAPPED, assign_action_group,
                                build_action_map, campaign_summary_intent,
                                load_breakdown, main, mix_by_campaign,
                                mix_by_campaign_month, mix_by_run,
                                parse_month, validate_totals,
                                write_conversion_report)

GROUPS = {
    "high_intent": ["Local actions - Directions", "Store visits",
                    "Purchase"],
    "engagement": ["Local actions - Menu views"],
}
ACTION_MAP = build_action_map(GROUPS)


def _table():
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core",
         "month": date(2026, 1, 1),
         "action": "Local actions - Directions",
         "action_group": "high_intent",
         "conversions": 10.0, "all_conversions": 100.0},
        {"campaign": "Alpha", "group": "core",
         "month": date(2026, 1, 1),
         "action": "Local actions - Menu views",
         "action_group": "engagement",
         "conversions": 30.0, "all_conversions": 300.0},
        {"campaign": "Alpha", "group": "core",
         "month": date(2026, 2, 1),
         "action": "Local actions - Directions",
         "action_group": "high_intent",
         "conversions": 5.0, "all_conversions": 50.0},
        {"campaign": "Beta", "group": "core",
         "month": date(2026, 1, 1),
         "action": "Some new action",
         "action_group": UNMAPPED,
         "conversions": 4.0, "all_conversions": 40.0},
    ])


def test_month_formats_parse():
    assert parse_month("June 2009") == date(2009, 6, 1)
    assert parse_month("2024-01-15") == date(2024, 1, 1)
    assert parse_month("2024-01") == date(2024, 1, 1)
    with pytest.raises(ValueError, match="June 2009"):
        parse_month("not a month")


def test_totals_mismatch_gives_fail():
    table = _table()
    expected = {"conversions": 49.0, "all_conversions": 490.0,
                "tolerance": 0.05}
    result = validate_totals(table, expected)
    assert result == {"conversions": "PASS",
                      "all_conversions": "PASS"}
    expected["conversions"] = 50.0
    result = validate_totals(table, expected)
    assert result["conversions"] == "FAIL"
    assert result["all_conversions"] == "PASS"


def test_grouping_ignores_case_and_dash_type():
    assert assign_action_group(
        "local actions - directions", ACTION_MAP) == "high_intent"
    # En dash and em dash count as a hyphen.
    assert assign_action_group(
        "Local actions \u2013 Directions", ACTION_MAP) == "high_intent"
    assert assign_action_group(
        "Local actions \u2014 Directions", ACTION_MAP) == "high_intent"
    assert assign_action_group(
        "STORE VISITS", ACTION_MAP) == "high_intent"


def test_unmapped_actions_are_reported(tmp_path):
    table = _table()
    report = tmp_path / "report.md"
    validation = {"conversions": "PASS", "all_conversions": "PASS"}
    write_conversion_report(report, validation, table, 0)
    text = report.read_text()
    assert "Some new action (unmapped)" in text
    assert "unmapped: 4.00 conversions" in text
    assert "Alpha" not in text
    assert "Beta" not in text


def test_load_breakdown_drops_total_rows_and_names_missing(tmp_path):
    path = tmp_path / "conv.csv"
    path.write_text(
        "Made-up title\n"
        "Made-up range\n"
        "Campaign,Month,Conversion action,Conversions,All conv.\n"
        "Alpha,June 2009,Store visits,2,20\n"
        "Alpha,2024-01-01,Store visits,3,30\n"
        "Total,0,0,0,0\n",
        encoding="utf-8-sig",
    )
    section = {
        "file": {"path": str(path), "title_lines": 2},
        "columns": {"campaign": "Campaign", "month": "Month",
                    "action": "Conversion action",
                    "conversions": "Conversions",
                    "all_conversions": "All conv."},
    }
    table, dropped = load_breakdown(section)
    assert dropped == 1
    assert len(table) == 2
    assert list(table["month"]) == [date(2009, 6, 1),
                                    date(2024, 1, 1)]
    # A missing column fails naming it.
    section["columns"]["action"] = "No such header"
    with pytest.raises(ValueError, match="action"):
        load_breakdown(section)


def test_run_mapping_sets_the_approximate_flag():
    month_mix = mix_by_campaign_month(_table())
    runs = pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "run_number": 1,
         "start": "2026-01-01", "end": "2026-01-31"},
        {"campaign": "Alpha", "group": "core", "run_number": 2,
         "start": "2026-01-15", "end": "2026-02-14"},
    ])
    run_mix = mix_by_run(month_mix, runs)
    whole = run_mix[run_mix["run_number"] == 1]
    assert not whole.empty
    assert bool(whole["approximate"].iloc[0]) is False
    # Run 1 touches January only: 10 high intent, 30 engagement.
    by_group = whole.set_index("action_group")
    assert by_group.loc["high_intent", "conversions"] == 10.0
    assert by_group.loc["engagement", "conversions"] == 30.0
    partial = run_mix[run_mix["run_number"] == 2]
    assert bool(partial["approximate"].iloc[0]) is True
    # Run 2 touches January and February: 15 high intent.
    by_group = partial.set_index("action_group")
    assert by_group.loc["high_intent", "conversions"] == 15.0


def test_cost_per_high_intent_conversion_is_correct():
    clean_day = pd.DataFrame([
        {"campaign": "Alpha", "cost": 150.0, "conversions": 45.0},
        {"campaign": "Beta", "cost": 40.0, "conversions": 4.0},
    ])
    intent = campaign_summary_intent(
        clean_day, _table(), date(2026, 1, 13), date(2026, 2, 12))
    alpha = intent[intent["campaign"] == "Alpha"].iloc[0]
    # Daily range touches Jan and Feb 2026: high intent 15.0.
    assert alpha["spend"] == 150.0
    assert alpha["high_intent_conversions"] == 15.0
    assert alpha["engagement_conversions"] == 30.0
    assert alpha["share_high_intent"] == pytest.approx(15.0 / 45.0)
    assert alpha["cost_per_high_intent_conversion"] == 10.0
    beta = intent[intent["campaign"] == "Beta"].iloc[0]
    assert beta["high_intent_conversions"] == 0.0
    assert pd.isna(beta["cost_per_high_intent_conversion"])


def test_mix_by_campaign_shares():
    mixed = mix_by_campaign(_table())
    alpha = mixed[mixed["campaign"] == "Alpha"]
    directions = alpha[alpha["action"] == "Local actions - Directions"]
    # High intent is 15 of Alpha's 45 conversions.
    assert directions["group_conversions"].iloc[0] == 15.0
    assert directions["share_group_conversions"].iloc[0] == \
        pytest.approx(15.0 / 45.0)


def test_main_writes_outputs(tmp_path, capsys):
    conv = tmp_path / "conv.csv"
    conv.write_text(
        "Made-up title\n"
        "Made-up range\n"
        "Campaign,Month,Conversion action,Conversions,All conv.\n"
        "Alpha,January 2026,Store visits,2,20\n"
        "Alpha,February 2026,Local actions - Menu views,3,30\n"
        "Total,0,0,0,0\n",
        encoding="utf-8-sig",
    )
    runs = tmp_path / "runs.csv"
    pd.DataFrame([
        {"campaign": "Alpha", "group": "core", "run_number": 1,
         "start": "2026-01-01", "end": "2026-02-28"},
    ]).to_csv(runs, index=False)
    clean_day = tmp_path / "clean_day.csv"
    pd.DataFrame([
        {"campaign": "Alpha", "cost": 50.0, "conversions": 5.0},
    ]).to_csv(clean_day, index=False)
    config = {
        "analysis": {
            "daily_start": "2026-01-01",
            "daily_end": "2026-02-28",
            "campaign_groups": {"core": ["Alpha"]},
            "outputs": {"runs": str(runs),
                        "day": str(clean_day)},
        },
        "conversion_breakdown": {
            "file": {"path": str(conv), "title_lines": 2},
            "columns": {"campaign": "Campaign", "month": "Month",
                        "action": "Conversion action",
                        "conversions": "Conversions",
                        "all_conversions": "All conv."},
            "ui_expected": {"conversions": 5.0,
                            "all_conversions": 50.0,
                            "tolerance": 0.05},
            "action_groups": GROUPS,
            "outputs": {
                "mix_by_campaign": str(tmp_path / "mix.csv"),
                "mix_by_campaign_month": str(tmp_path / "mix_month.csv"),
                "mix_by_run": str(tmp_path / "mix_run.csv"),
                "campaign_summary_intent": str(tmp_path / "intent.csv"),
                "report": str(tmp_path / "report.md"),
            },
        },
    }
    config_path = tmp_path / "restaurant.yaml"
    config_path.write_text(yaml.safe_dump(config))
    assert main(["--config", str(config_path)]) == 0
    out = capsys.readouterr().out
    assert "Conversion breakdown: PASS" in out
    assert "Alpha" not in out
    for name in ("mix.csv", "mix_month.csv", "mix_run.csv",
                 "intent.csv", "report.md"):
        assert (tmp_path / name).is_file()
    intent = pd.read_csv(tmp_path / "intent.csv")
    assert intent["cost_per_high_intent_conversion"].iloc[0] == 25.0
