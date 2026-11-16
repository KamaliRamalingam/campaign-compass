"""Recent trend and weekly tables (T11).

Usage:
    python src/recent_trend.py --config config/restaurant.yaml

Reads outputs/interim/clean_day.csv, outputs/results/runs.csv
and outputs/results/recommendations_by_campaign.csv (their paths
come from the config) and writes, all git-ignored:
- outputs/results/recent_trend.csv: one row per campaign with
  status_now = active. Recent window = the recent_window_days
  ending at (last data date minus conversion_lag_days); prior
  window = the same number of days before that. Run average =
  cost per tracked action of the campaign's current run (its
  latest run). recent_vs_prior_ratio is the recent cost per
  tracked action divided by the prior window's, empty when the
  prior window is empty or below the minimum tracked actions.
  recent_trend is worsening when the recent cost per tracked
  action is at least worsening_vs_prior_ratio times the prior
  window or at least worsening_ratio times the run average,
  improving when it is at most improving_vs_prior_ratio times
  the prior window or at most improving_ratio times the run
  average (worsening wins when both would apply), stable
  otherwise, and insufficient_data when either window has fewer
  tracked actions than min_tracked_actions_in_window.
  trend_reason explains the trend in plain language, with both
  ratios.
- outputs/results/weekly_by_campaign.csv: per campaign and week
  (week start Monday), from the daily data.
- updates outputs/results/recommendations_by_campaign.csv in
  place: adds recent_trend and ratio_vs_run_average, and when
  recent_trend is worsening appends to action_text:
  "; cost per tracked action has risen recently: check budget
  changes and conversion reporting".
- outputs/reports/recent-trend-report.md: counts only
  (campaigns by trend, windows used, dates). No campaign names.

All values come from analysis.recent_trend in the config; no
dates, thresholds or campaign names are hard-coded here. The
lag is provisional and not verified: the last
conversion_lag_days of data are excluded because tracked
actions can be reported with a delay.

Only counts per trend are printed, never campaign names or rows.
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

try:
    from src.paths import apply_output_root
    from src.clean import load_config
except ImportError:  # running as `python src/recent_trend.py`
    from clean import load_config
    from paths import apply_output_root

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
TREND_WORSENING = "worsening"
TREND_IMPROVING = "improving"
TREND_STABLE = "stable"
TREND_INSUFFICIENT = "insufficient_data"
TREND_NOT_ACTIVE = "not_active"
WORSENING_SUFFIX = (
    "; cost per tracked action has risen recently: check "
    "budget changes and conversion reporting"
)


def _safe_divide(numerator, denominator):
    """Division that returns None instead of failing on zero."""
    if denominator is None or denominator == 0:
        return None
    return numerator / denominator


def window_bounds(last_date, window_days, lag_days):
    """(recent_start, recent_end, prior_start, prior_end).

    The recent window is window_days long and ends at
    (last_date minus lag_days); the prior window is the
    window_days before that.
    """
    recent_end = last_date - timedelta(days=lag_days)
    recent_start = recent_end - timedelta(days=window_days - 1)
    prior_end = recent_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=window_days - 1)
    return recent_start, recent_end, prior_start, prior_end


def _window_totals(day_df, campaign, start, end):
    """(spend, tracked actions) for one campaign in a window."""
    part = day_df.loc[
        (day_df["campaign"] == campaign)
        & (day_df["date"] >= start)
        & (day_df["date"] <= end)
    ]
    return float(part["cost"].sum()), float(part["conversions"].sum())


def current_run_average(runs_df, campaign):
    """Cost per tracked action of the campaign's current run.

    The current run is the one with the latest end date. None
    when the campaign has no runs or the run has no average.
    """
    part = runs_df.loc[runs_df["campaign"] == campaign]
    if part.empty:
        return None
    latest = part.sort_values("end").iloc[-1]
    value = latest.get("cost_per_conversion")
    if value is None or pd.isna(value):
        return None
    return float(value)


def label_trend(prior_ratio, run_ratio, recent_actions,
                prior_actions, settings):
    """recent_trend from the two ratios and the window volumes.

    insufficient_data when either window has fewer tracked
    actions than the minimum. Worsening when the recent cost
    per tracked action is at least worsening_vs_prior_ratio
    times the prior window, or at least worsening_ratio times
    the run average. Improving when it is at most
    improving_vs_prior_ratio times the prior window, or at most
    improving_ratio times the run average. Otherwise stable.
    When worsening and improving would both apply, worsening
    wins.
    """
    minimum = settings["min_tracked_actions_in_window"]
    if recent_actions < minimum or prior_actions < minimum:
        return TREND_INSUFFICIENT
    worsening = (
        (prior_ratio is not None
         and prior_ratio >= settings["worsening_vs_prior_ratio"])
        or (run_ratio is not None
            and run_ratio >= settings["worsening_ratio"])
    )
    if worsening:
        return TREND_WORSENING
    improving = (
        (prior_ratio is not None
         and prior_ratio <= settings["improving_vs_prior_ratio"])
        or (run_ratio is not None
            and run_ratio <= settings["improving_ratio"])
    )
    if improving:
        return TREND_IMPROVING
    return TREND_STABLE


def trend_reason(trend, prior_ratio, run_ratio, recent_actions,
                 prior_actions, settings):
    """Plain-language reason for the trend, with both ratios."""
    minimum = settings["min_tracked_actions_in_window"]
    if trend == TREND_INSUFFICIENT:
        return (
            f"not enough data to judge: {recent_actions:.0f} "
            f"tracked actions in the recent window and "
            f"{prior_actions:.0f} in the prior window "
            f"(minimum {minimum} per window)"
        )
    parts = []
    if prior_ratio is not None:
        parts.append(
            f"{prior_ratio:.2f} times the prior 28 days")
    if run_ratio is not None:
        parts.append(f"{run_ratio:.2f} times the run average")
    if not parts:
        return "no prior window or run average to compare with"
    return "cost per tracked action is " + " and ".join(parts)


def compute_recent_trend(day_df, runs_df, recommendations,
                         settings):
    """Recent trend, one row per campaign with status_now active."""
    day = day_df.copy()
    day["date"] = pd.to_datetime(day["date"]).dt.date
    last_date = day["date"].max()
    window_days = settings["recent_window_days"]
    bounds = window_bounds(
        last_date, window_days, settings["conversion_lag_days"])
    recent_start, recent_end, prior_start, prior_end = bounds
    rows = []
    for _, rec in recommendations.iterrows():
        if rec["status_now"] != "active":
            continue
        campaign = rec["campaign"]
        recent_spend, recent_actions = _window_totals(
            day, campaign, recent_start, recent_end)
        prior_spend, prior_actions = _window_totals(
            day, campaign, prior_start, prior_end)
        recent_cost = _safe_divide(recent_spend, recent_actions)
        prior_cost = _safe_divide(prior_spend, prior_actions)
        run_average = current_run_average(runs_df, campaign)
        run_ratio = (
            recent_cost / run_average
            if recent_cost is not None and run_average
            else None
        )
        # Round so a ratio that is exactly on a threshold in
        # the data is not pushed under it by float arithmetic.
        run_ratio = round(run_ratio, 4) \
            if run_ratio is not None else None
        # Empty when the prior window is empty or below the
        # minimum tracked actions.
        prior_ratio = (
            recent_cost / prior_cost
            if recent_cost is not None and prior_cost is not None
            and prior_actions >= settings[
                "min_tracked_actions_in_window"]
            else None
        )
        prior_ratio = round(prior_ratio, 4) \
            if prior_ratio is not None else None
        trend = label_trend(
            prior_ratio, run_ratio, recent_actions,
            prior_actions, settings)
        rows.append({
            "campaign": campaign,
            "recent_window_start": recent_start,
            "recent_window_end": recent_end,
            "prior_window_start": prior_start,
            "prior_window_end": prior_end,
            "recent_spend": recent_spend,
            "recent_tracked_actions": recent_actions,
            "recent_cost_per_tracked_action": recent_cost,
            "prior_spend": prior_spend,
            "prior_tracked_actions": prior_actions,
            "prior_cost_per_tracked_action": prior_cost,
            "run_average_cost_per_tracked_action": run_average,
            "ratio_vs_run_average": run_ratio,
            "recent_vs_prior_ratio": prior_ratio,
            "recent_trend": trend,
            "trend_reason": trend_reason(
                trend, prior_ratio, run_ratio, recent_actions,
                prior_actions, settings),
        })
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values("campaign").reset_index(drop=True)


def weekly_table(day_df):
    """Per campaign and week (week start Monday), daily data."""
    day = day_df.copy()
    day["date"] = pd.to_datetime(day["date"])
    day["week_start"] = (
        day["date"] - pd.to_timedelta(day["date"].dt.day_of_week,
                                      unit="D")
    ).dt.date
    rows = []
    for (campaign, week_start), part in day.groupby(
            ["campaign", "week_start"]):
        spend = float(part["cost"].sum())
        conversions = float(part["conversions"].sum())
        rows.append({
            "campaign": campaign,
            "week_start": week_start,
            "active_days": int(part["date"].nunique()),
            "spend": spend,
            "tracked_actions": conversions,
            "cost_per_tracked_action": _safe_divide(
                spend, conversions),
        })
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values(["campaign", "week_start"]).reset_index(
        drop=True)


def apply_to_recommendations(recommendations, trend_table):
    """Add recent trend, ratios and reason, and the suffix.

    Campaigns that are not active get recent_trend not_active
    and no ratio or reason. The suffix is appended to
    action_text only when recent_trend is worsening.
    """
    recs = recommendations.copy()
    by_campaign = trend_table.set_index("campaign") \
        if not trend_table.empty else None
    trends = []
    run_ratios = []
    prior_ratios = []
    reasons = []
    for _, row in recs.iterrows():
        campaign = row["campaign"]
        if by_campaign is not None and campaign in by_campaign.index:
            trend_row = by_campaign.loc[campaign]
            trends.append(trend_row["recent_trend"])
            run_ratios.append(trend_row["ratio_vs_run_average"])
            prior_ratios.append(trend_row["recent_vs_prior_ratio"])
            reasons.append(trend_row["trend_reason"])
        else:
            trends.append(TREND_NOT_ACTIVE)
            run_ratios.append(None)
            prior_ratios.append(None)
            reasons.append("")
    recs["recent_trend"] = trends
    recs["ratio_vs_run_average"] = run_ratios
    recs["recent_vs_prior_ratio"] = prior_ratios
    recs["trend_reason"] = reasons
    recs["action_text"] = [
        text + WORSENING_SUFFIX if trend == TREND_WORSENING
        else text
        for text, trend in zip(recs["action_text"], trends)
    ]
    return recs


def write_recent_trend_report(report_path, trend_table, bounds,
                              last_date):
    """Write the recent-trend report: counts only, no names."""
    recent_start, recent_end, prior_start, prior_end = bounds
    lines = ["# Recent trend report", ""]
    lines.append(f"- Last data date: {last_date}")
    lines.append(
        f"- Recent window: {recent_start} to {recent_end}")
    lines.append(f"- Prior window: {prior_start} to {prior_end}")
    lines.append(f"- Active campaigns: {len(trend_table)}")
    lines.append("")
    lines.append("## Campaigns per recent trend")
    lines.append("")
    if trend_table.empty:
        lines.append("- (none)")
    else:
        for trend, count in trend_table["recent_trend"] \
                .value_counts().items():
            lines.append(f"- {trend}: {int(count)}")
    lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Compute the recent trend and weekly tables."""
    parser = argparse.ArgumentParser(
        description="Compute recent trend and weekly tables."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        config = apply_output_root(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    analysis = config["analysis"]
    outputs = analysis.get("outputs") or {}
    settings = analysis.get("recent_trend") or {}
    try:
        day_df = pd.read_csv(outputs["day"])
        runs_df = pd.read_csv(outputs["runs"])
        recommendations = pd.read_csv(
            outputs["recommendations_by_campaign"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    try:
        last_date = pd.to_datetime(day_df["date"]).dt.date.max()
        bounds = window_bounds(
            last_date, settings["recent_window_days"],
            settings["conversion_lag_days"])
        trend_table = compute_recent_trend(
            day_df, runs_df, recommendations, settings)
        weekly = weekly_table(day_df)
        updated = apply_to_recommendations(
            recommendations, trend_table)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    trend_out = Path(outputs.get(
        "recent_trend", "outputs/results/recent_trend.csv"))
    weekly_out = Path(outputs.get(
        "weekly_by_campaign",
        "outputs/results/weekly_by_campaign.csv"))
    recs_out = Path(outputs["recommendations_by_campaign"])
    report_out = Path(outputs.get(
        "recent_trend_report",
        "outputs/reports/recent-trend-report.md"))
    for path in (trend_out, weekly_out, recs_out, report_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    trend_table.to_csv(trend_out, index=False)
    weekly.to_csv(weekly_out, index=False)
    updated.to_csv(recs_out, index=False)
    write_recent_trend_report(
        report_out, trend_table, bounds, last_date)

    print(f"Last data date: {last_date}")
    print(f"Recent window: {bounds[0]} to {bounds[1]}")
    print(f"Prior window: {bounds[2]} to {bounds[3]}")
    print(f"Active campaigns: {len(trend_table)}")
    print("Campaigns per recent trend:")
    for trend, count in trend_table["recent_trend"] \
            .value_counts().items():
        print(f"  {trend}: {int(count)}")
    print(f"Weekly rows: {len(weekly)}")
    print(f"wrote: {trend_out}")
    print(f"wrote: {weekly_out}")
    print(f"wrote: {recs_out}")
    print(f"report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
