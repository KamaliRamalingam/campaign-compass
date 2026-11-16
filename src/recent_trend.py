"""Recent trend and weekly tables (T11).

Usage:
    python src/recent_trend.py --config config/restaurant.yaml

Reads outputs/interim/clean_day.csv, outputs/results/runs.csv
and outputs/results/recommendations_by_campaign.csv (their paths
come from the config) and writes, all git-ignored:
- outputs/results/recent_trend.csv: one row per campaign with
  status_now = active, except campaigns labelled not_judged
  (their group is not evaluated, so they get no trend row).
  Recent window = the recent_window_days
  ending at (last data date minus conversion_lag_days); prior
  window = the same number of days before that. Run average =
  cost per tracked action of the campaign's current run (its
  latest run), or, with recent_trend.run_average set to
  label_run_excluding_windows, of the run the label uses
  (latest_run_number), counting only its days before the prior
  window. recent_vs_prior_ratio is the recent cost per
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
    from src.recommend import ACTION_TEXT, action_text
except ImportError:  # running as `python src/recent_trend.py`
    from clean import load_config
    from paths import apply_output_root
    from recommend import ACTION_TEXT, action_text

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
TREND_WORSENING = "worsening"
TREND_IMPROVING = "improving"
TREND_STABLE = "stable"
TREND_INSUFFICIENT = "insufficient_data"
TREND_NOT_ACTIVE = "not_active"
TREND_NOT_JUDGED = "not_judged"
LABEL_NOT_JUDGED = "not_judged"
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


def current_run_period(runs_df, campaign):
    """(run_number, start, end) of the run used for the run
    average (the one with the latest end date), or None."""
    part = runs_df.loc[runs_df["campaign"] == campaign]
    if part.empty:
        return None
    latest = part.sort_values("end").iloc[-1]
    number = latest.get("run_number")
    return (None if number is None or pd.isna(number) else int(number),
            str(latest["start"]), str(latest["end"]))


RUN_AVERAGE_LEGACY = "legacy"
RUN_AVERAGE_LABEL_RUN = "label_run_excluding_windows"


def run_average_for(day, runs_df, rec, bounds, mode):
    """(run average, run_period) for one campaign.

    legacy (default): the whole run with the latest end date,
    including the recent and prior windows, as before.
    label_run_excluding_windows: the run the label uses
    (latest_run_number in the recommendations), only its days
    before the prior window starts, so the windows are not
    compared with themselves. run_period is (run_number, first
    day, last day) of the days used; (None, None) when there is
    no such run or no conversions in those days.
    """
    campaign = rec["campaign"]
    if mode == RUN_AVERAGE_LEGACY:
        return (current_run_average(runs_df, campaign),
                current_run_period(runs_df, campaign))
    if mode != RUN_AVERAGE_LABEL_RUN:
        raise ValueError(
            f"recent_trend.run_average: unknown value {mode!r} "
            f"(use {RUN_AVERAGE_LEGACY} or {RUN_AVERAGE_LABEL_RUN})")
    number = rec.get("latest_run_number")
    if number is None or pd.isna(number):
        return None, None
    run = runs_df.loc[(runs_df["campaign"] == campaign)
                      & (runs_df["run_number"] == int(number))]
    if run.empty:
        return None, None
    run = run.iloc[0]
    start = pd.to_datetime(run["start"]).date()
    end = pd.to_datetime(run["end"]).date()
    prior_start = bounds[2]
    part = day.loc[(day["campaign"] == campaign)
                   & (day["date"] >= start) & (day["date"] <= end)
                   & (day["date"] < prior_start)]
    conversions = float(part["conversions"].sum())
    if part.empty or conversions == 0:
        return None, None
    return (float(part["cost"].sum()) / conversions,
            (int(number), part["date"].min(), part["date"].max()))


def _period(start, end):
    return f"{start} to {end}"


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
                 prior_actions, settings, bounds, run_period=None):
    """Plain-language reason for the trend, with both ratios and
    the period each one covers.

    bounds is (recent_start, recent_end, prior_start, prior_end);
    run_period is (run_number, start, end) of the days the run
    average was taken from, or None.
    """
    recent_start, recent_end, prior_start, prior_end = bounds
    recent = f"the recent window ({_period(recent_start, recent_end)})"
    prior = f"the prior window ({_period(prior_start, prior_end)})"
    minimum = settings["min_tracked_actions_in_window"]
    if trend == TREND_INSUFFICIENT:
        return (
            f"not enough data to judge: {recent_actions:.0f} "
            f"tracked actions in {recent} and "
            f"{prior_actions:.0f} in {prior} "
            f"(minimum {minimum} per window)"
        )
    parts = []
    if prior_ratio is not None:
        parts.append(f"{prior_ratio:.2f} times {prior}")
    if run_ratio is not None:
        if run_period is not None:
            number, start, end = run_period
            run = (f"the run {number} average "
                   f"({_period(start, end)})")
        else:
            run = "the run average"
        parts.append(f"{run_ratio:.2f} times {run}")
    if not parts:
        return (f"no prior window or run average to compare "
                f"{recent} with")
    return (f"cost per tracked action in {recent} is "
            + " and ".join(parts))


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
        if rec.get("base_label", rec.get("label")) == LABEL_NOT_JUDGED:
            continue
        campaign = rec["campaign"]
        recent_spend, recent_actions = _window_totals(
            day, campaign, recent_start, recent_end)
        prior_spend, prior_actions = _window_totals(
            day, campaign, prior_start, prior_end)
        recent_cost = _safe_divide(recent_spend, recent_actions)
        prior_cost = _safe_divide(prior_spend, prior_actions)
        run_average, run_period = run_average_for(
            day, runs_df, rec, bounds,
            settings.get("run_average", RUN_AVERAGE_LEGACY))
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
                prior_actions, settings, bounds, run_period),
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


def _strip_suffix(text):
    """action_text without any trailing worsening suffix."""
    text = "" if pd.isna(text) else str(text)
    while text.endswith(WORSENING_SUFFIX):
        text = text[:-len(WORSENING_SUFFIX)]
    return text


def _base_columns(recs):
    """base_label / base_action_text / base_reason, filled in.

    Written by src/recommend.py. For an older file without them
    they are taken from the current columns, with any worsening
    suffix removed from action_text.
    """
    recs = recs.copy()
    if "base_label" not in recs.columns:
        recs["base_label"] = recs["label"] \
            if "label" in recs.columns else None
    if "base_action_text" not in recs.columns:
        recs["base_action_text"] = recs["action_text"].map(
            _strip_suffix)
    if "base_reason" not in recs.columns:
        recs["base_reason"] = recs["reason"] \
            if "reason" in recs.columns else ""
    return recs


def trend_overrides(settings):
    """{trend: {label: new_label}} from settings, checked.

    Default {} (no overrides). Every new label must be a known
    label, so the action text can be rebuilt for it.
    """
    overrides = (settings or {}).get("trend_overrides") or {}
    known = {label for label, _ in ACTION_TEXT}
    for trend, mapping in overrides.items():
        for old, new in (mapping or {}).items():
            if new not in known:
                raise ValueError(
                    f"trend_overrides.{trend}.{old}: unknown label "
                    f"{new!r} (known: {', '.join(sorted(known))})")
    return overrides


def _best_run(row):
    """best_run dict for action_text from a recommendation row."""
    number = row.get("best_run_number")
    if number is None or pd.isna(number):
        return None
    return {"run_number": int(number),
            "start": row.get("best_run_start"),
            "end": row.get("best_run_end")}


def _override(row, trend, window, overrides):
    """(label, action_text, reason, note) after trend_overrides.

    Without a matching override the base values are returned
    and note is "".
    """
    label = row["base_label"]
    text = row["base_action_text"]
    reason = row.get("base_reason", "")
    new = (overrides.get(trend) or {}).get(label)
    if new is None or new == label:
        return label, text, reason, ""
    latest = row.get("latest_run_number")
    latest = None if latest is None or pd.isna(latest) else int(latest)
    repeat = bool(row.get("repeat_eligible")) \
        if not pd.isna(row.get("repeat_eligible", False)) else False
    text = action_text(new, row["status_now"], repeat,
                       _best_run(row), latest)
    note = f"{label} -> {new}"
    reason = (f"{reason}; label changed {label} -> {new} because "
              f"the recent trend is {trend} ({window})")
    return new, text, reason, note


def apply_to_recommendations(recommendations, trend_table,
                             settings=None):
    """Add recent trend, ratios and reason, and the suffix.

    Campaigns that are not active get recent_trend not_active
    and no ratio or reason; campaigns labelled not_judged get
    recent_trend not_judged. The suffix is appended to
    action_text only when recent_trend is worsening.

    Idempotent: label, action_text and reason are always rebuilt
    from the base_ columns, so running the stage twice gives the
    same file.

    settings["trend_overrides"] (default none) changes the label
    of an active campaign by its trend, e.g. {worsening:
    {continue: test}}: the action text is rebuilt for the new
    label, the reason says why and for which window, and the
    trend_override column records the change.
    """
    overrides = trend_overrides(settings)
    recs = _base_columns(recommendations)
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
        elif row.get("base_label") == LABEL_NOT_JUDGED:
            trends.append(TREND_NOT_JUDGED)
            run_ratios.append(None)
            prior_ratios.append(None)
            reasons.append("")
        else:
            trends.append(TREND_NOT_ACTIVE)
            run_ratios.append(None)
            prior_ratios.append(None)
            reasons.append("")
    recs["recent_trend"] = trends
    recs["ratio_vs_run_average"] = run_ratios
    recs["recent_vs_prior_ratio"] = prior_ratios
    recs["trend_reason"] = reasons
    windows = {}
    if by_campaign is not None:
        for campaign, trend_row in by_campaign.iterrows():
            windows[campaign] = (
                f"recent window {trend_row['recent_window_start']} "
                f"to {trend_row['recent_window_end']}")
    labels, texts, new_reasons, notes = [], [], [], []
    for (_, row), trend in zip(recs.iterrows(), trends):
        if "label" in recs.columns and overrides:
            label, text, reason, note = _override(
                row, trend, windows.get(row["campaign"], ""),
                overrides)
        else:
            label, text, reason, note = (
                row.get("base_label"), row["base_action_text"],
                row.get("base_reason", ""), "")
        labels.append(label)
        texts.append(text)
        new_reasons.append(reason)
        notes.append(note)
    if "label" in recs.columns:
        recs["label"] = labels
    if "reason" in recs.columns:
        recs["reason"] = new_reasons
    recs["trend_override"] = notes
    recs["action_text"] = [
        text + WORSENING_SUFFIX if trend == TREND_WORSENING
        else text
        for text, trend in zip(texts, trends)
    ]
    return recs


FINAL_LABELS_HEADING = (
    "## Campaigns per label (final, after trend override)")


def update_recommend_report(report_path, updated):
    """Add the final label counts to recommend-report.md.

    The section FINAL_LABELS_HEADING is replaced if it is already
    there (so reruns stay idempotent) or appended. Counts only.
    Returns False when the report does not exist.
    """
    path = Path(report_path)
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    if FINAL_LABELS_HEADING in lines:
        start = lines.index(FINAL_LABELS_HEADING)
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith("## ")), len(lines))
        lines = lines[:start] + lines[end:]
    while lines and lines[-1] == "":
        lines.pop()
    lines += ["", FINAL_LABELS_HEADING, ""]
    for label, count in updated["label"].value_counts().items():
        lines.append(f"- {label}: {int(count)}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return True


def write_recent_trend_report(report_path, trend_table, bounds,
                              last_date, updated=None):
    """Write the recent-trend report: counts only, no names.

    updated (the recommendations after trend_overrides) adds the
    number of labels the overrides changed, by transition.
    """
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
    if updated is not None and "trend_override" in updated.columns:
        changed = updated.loc[updated["trend_override"].fillna("") != ""]
        lines.append("## Labels changed by trend_overrides")
        lines.append("")
        lines.append(f"- Campaigns: {len(changed)}")
        for note, count in changed["trend_override"] \
                .value_counts().items():
            lines.append(f"  - {note}: {int(count)}")
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
            recommendations, trend_table, settings)
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
        report_out, trend_table, bounds, last_date, updated)

    print(f"Last data date: {last_date}")
    print(f"Recent window: {bounds[0]} to {bounds[1]}")
    print(f"Prior window: {bounds[2]} to {bounds[3]}")
    print(f"Active campaigns: {len(trend_table)}")
    print("Campaigns per recent trend:")
    for trend, count in trend_table["recent_trend"] \
            .value_counts().items():
        print(f"  {trend}: {int(count)}")
    if "label" in updated.columns:
        print("Campaigns per final label (after trend override):")
        for label, count in updated["label"].value_counts().items():
            print(f"  {label}: {int(count)}")
        recommend_report = outputs.get("recommend_report")
        if recommend_report and update_recommend_report(
                recommend_report, updated):
            print(f"updated: {recommend_report} (final label counts)")
        else:
            print("Final label counts not added: recommend report "
                  "not found")
    print(f"Weekly rows: {len(weekly)}")
    print(f"wrote: {trend_out}")
    print(f"wrote: {weekly_out}")
    print(f"wrote: {recs_out}")
    print(f"report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
