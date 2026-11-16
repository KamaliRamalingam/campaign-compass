"""Tests for PR 2 M3: the lag check (src/lag_check.py).

All data is tiny and made up. No real data, no real campaign
names, no real rows from the exports.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import lag_check, recommend

START = date(2025, 10, 1)
LAST = date(2026, 2, 14)
LOW_FROM = date(2026, 2, 5)

ANALYSIS = {
    "caveat_text": "caveat",
    "volume_rule": {"min_conversions": 10, "min_days_active": 14},
    "recommendation_rules": {
        "continue_max_ratio": 1.0, "test_max_ratio": 2.0,
        "repeat_min_runs": 2, "active_window_days": 14,
    },
    "recent_trend": {
        "recent_window_days": 28, "conversion_lag_days": 3,
        "worsening_ratio": 1.5, "improving_ratio": 0.67,
        "worsening_vs_prior_ratio": 1.3,
        "improving_vs_prior_ratio": 0.77,
        "min_tracked_actions_in_window": 30,
        "trend_overrides": {"worsening": {"continue": "test"}},
        "lag_check_days": [3, 7, 14],
    },
}


def _inputs():
    """Alpha spends 10.00 a day with 2 actions, except the last
    10 days, which have 0 actions so far (reporting lag)."""
    rows = []
    day = START
    while day <= LAST:
        rows.append({"date": day.isoformat(), "campaign": "Alpha",
                     "clicks": 10, "cost": 10.0,
                     "conversions": 0.0 if day >= LOW_FROM else 2.0})
        day += timedelta(days=1)
    day_df = pd.DataFrame(rows)
    spend = float(day_df["cost"].sum())
    conversions = float(day_df["conversions"].sum())
    runs = pd.DataFrame([{
        "campaign": "Alpha", "group": "core", "run_number": 1,
        "start": START.isoformat(), "end": LAST.isoformat(),
        "active_days": len(day_df), "spend": spend,
        "clicks": int(day_df["clicks"].sum()),
        "conversions": conversions,
        "cost_per_conversion": spend / conversions,
        "volume_flag": "ok"}])
    summary = pd.DataFrame([{
        "campaign": "Alpha", "group": "core", "spend": spend,
        "clicks": int(day_df["clicks"].sum()),
        "conversions": conversions,
        "last_active_date": LAST.isoformat()}])
    # The run is 0.50 times a made-up benchmark of twice its cost,
    # so its label is continue.
    run_recs = recommend.recommend_runs(
        runs, 2 * spend / conversions,
        ANALYSIS["recommendation_rules"], "caveat")
    return day_df, runs, run_recs, summary


def _table(analysis=ANALYSIS):
    day_df, runs, run_recs, summary = _inputs()
    # Use a pooled benchmark of twice the campaign's cost so the
    # run label is continue: one campaign in core, so give the
    # summary a second, dearer core campaign.
    summary = pd.concat([summary, pd.DataFrame([{
        "campaign": "Other", "group": "core",
        "spend": 3 * float(summary["spend"].iloc[0]),
        "clicks": 10, "conversions": float(
            summary["conversions"].iloc[0]),
        "last_active_date": "2025-10-01"}])], ignore_index=True)
    return lag_check.lag_check_table(
        day_df, runs, run_recs, summary, analysis,
        analysis["recent_trend"]["lag_check_days"])


def _value(table, lag, measure, value=None):
    part = table.loc[(table["lag"] == lag)
                     & (table["measure"] == measure)]
    if value is not None:
        part = part.loc[part["value"] == value]
    return int(part["campaigns"].sum())


def test_short_lag_reads_undercounted_days_as_worsening():
    table, configured = _table()
    assert configured == 3
    # Lag 3: recent window 2026-01-15 to 2026-02-11 has 7 days
    # with 0 actions: 280 / 42 = 6.67, 1.33 times the prior 5.00.
    assert _value(table, 3, "recent_trend", "worsening") == 1
    # Lag 7: 3 such days: 280 / 50 = 5.60, 1.12 times: stable.
    assert _value(table, 7, "recent_trend", "stable") == 1
    # Lag 14: none: 5.00, 1.00 times: stable.
    assert _value(table, 14, "recent_trend", "stable") == 1


def test_changes_are_counted_against_the_configured_lag():
    table, _ = _table()
    assert _value(table, 3, "recent_trend_changes_total") == 0
    assert _value(table, 3, "label_changes_total") == 0
    assert _value(table, 7, "recent_trend_change",
                  "worsening -> stable") == 1
    assert _value(table, 14, "recent_trend_changes_total") == 1
    # With lag 3 the override turns continue into test; with
    # lag 7 and 14 the trend is stable, so the label stays
    # continue.
    assert _value(table, 3, "label", "test") == 1
    assert _value(table, 7, "label_change", "test -> continue") == 1
    assert _value(table, 14, "label_changes_total") == 1


def test_main_skips_without_lag_check_days(tmp_path, capsys):
    analysis = dict(ANALYSIS)
    analysis["recent_trend"] = {
        k: v for k, v in ANALYSIS["recent_trend"].items()
        if k != "lag_check_days"}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"analysis": analysis}))
    assert lag_check.main(["--config", str(path)]) == 0
    assert "Lag check skipped" in capsys.readouterr().out


def test_main_writes_aggregate_outputs_only(tmp_path, capsys):
    day_df, runs, run_recs, summary = _inputs()
    paths = {}
    for name, frame in (("day", day_df), ("runs", runs),
                        ("recommendations_by_run", run_recs),
                        ("campaign_summary_day", summary)):
        paths[name] = str(tmp_path / f"{name}.csv")
        frame.to_csv(paths[name], index=False)
    paths["lag_check"] = str(tmp_path / "lag.csv")
    paths["lag_check_report"] = str(tmp_path / "lag.md")
    analysis = dict(ANALYSIS, outputs=paths)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"analysis": analysis}))
    assert lag_check.main(["--config", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Configured lag: 3 days (unchanged)" in out
    table = pd.read_csv(tmp_path / "lag.csv")
    assert list(table.columns) == ["lag", "measure", "value",
                                   "campaigns"]
    report = (tmp_path / "lag.md").read_text()
    # Lag 7: the recent window ends 2026-02-14 - 7 = 2026-02-07.
    assert "| 7 | 2026-01-11 to 2026-02-07 |" in report
    for text in (out, report, (tmp_path / "lag.csv").read_text()):
        assert "Alpha" not in text
