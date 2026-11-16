"""Time patterns, trends and runs (T4).

Usage:
    python src/time_patterns.py --config config/restaurant.yaml

Reads the cleaned day and month tables written by src/clean.py
(their paths come from the config) and writes, all git-ignored:
- outputs/results/weekday_by_campaign.csv: per campaign and
  weekday (Mon-Sun), active days, spend, clicks, conversions,
  cost_per_conversion, conversion_rate, share of the campaign's
  conversions, volume_flag.
- outputs/results/weekday_core.csv: the same, pooled for the
  whole core group.
- outputs/results/monthly_by_campaign.csv: per campaign and
  calendar month from the daily data, with days_in_month,
  days_covered (days of the month between the campaign's first
  and last active date, capped at the last date of the data),
  is_partial (days_covered < days_in_month) and is_lagged (the
  campaign has active days in the month within the last
  recent_trend.conversion_lag_days of data, default 0 = never).
- outputs/results/timeline_by_campaign.csv: the monthly table
  with the monthly-history table appended, with a "source"
  column (day or month). The partial-month columns are empty
  for monthly-history rows (no daily dates to check).
- outputs/results/runs.csv: per campaign, activity split into
  runs; for each run: run_number, start, end, active_days, spend,
  clicks, conversions, cost_per_conversion, conversion_rate,
  volume_flag.
- outputs/reports/time-report.md: counts only (rows per table,
  number of runs, number of cells flagged insufficient). No
  campaign names, no rows.

Only the groups in analysis.time_groups are analysed. Runs
are built for the groups in analysis.run_groups; when that key
is not set, runs cover time_groups plus sep_2026_group (the
behaviour before run_groups existed). Use active days only; never fill
missing days. A gap of more than analysis.run_gap_days with no
activity starts a new run. A weekday cell below
analysis.weekday_min_conversions is flagged insufficient_data.
"""

import argparse
import calendar
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yaml

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src.groups import assign_group
    from src.metrics import _safe_divide
except ImportError:  # running as `python src/time_patterns.py`
    from clean import load_config
    from paths import apply_output_root
    from groups import assign_group
    from metrics import _safe_divide

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Used only when analysis.run_groups is not set, so configs
# without the key behave exactly as before run_groups existed.
LEGACY_RUN_GROUPS_EXTRA = ("sep_2026_group",)


def resolve_run_groups(analysis):
    """analysis.run_groups, or time_groups plus the legacy group."""
    run_groups = analysis.get("run_groups")
    if run_groups is not None:
        return list(run_groups)
    return (list(analysis.get("time_groups") or [])
            + list(LEGACY_RUN_GROUPS_EXTRA))


def _prepare(df):
    """Copy a cleaned table and parse its date column."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _with_group(df, groups):
    """Add a group column from the config groups."""
    df = df.copy()
    df["group"] = df["campaign"].apply(
        lambda name: assign_group(name, groups)
    )
    return df


def _metrics_row(part, conversions_total=None):
    """Metrics for one slice of rows (one campaign/weekday, etc.)."""
    spend = float(part["cost"].sum())
    clicks = int(part["clicks"].sum())
    conversions = float(part["conversions"].sum())
    row = {
        "active_days": int(part["date"].nunique()),
        "spend": spend,
        "clicks": clicks,
        "conversions": conversions,
        "cost_per_conversion": _safe_divide(spend, conversions),
        "conversion_rate": _safe_divide(conversions, clicks),
    }
    if conversions_total is not None:
        row["share_of_campaign_conversions"] = (
            conversions / conversions_total * 100
            if conversions_total else 0.0
        )
    return row


def weekday_table(day_df, groups, time_groups,
                  weekday_min_conversions):
    """Per campaign and weekday, for the groups in time_groups."""
    df = _with_group(_prepare(day_df), groups)
    df = df.loc[df["group"].isin(time_groups)].copy()
    df["weekday"] = pd.to_datetime(df["date"]).dt.day_of_week
    campaign_totals = df.groupby("campaign")["conversions"].sum()
    rows = []
    for (campaign, weekday), part in df.groupby(["campaign", "weekday"]):
        row = {"campaign": campaign,
               "weekday": WEEKDAYS[weekday]}
        row.update(_metrics_row(
            part, campaign_totals[campaign]))
        row["volume_flag"] = (
            "insufficient_data"
            if row["conversions"] < weekday_min_conversions
            else "ok"
        )
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["weekday_no"] = table["weekday"].apply(WEEKDAYS.index)
    table = table.sort_values(["campaign", "weekday_no"])
    return table.drop(columns=["weekday_no"]).reset_index(drop=True)


def pooled_weekday_table(day_df, groups, time_groups,
                         weekday_min_conversions):
    """Weekday table pooled for the whole time_groups set."""
    df = _with_group(_prepare(day_df), groups)
    df = df.loc[df["group"].isin(time_groups)].copy()
    df["weekday"] = pd.to_datetime(df["date"]).dt.day_of_week
    total_conversions = float(df["conversions"].sum())
    rows = []
    for weekday, part in df.groupby("weekday"):
        row = {"weekday": WEEKDAYS[weekday]}
        row.update(_metrics_row(part, total_conversions))
        row["volume_flag"] = (
            "insufficient_data"
            if row["conversions"] < weekday_min_conversions
            else "ok"
        )
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["weekday_no"] = table["weekday"].apply(WEEKDAYS.index)
    table = table.sort_values("weekday_no")
    return table.drop(columns=["weekday_no"]).reset_index(drop=True)


PARTIAL_COLUMNS = ["days_in_month", "days_covered", "is_partial",
                   "is_lagged"]


def _partial_month(month, part_dates, first_active, last_active,
                   data_end, lag_days):
    """days_in_month, days_covered, is_partial, is_lagged."""
    year, number = (int(value) for value in month.split("-"))
    days_in_month = calendar.monthrange(year, number)[1]
    month_start = pd.Timestamp(year, number, 1).date()
    month_end = pd.Timestamp(year, number, days_in_month).date()
    start = max(month_start, first_active)
    end = min(month_end, last_active, data_end)
    days_covered = max((end - start).days + 1, 0)
    lagged = False
    if lag_days > 0:
        lag_start = data_end - timedelta(days=lag_days - 1)
        lagged = any(day >= lag_start for day in part_dates)
    return {"days_in_month": days_in_month,
            "days_covered": days_covered,
            "is_partial": days_covered < days_in_month,
            "is_lagged": lagged}


def monthly_table(day_df, groups, time_groups, lag_days=0):
    """Per campaign and calendar month, from the daily data.

    Adds the partial-month columns (PARTIAL_COLUMNS) after the
    metrics; the metrics themselves are unchanged.
    """
    df = _with_group(_prepare(day_df), groups)
    data_end = df["date"].max() if not df.empty else None
    df = df.loc[df["group"].isin(time_groups)].copy()
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    span = df.groupby("campaign")["date"].agg(["min", "max"])
    rows = []
    for (campaign, month), part in df.groupby(["campaign", "month"]):
        row = {"campaign": campaign, "month": month}
        row.update(_metrics_row(part))
        row.update(_partial_month(
            month, part["date"], span.loc[campaign, "min"],
            span.loc[campaign, "max"], data_end, lag_days))
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values(["campaign", "month"]).reset_index(drop=True)


def timeline_table(day_df, month_df, groups, time_groups,
                   lag_days=0):
    """Monthly table with the monthly-history table appended.

    Rows from the daily data have source "day"; rows from the
    monthly-history table have source "month" and empty
    partial-month columns.
    """
    monthly = monthly_table(day_df, groups, time_groups, lag_days)
    if not monthly.empty:
        monthly = monthly.assign(source="day")
    hist = _with_group(_prepare(month_df), groups)
    hist = hist.loc[hist["group"].isin(time_groups)].copy()
    hist["month"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m")
    rows = []
    for (campaign, month), part in hist.groupby(["campaign", "month"]):
        row = {"campaign": campaign, "month": month}
        row.update(_metrics_row(part))
        row["source"] = "month"
        rows.append(row)
    history = pd.DataFrame(rows)
    combined = pd.concat([monthly, history], ignore_index=True)
    if combined.empty:
        return combined
    columns = ["campaign", "month", "source", "active_days", "spend",
               "clicks", "conversions", "cost_per_conversion",
               "conversion_rate"] + PARTIAL_COLUMNS
    for column in PARTIAL_COLUMNS:
        if column not in combined.columns:
            combined[column] = None
    return combined[columns].sort_values(
        ["campaign", "month", "source"]).reset_index(drop=True)


def split_runs(dates, run_gap_days):
    """Split sorted unique dates into runs.

    A new run starts when the gap with no activity between two
    consecutive active dates is more than run_gap_days.
    Returns a list of (start, end, [dates]).
    """
    unique = sorted(set(pd.to_datetime(pd.Series(dates)).dt.date))
    runs = []
    current = []
    for date in unique:
        if current:
            missing = (date - current[-1]).days - 1
            if missing > run_gap_days:
                runs.append(current)
                current = []
        current.append(date)
    if current:
        runs.append(current)
    return [(run[0], run[-1], run) for run in runs]


def runs_table(day_df, groups, run_groups, run_gap_days,
               volume_rule):
    """Per campaign, activity split into runs.

    Covers the groups in run_groups (see resolve_run_groups).
    """
    wanted = list(run_groups)
    df = _with_group(_prepare(day_df), groups)
    df = df.loc[df["group"].isin(wanted)].copy()
    min_conversions = (volume_rule or {}).get("min_conversions", 0)
    min_days = (volume_rule or {}).get("min_days_active", 0)
    rows = []
    for campaign, part in df.groupby("campaign"):
        for number, (start, end, run_dates) in enumerate(
                split_runs(part["date"], run_gap_days), start=1):
            slice_df = part.loc[part["date"].isin(run_dates)]
            row = {
                "campaign": campaign,
                "group": assign_group(campaign, groups),
                "run_number": number,
                "start": start,
                "end": end,
            }
            row.update(_metrics_row(slice_df))
            row["volume_flag"] = (
                "insufficient_data"
                if row["conversions"] < min_conversions
                or row["active_days"] < min_days
                else "ok"
            )
            rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values(["campaign", "run_number"]).reset_index(
        drop=True)


def write_time_report(report_path, tables, runs, weekday_flagged):
    """Write the time report: counts only, no names, no rows."""
    lines = ["# Time report", ""]
    for label, table in tables:
        lines.append(f"- {label}: {len(table)} rows")
    lines.append(f"- Runs: {len(runs)}")
    lines.append(
        f"- Weekday cells flagged insufficient_data: {weekday_flagged}"
    )
    if not runs.empty:
        lines.append(
            "- Runs flagged insufficient_data: "
            f"{int((runs['volume_flag'] == 'insufficient_data').sum())}"
        )
    lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Compute the time tables and write them and the report."""
    parser = argparse.ArgumentParser(
        description="Compute time patterns, trends and runs."
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
    groups = analysis.get("campaign_groups") or {}
    time_groups = analysis.get("time_groups") or []
    weekday_min = analysis.get("weekday_min_conversions", 0)
    run_gap_days = analysis.get("run_gap_days", 14)
    volume_rule = analysis.get("volume_rule") or {}
    try:
        day_df = pd.read_csv(outputs["day"])
        month_df = pd.read_csv(outputs["month"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the load and clean stages first)",
              file=sys.stderr)
        return 1
    try:
        weekday = weekday_table(day_df, groups, time_groups, weekday_min)
        weekday_core = pooled_weekday_table(
            day_df, groups, time_groups, weekday_min)
        lag_days = int((analysis.get("recent_trend") or {}).get(
            "conversion_lag_days", 0))
        monthly = monthly_table(day_df, groups, time_groups, lag_days)
        timeline = timeline_table(day_df, month_df, groups,
                                  time_groups, lag_days)
        runs = runs_table(day_df, groups,
                          resolve_run_groups(analysis),
                          run_gap_days, volume_rule)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    paths = {
        "weekday": outputs.get(
            "weekday_by_campaign",
            "outputs/results/weekday_by_campaign.csv"),
        "weekday_core": outputs.get(
            "weekday_core", "outputs/results/weekday_core.csv"),
        "monthly": outputs.get(
            "monthly_by_campaign",
            "outputs/results/monthly_by_campaign.csv"),
        "timeline": outputs.get(
            "timeline_by_campaign",
            "outputs/results/timeline_by_campaign.csv"),
        "runs": outputs.get("runs", "outputs/results/runs.csv"),
        "report": outputs.get(
            "time_report", "outputs/reports/time-report.md"),
    }
    for name in ("weekday", "weekday_core", "monthly", "timeline",
                 "runs"):
        path = Path(paths[name])
        path.parent.mkdir(parents=True, exist_ok=True)
    weekday.to_csv(paths["weekday"], index=False)
    weekday_core.to_csv(paths["weekday_core"], index=False)
    monthly.to_csv(paths["monthly"], index=False)
    timeline.to_csv(paths["timeline"], index=False)
    runs.to_csv(paths["runs"], index=False)
    weekday_flagged = int(
        (weekday["volume_flag"] == "insufficient_data").sum()
    ) if not weekday.empty else 0
    write_time_report(paths["report"], [
        ("Weekday rows per campaign", weekday),
        ("Weekday rows pooled (core)", weekday_core),
        ("Monthly rows per campaign", monthly),
        ("Timeline rows per campaign", timeline),
        ("Run rows", runs),
    ], runs, weekday_flagged)

    print(f"weekday rows: {len(weekday)}")
    print(f"monthly rows: {len(monthly)}")
    print(f"timeline rows: {len(timeline)}")
    print(f"runs: {len(runs)}")
    print(f"weekday cells flagged insufficient_data: {weekday_flagged}")
    print(f"wrote: {paths['weekday']}")
    print(f"wrote: {paths['weekday_core']}")
    print(f"wrote: {paths['monthly']}")
    print(f"wrote: {paths['timeline']}")
    print(f"wrote: {paths['runs']}")
    print(f"report: {paths['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
