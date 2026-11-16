"""Tests for PR 3 M5: the weekday decomposition.

All data is tiny and made up. No real data, no real campaign
names, no real rows from the exports.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import weekday_decomposition as wd

GROUPS = {"core": ["Alpha"], "core_pmax": ["Pmax"], "other": ["Gamma"]}
TIME_GROUPS = ["core", "core_pmax"]
BASELINE = ["Mon", "Tue", "Wed", "Thu"]


def _day_df():
    """Two weeks from Monday 2026-01-05. Alpha: 10 clicks and 2
    actions every day (Friday 20 clicks, 4 actions, so its own
    Friday rate equals its baseline). Pmax: 10 clicks and 1
    action a day, but 50 and 70 clicks with 1 action on the two
    Fridays. Gamma is outside time_groups."""
    rows = []
    for offset in range(14):
        day = date(2026, 1, 5) + timedelta(days=offset)
        friday = day.weekday() == 4
        alpha = (20, 4.0) if friday else (10, 2.0)
        pmax = ((50 if offset < 7 else 70), 1.0) if friday \
            else (10, 1.0)
        for name, (clicks, conversions) in (
                ("Alpha", alpha), ("Pmax", pmax), ("Gamma", (99, 0.0))):
            rows.append({"date": day.isoformat(), "campaign": name,
                         "clicks": clicks, "cost": float(clicks),
                         "conversions": conversions})
    return pd.DataFrame(rows)


def _prepared():
    return wd.prepare(_day_df(), GROUPS, TIME_GROUPS)


def test_mix_by_campaign_shares_and_rates():
    mix = wd.mix_by_campaign(_prepared(), BASELINE).set_index(
        ["campaign", "weekday"])
    pmax_fri = mix.loc[("Pmax", "Fri")]
    # Pmax: 80 Mon-Thu + 120 Fri + 40 Sat-Sun = 240 clicks.
    assert pmax_fri["clicks"] == 120
    assert pmax_fri["share_of_campaign_clicks"] == pytest.approx(0.5)
    assert pmax_fri["share_vs_even"] == pytest.approx(3.5)
    # Pooled Friday clicks: Alpha 40 + Pmax 120 = 160.
    assert pmax_fri["share_of_weekday_clicks"] == pytest.approx(0.75)
    # Friday 2 / 120, baseline 8 / 80 = 0.1.
    assert pmax_fri["actions_per_click_vs_baseline"] == \
        pytest.approx((2 / 120) / 0.1)
    alpha_fri = mix.loc[("Alpha", "Fri")]
    assert alpha_fri["actions_per_click_vs_baseline"] == \
        pytest.approx(1.0)
    assert "Gamma" not in mix.index.get_level_values("campaign")


def test_leave_one_out_shows_one_campaign_explains_friday():
    loo = wd.leave_one_out(_prepared(), BASELINE).set_index(
        ["left_out", "weekday"])
    # All: Friday 10 actions / 160 clicks vs baseline 24 / 160.
    full = loo.loc[("(none)", "Fri"), "actions_per_click_vs_baseline"]
    assert full == pytest.approx((10 / 160) / (24 / 160))
    # Without Pmax, Friday is back at the baseline.
    assert loo.loc[("Pmax", "Fri"), "actions_per_click_vs_baseline"] \
        == pytest.approx(1.0)
    assert loo.loc[("Alpha", "Fri"), "clicks"] == 120
    assert list(loo.reset_index()["left_out"].unique()) == [
        "(none)", "Alpha", "Pmax"]


def test_focus_weekday_and_top_days():
    df = _prepared()
    assert wd.focus_weekday(df, {}) == "Fri"
    assert wd.focus_weekday(df, {"focus_weekday": "Mon"}) == "Mon"
    with pytest.raises(ValueError, match="Funday"):
        wd.focus_weekday(df, {"focus_weekday": "Funday"})
    top = wd.top_days(df, "Fri", 5)
    assert list(top["date"].astype(str)) == ["2026-01-16",
                                             "2026-01-09"]
    assert list(top["clicks"]) == [90, 70]
    assert top["share_of_weekday_clicks"].sum() == pytest.approx(1.0)


def _config(tmp_path, settings):
    day = tmp_path / "clean_day.csv"
    _day_df().to_csv(day, index=False)
    analysis = {"campaign_groups": GROUPS, "time_groups": TIME_GROUPS,
                "outputs": {
                    "day": str(day),
                    "weekday_mix_by_campaign": str(tmp_path / "mix.csv"),
                    "weekday_leave_one_out": str(tmp_path / "loo.csv"),
                    "weekday_top_days": str(tmp_path / "top.csv"),
                    "weekday_decomposition_report": str(
                        tmp_path / "report.md")}}
    if settings is not None:
        analysis["weekday_decomposition"] = settings
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(analysis and {"analysis": analysis}))
    return path


def test_main_skips_without_settings(tmp_path, capsys):
    assert wd.main(["--config", str(_config(tmp_path, None))]) == 0
    assert "Weekday decomposition skipped" in capsys.readouterr().out
    assert not (tmp_path / "mix.csv").exists()


def test_main_writes_aggregates_and_name_free_report(tmp_path, capsys):
    path = _config(tmp_path, {"top_days": 5})
    assert wd.main(["--config", str(path)]) == 0
    out = capsys.readouterr().out
    assert "focus weekday Fri" in out
    for name in ("Alpha", "Pmax", "Gamma", "2026-01"):
        assert name not in out
    report = (tmp_path / "report.md").read_text()
    for name in ("Alpha", "Pmax", "Gamma"):
        assert name not in report
    # Pooled clicks: Alpha 160 + Pmax 240 = 400; Friday 160.
    assert "- Focus weekday (most pooled clicks): Fri, 40.0% of " \
        "pooled clicks" in report
    assert ("Campaigns with more than an even share (1/7) of their "
            "own clicks on Fri: 2 of 2") in report
    # Only Pmax has a lower Friday rate than its own baseline.
    assert ("lower actions per click on Fri than on their own "
            "baseline weekdays: 1 of 2") in report
    assert "Largest single-campaign share of Fri clicks: 75.0%" in report
    assert ("Leaving out the campaign with the largest effect (its "
            "share of Fri clicks: 75.0%) moves it from 0.42 to 1.00"
            ) in report
    assert "the top 2 hold 100.0% of Fri clicks" in report
    assert "| 1 | 2026-01-16 | 56.2% | 0.056 |" in report
