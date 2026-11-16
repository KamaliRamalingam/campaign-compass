"""Tests for PR 2 M2: the recent-window label for active
campaigns (recommendation_rules.recent_label).

All data is tiny and made up. No real data, no real campaign
names, no real rows from the exports.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import recommend

RULES = {
    "continue_max_ratio": 1.0,
    "test_max_ratio": 2.0,
    "repeat_min_runs": 2,
    "active_window_days": 14,
    "sensitivity_continue_max_ratio": [0.75, 1.0, 1.25, 1.5],
    "sensitivity_test_max_ratio": [1.5, 2.0, 3.0],
}
VOLUME = {"min_conversions": 10, "min_days_active": 14}


def _days(campaign, start, count, spend, conversions):
    return [{"date": (start + timedelta(days=i)).isoformat(),
             "campaign": campaign, "clicks": 10, "cost": spend,
             "conversions": conversions} for i in range(count)]


def _day_df():
    """Alpha (active): 61 days at 5.00 per conversion, then 30
    days at 15.00. Beta (ended): 31 days at 15.00 in January.
    Pmax (active, core_pmax): 91 days at 30.00."""
    rows = _days("Alpha", date(2024, 1, 1), 61, 5.0, 1.0)
    rows += _days("Alpha", date(2024, 3, 2), 30, 15.0, 1.0)
    rows += _days("Beta", date(2024, 1, 1), 31, 15.0, 1.0)
    rows += _days("Pmax", date(2024, 1, 1), 91, 30.0, 1.0)
    return pd.DataFrame(rows)


def _summary():
    day = _day_df()
    rows = []
    for campaign, part in day.groupby("campaign"):
        rows.append({
            "campaign": campaign,
            "group": "core_pmax" if campaign == "Pmax" else "core",
            "spend": part["cost"].sum(), "clicks": 10 * len(part),
            "conversions": part["conversions"].sum(),
            "last_active_date": part["date"].max()})
    return pd.DataFrame(rows)


def _run_recs(rules=RULES):
    summary = _summary()
    runs = pd.DataFrame([{
        "campaign": row["campaign"], "group": row["group"],
        "run_number": 1, "start": "2024-01-01",
        "end": row["last_active_date"],
        "active_days": int(row["conversions"]),
        "spend": row["spend"], "clicks": row["clicks"],
        "conversions": row["conversions"],
        "cost_per_conversion": row["spend"] / row["conversions"],
        "volume_flag": "ok"} for _, row in summary.iterrows()])
    return recommend.recommend_runs(runs, 10.0, rules, "caveat")


def _windows(window_days=30, lag=0, rules=RULES):
    return recommend.recent_window_results(
        _day_df(), _summary()["campaign"], window_days, lag, None,
        10.0, rules, VOLUME)


def test_recent_window_bounds_cost_and_label():
    alpha = _windows()["Alpha"]
    assert alpha["start"] == date(2024, 3, 2)
    assert alpha["end"] == date(2024, 3, 31)
    assert alpha["conversions"] == 30.0
    assert alpha["cost_per_conversion"] == 15.0
    assert alpha["ratio"] == 1.5
    assert alpha["label"] == "test"


def test_recent_window_end_applies_the_lag():
    alpha = _windows(lag=3)["Alpha"]
    assert alpha["end"] == date(2024, 3, 28)
    assert alpha["start"] == date(2024, 2, 28)


def test_active_campaign_label_comes_from_recent_window():
    recs = recommend.recommend_campaigns(
        _run_recs(), _summary(), RULES, "caveat",
        _windows()).set_index("campaign")
    alpha = recs.loc["Alpha"]
    # The run (91 days) is 755 / 91 = 8.30, continue; the last
    # 30 days are 15.00, 1.50 times the benchmark, test.
    assert alpha["run_label"] == "continue"
    assert alpha["label"] == "test"
    assert alpha["label_basis"] == "recent_window"
    assert alpha["label_ratio"] == 1.5
    assert alpha["action_text"] == "keep running, but test changes"
    assert alpha["reason"].startswith(
        "last 30 days (2024-03-02 to 2024-03-31): cost per "
        "conversion is 1.50 times the core benchmark")
    assert "latest run 1 (2024-01-01 to 2024-03-31" in alpha["reason"]
    assert "was labelled continue" in alpha["reason"]


def test_ended_and_fixed_campaigns_keep_their_label():
    rules = dict(RULES, not_comparable_groups=["core_pmax"])
    recs = recommend.recommend_campaigns(
        _run_recs(rules), _summary(), rules, "caveat",
        _windows(rules=rules)).set_index("campaign")
    assert recs.loc["Beta", "status_now"] == "ended"
    assert recs.loc["Beta", "label_basis"] == "latest_run"
    assert recs.loc["Pmax", "label"] == "not_comparable"
    assert recs.loc["Pmax", "label_basis"] == "fixed"


def test_low_recent_volume_is_insufficient_data():
    # A 5-day window has 5 conversions over 5 days: below the
    # volume rule, so insufficient_data, not the run label.
    recs = recommend.recommend_campaigns(
        _run_recs(), _summary(), RULES, "caveat",
        _windows(window_days=5)).set_index("campaign")
    alpha = recs.loc["Alpha"]
    assert alpha["label"] == "insufficient_data"
    assert alpha["run_label"] == "continue"
    assert "not enough volume to judge: 5 tracked conversions over 5 " \
        "active days" in alpha["reason"]


def test_without_recent_label_nothing_changes():
    recs = recommend.recommend_campaigns(
        _run_recs(), _summary(), RULES, "caveat").set_index("campaign")
    assert recs.loc["Alpha", "label"] == "continue"
    assert recs.loc["Alpha", "label_basis"] == "latest_run"
    assert (recs["label"] == recs["run_label"]).all()


def test_sensitivity_uses_the_recent_ratio():
    run_recs = _run_recs()
    recs = recommend.recommend_campaigns(
        run_recs, _summary(), RULES, "caveat", _windows())
    sens = recommend.sensitivity_table(
        run_recs, _summary(), RULES, recs).set_index("campaign")
    # Ratio 1.50 (the recent window, not the run's 0.83): test
    # below continue_max 1.5, continue at 1.5; every test_max is
    # at least 1.5, so never pause_or_review.
    assert set(sens.loc["Alpha", "label"]) == {"test", "continue"}
    assert not sens.loc["Alpha", "label_stable"].any()
    row = sens.loc["Alpha"]
    at_125 = row.loc[(row["continue_max_ratio"] == 1.25)
                     & (row["test_max_ratio"] == 2.0), "label"]
    assert list(at_125) == ["test"]


def test_report_counts_recent_labels(tmp_path):
    run_recs = _run_recs()
    recs = recommend.recommend_campaigns(
        run_recs, _summary(), RULES, "caveat", _windows())
    sens = recommend.sensitivity_table(run_recs, _summary(), RULES,
                                       recs)
    report = tmp_path / "recommend-report.md"
    recommend.write_recommend_report(report, run_recs, recs, sens,
                                     10.0)
    text = report.read_text()
    assert "- Active campaigns labelled from the recent window: 2" in text
    assert "- Of these, label differs from the run label: 1" in text
    assert "  - continue -> test: 1" in text
    assert "Alpha" not in text


def test_main_with_recent_label(tmp_path):
    summary = _summary()
    run_recs = _run_recs()
    runs = run_recs[["campaign", "group", "run_number", "start",
                     "end", "active_days", "spend", "clicks",
                     "conversions", "cost_per_conversion",
                     "volume_flag"]]
    paths = {name: tmp_path / f"{name}.csv" for name in
             ("runs", "summary", "day")}
    runs.to_csv(paths["runs"], index=False)
    summary.to_csv(paths["summary"], index=False)
    _day_df().to_csv(paths["day"], index=False)
    config = {"analysis": {
        "caveat_text": "caveat",
        "volume_rule": VOLUME,
        "recent_trend": {"conversion_lag_days": 0},
        "recommendation_rules": dict(
            RULES, recent_label={"window_days": 30}),
        "outputs": {
            "runs": str(paths["runs"]),
            "campaign_summary_day": str(paths["summary"]),
            "day": str(paths["day"]),
            "recommendations_by_run": str(tmp_path / "rr.csv"),
            "recommendations_by_campaign": str(tmp_path / "rc.csv"),
            "recommendation_sensitivity": str(tmp_path / "rs.csv"),
            "recommend_report": str(tmp_path / "r.md"),
        }}}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    assert recommend.main(["--config", str(path)]) == 0
    recs = pd.read_csv(tmp_path / "rc.csv").set_index("campaign")
    assert recs.loc["Alpha", "label"] == "test"
    assert recs.loc["Alpha", "base_label"] == "test"
