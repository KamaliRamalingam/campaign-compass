"""Tests for the Context, Campaign detail and Method display helpers
(dashboard/data.py). Made-up rows only; only data.py is imported."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import data as dd  # noqa: E402

NAN = float("nan")


def _weekdays():
    return pd.DataFrame({
        "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "tracked_actions": [100, 100, 100, 100, 100, 100, 100.0],
        "cost_per_tracked_action": [5.37, 6.19, 6.11, 6.26, 5.80, 4.44,
                                    4.57],
        "active_days": [10] * 7, "spend": [500.0] * 7,
        "clicks": [100, 100, 100, 100, 300, 100, 100],
        "conversion_rate": [0.3047, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
        "share_of_campaign_conversions": [12.2346] * 7,
        "volume_flag": ["ok"] * 6 + ["insufficient_data"]})


def test_weekday_outline_text_three_days_and_shared_day():
    assert dd.weekday_outline_text(_weekdays()) == (
        "Outlined: Thursday (highest cost), Saturday (lowest cost) and "
        "Friday (most clicks).")
    table = _weekdays()
    table.loc[3, "clicks"] = 900
    assert dd.weekday_outline_text(table) == (
        "Outlined: Thursday (highest cost, most clicks) and Saturday "
        "(lowest cost).")
    assert dd.weekday_outline_text(table.iloc[0:0]) == ""


def test_pooled_weekday_display_headers_and_values():
    shown = dd.pooled_weekday_display(_weekdays(), "SEK")
    assert list(shown.columns) == [
        "Weekday", "Tracked actions", "Cost per tracked action (SEK)",
        "Active days", "Spend (SEK)", "Clicks",
        "Tracked actions per 100 clicks", "Share of tracked actions (%)",
        "Volume"]
    assert shown["Weekday"].iloc[0] == "Monday"
    assert round(shown["Tracked actions per 100 clicks"].iloc[0], 2) == 30.47
    assert list(shown["Volume"].iloc[-2:]) == ["OK", "Low volume"]
    assert dd.format_number(30.47, dd.POOLED_WEEKDAY_FORMATS[
        "Tracked actions per 100 clicks"]) == "30.5"


def test_top_days_display():
    top = pd.DataFrame({
        "weekday": ["Fri"], "rank": [1], "date": ["2024-08-16"],
        "clicks": [7099.0], "share_of_weekday_clicks": [0.317856],
        "conversions": [38.0], "actions_per_click": [0.005353]})
    shown = dd.top_days_display(top, "Fri")
    assert list(shown.columns) == [
        "Rank", "Date", "Clicks", "Share of Friday clicks (%)",
        "Tracked actions", "Tracked actions per click"]
    assert shown["Date"].iloc[0] == "16 Aug 2024"
    assert dd.format_number(shown["Share of Friday clicks (%)"].iloc[0],
                            "%.1f") == "31.8"


def test_leave_one_out_takeaway():
    loo = pd.DataFrame({
        "left_out": ["(none)", "Alpha", "Beta"], "weekday": ["Fri"] * 3,
        "actions_per_click_vs_baseline": [0.82, 0.98, 0.7]})
    table = dd.leave_one_out_for_weekday(loo, "Fri")
    assert dd.leave_one_out_takeaway(table, "Fri", "Mon-Thu") == (
        "Leaving out Alpha brings Friday to 0.98x of the Mon-Thu level "
        "(with all campaigns: 0.82x).")
    assert dd.leave_one_out_takeaway(table.iloc[:1], "Fri", "Mon-Thu") == ""
    assert dd.leave_one_out_takeaway(table.iloc[1:], "Fri", "Mon-Thu") == ""
    config = {"analysis": {"weekday_decomposition": {
        "baseline_weekdays": ["Mon", "Tue", "Wed", "Thu"]}}}
    assert dd.baseline_label(config) == "Mon-Thu"


def test_what_if_note_and_value_text():
    assert dd.what_if_note("SEK") == (
        "Rough linear estimate. It assumes every extra SEK buys actions "
        "at today's average cost, and ignores diminishing returns and "
        "the campaign mix.")
    assert dd.value_text("not_active") == "Not active"
    assert dd.value_text("ended") == "Ended"
    assert dd.value_text(None) == "—"
    assert dd.trend_window_caption({"analysis": {"recent_trend": {
        "recent_window_days": 28}}}) == "Last 28 days vs the 28 days before."
    assert dd.trend_window_caption({}) is None


def _row(**changes):
    row = {"label": "pause_or_review", "label_basis": "latest_run",
           "latest_run_number": 2.0, "runs_with_volume": 1,
           "label_period_start": "2026-05-31",
           "label_period_end": "2026-07-13", "label_ratio": 25.373,
           "trend_override": NAN, "group": "core", "reason": "x"}
    row.update(changes)
    return pd.Series(row)


def test_why_lines_latest_run():
    assert dd.why_lines(_row(), 3, "Core campaigns") == [
        "Based on run 2 (31 May – 13 Jul 2026), the latest run with "
        "enough data.",
        "Cost per tracked action was 25.37x the benchmark of the Core "
        "campaigns.",
        "Only 1 of 3 runs had enough data."]
    lines = dd.why_lines(_row(runs_with_volume=3), 3, "Core campaigns")
    assert lines[-1] == "3 of 3 runs had enough data."
    assert len(dd.why_lines(_row(), 1, "Core campaigns")) == 2


def test_why_lines_recent_window_with_override():
    row = _row(label="test", label_basis="recent_window",
               label_period_start="2026-08-12",
               label_period_end="2026-11-09", label_ratio=0.446,
               trend_override="continue -> test")
    assert dd.why_lines(row, 1, "Core campaigns", window_days=90) == [
        "Based on the last 90 days (12 Aug – 9 Nov 2026), because the "
        "campaign is running.",
        "Cost per tracked action was 0.45x the benchmark of the Core "
        "campaigns.",
        "The label moved from Continue to Test because cost has risen "
        "recently."]


def test_why_lines_other_labels_have_no_keys_or_iso_dates():
    names = {"monthly_history_only": "Older campaigns"}
    assert dd.why_lines(_row(label="not_judged",
                             group="monthly_history_only"), 0, "C",
                        names=names) == [
        "Not judged: the Older campaigns group is not one of the judged "
        "groups."]
    assert dd.why_lines(_row(label="insufficient_data", label_ratio=NAN,
                             runs_with_volume=0), 1, "C") == [
        "No run had enough data to judge (0 of 1 runs)."]
    lines = dd.why_lines(_row(
        label="not_comparable",
        reason="group core_pmax is not comparable with the core benchmark "
               "(leave-one-out); cost per tracked action is 177.90"), 1, "C")
    assert lines == ["Not compared with the benchmark: judged against its "
                     "own history.",
                     "Cost per tracked action was 177.90 SEK."]
    text = " ".join(dd.why_lines(_row(), 3, "C"))
    assert "leave-one-out" not in text and "volume" not in text
    assert "2026-05-31" not in text


def test_trend_line():
    row = pd.Series({"recent_trend": "worsening",
                     "recent_window_start": "2026-10-13",
                     "recent_window_end": "2026-11-09",
                     "recent_vs_prior_ratio": 1.5158})
    assert dd.trend_line(row, 28) == (
        "Recent trend: Worsening. Cost per tracked action in the last 28 "
        "days (13 Oct – 9 Nov 2026) was 1.52x the 28 days before.")
    assert dd.trend_line(None, 28) == ""
    assert dd.NO_TREND_TEXT == ("No recent trend: this campaign is not "
                                "running.")


def test_low_volume_and_monthly_history_texts():
    config = {"analysis": {"weekday_min_conversions": 5}}
    table = pd.DataFrame({"tracked_actions": [3.0, 4.0]})
    assert dd.low_weekday_volume_text(table, config) == (
        "Based on only 7 tracked actions: read with care.")
    assert dd.low_weekday_volume_text(
        pd.DataFrame({"tracked_actions": [40.0]}), config) == ""
    months = pd.DataFrame({"source": ["month", "day"]})
    assert dd.monthly_history_text(months, pd.Timestamp("2024-07-01")) == (
        "Months before Jul 2024 come from the older monthly export.")
    assert dd.monthly_history_text(months.iloc[1:],
                                   pd.Timestamp("2024-07-01")) == ""


def test_period_labels_and_month_table():
    assert dd.period_label("2024-07") == "Jul 2024"
    assert dd.period_label("2024-08-16") == "16 Aug 2024"
    table = pd.DataFrame({"month": ["2019-07", "2024-07"],
                          "source": ["month", "day"], "active_days": [5, 9],
                          "spend": [10.0, 20.0], "tracked_actions": [1, 2],
                          "cost_per_tracked_action": [10.0, 10.0],
                          "month_note": ["", "partial"]})
    shown = dd.month_table_display(table, "SEK")
    assert list(shown.columns) == [
        "Month", "Source", "Active days", "Spend (SEK)", "Tracked actions",
        "Cost per tracked action (SEK)", "Month note"]
    assert list(shown["Month"]) == ["Jul 2019", "Jul 2024"]
    assert list(shown["Source"]) == ["Monthly export", "Daily export"]


def test_benchmarks_display():
    bench = pd.DataFrame({
        "variant": ["benchmark", "with_not_comparable", "judged_campaigns"],
        "groups": ["core", "core+core_pmax", "core+sep"],
        "leave_one_out": [True, NAN, NAN], "campaigns": [5, 6, 11],
        "spend": [1.0] * 3, "tracked_actions": [1.0] * 3,
        "cost_per_tracked_action": [1.0] * 3, "loo_min": [4.0, 4.1, NAN],
        "loo_max": [5.0, 7.8, NAN]})
    shown = dd.benchmarks_display(bench, {"core": "Core"}, "SEK")
    assert list(shown.columns) == [
        "What", "Groups", "Campaign left out?", "Campaigns", "Spend (SEK)",
        "Tracked actions", "Cost per tracked action (SEK)",
        "Lowest when one campaign is left out",
        "Highest when one campaign is left out"]
    assert shown["What"].iloc[2] == "Campaigns in the totals"
    assert list(shown["Campaign left out?"]) == ["Yes", "—", "—"]
    assert shown["Groups"].iloc[0] == "Core"


def test_settings_display_names_values_and_fallback():
    config = {"analysis": {
        "volume_rule": {"min_conversions": 10},
        "recommendation_rules": {"continue_max_ratio": 1.0,
                                 "benchmark": {"groups": ["core"],
                                               "leave_one_out": True},
                                 "made_up_key": 3},
        "recent_trend": {"lag_check_days": [3, 7, 14],
                         "trend_overrides": {"worsening": {
                             "continue": "test"}}},
        "run_gap_days": 14}}
    shown = dd.settings_display(config, {"core": "Core campaigns"})
    rows = shown.set_index("Key")
    assert list(shown.columns) == ["Setting", "What it means", "Value",
                                   "Key"]
    assert rows.loc["volume_rule.min_conversions", "Value"] == \
        "10 tracked actions"
    assert rows.loc["recommendation_rules.continue_max_ratio", "Value"] == \
        "1.0x"
    assert rows.loc["recommendation_rules.benchmark.groups", "Value"] == \
        "Core campaigns"
    assert rows.loc["recommendation_rules.benchmark.leave_one_out",
                    "Value"] == "Yes"
    assert rows.loc["recent_trend.lag_check_days", "Value"] == \
        "3, 7, 14 days"
    assert rows.loc["recent_trend.trend_overrides.worsening", "Value"] == \
        "Continue → Test"
    assert rows.loc["recommendation_rules.made_up_key", "Setting"] == \
        "recommendation_rules.made_up_key"
    assert rows.loc["run_gap_days", "Setting"] == "Run gap"


def test_what_counts_caption_and_journey_headers():
    mix = pd.DataFrame({"campaign": ["A", "B", "B"]})
    months = pd.DataFrame({"month": ["2019-06-01", "2026-11-01"]})
    assert dd.what_counts_caption(mix, months) == (
        "Covers all 2 campaigns in the conversion export, Jun 2019 – "
        "Nov 2026.")
    assert dd.what_counts_caption(mix) == (
        "Covers all 2 campaigns in the conversion export.")
    journey = pd.DataFrame({"campaign": ["A"], "spend": [1.0],
                            "directions_share": [0.5],
                            "tracked_actions_per_click": [0.3]})
    shown = dd.journey_table_display(journey, "SEK")
    assert list(shown.columns) == ["Campaign", "Spend (SEK)",
                                   "Directions (%)",
                                   "Tracked actions per click"]
    assert shown["Directions (%)"].iloc[0] == 50.0
    assert dd.ACTION_GROUP_TEXT["high_intent"] == "High intent"


def test_sensitivity_display():
    sens = pd.DataFrame({"campaign": ["A"], "group": ["core"],
                         "continue_max_ratio": [0.75],
                         "test_max_ratio": [1.5],
                         "label": ["pause_or_review"],
                         "label_stable": [False]})
    shown = dd.sensitivity_display(sens, {"core": "Core campaigns"})
    assert list(shown.iloc[0]) == ["A", "Core campaigns", 0.75, 1.5,
                                   "Pause or review", "No"]
