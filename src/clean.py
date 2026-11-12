"""Clean the standardised tables from T1 and report what was done (T2).

Usage:
    python src/clean.py --config config/restaurant.yaml

Reads the standardised day and month tables written by src/load.py
(their paths come from the config), then:
- keeps day rows inside analysis.daily_start..daily_end and month
  rows up to analysis.monthly_end (no monthly start limit);
- drops duplicate rows on (date, campaign), keeping the first;
- flags rows with missing or negative clicks, cost or conversions
  and rows with conversions greater than clicks, and keeps them;
- adds, per campaign, the active-day count and first and last
  active date (for the month table: active-month count and first
  and last active month);
- detects stretches of 30 or more days with no activity at account
  level in the daily data. Missing days are NOT filled: a missing
  day means no activity.

Outputs (paths from the config, all git-ignored):
outputs/interim/clean_day.csv, outputs/interim/clean_month.csv and
outputs/reports/cleaning-report.md. The report holds counts, sums
and dates only — no campaign names and no rows.

Only a short summary is printed: rows before and after per table,
duplicates removed, rows outside range, flagged rows, first and
last active date, and gap periods.
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
# A gap is a stretch with no activity this long or longer, in days.
GAP_DAYS = 30
FLAG_COLUMNS = ("clicks", "cost", "conversions")


def load_config(config_path):
    """Read the YAML config file and return it as a dictionary."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {config_path}")
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or not config.get("analysis"):
        raise ValueError(
            f"config file {config_path} must contain an 'analysis' section"
        )
    return config


def _flag_row(row):
    """Return the flag reasons for one row, as a list (empty = clean)."""
    reasons = []
    for column in FLAG_COLUMNS:
        value = row[column]
        if pd.isna(value):
            reasons.append(f"missing_{column}")
        elif value < 0:
            reasons.append(f"negative_{column}")
    clicks = row["clicks"]
    conversions = row["conversions"]
    if not pd.isna(clicks) and not pd.isna(conversions) \
            and conversions > clicks:
        reasons.append("conversions_gt_clicks")
    return reasons


def detect_gaps(dates, min_gap_days=GAP_DAYS):
    """Find stretches of min_gap_days or more with no activity.

    Takes sorted unique dates. A gap is the run of days between two
    consecutive active dates, when that run is min_gap_days or
    longer. Returns a list of (gap_start, gap_end, gap_days).
    """
    unique = sorted(set(pd.to_datetime(pd.Series(dates)).dt.date))
    gaps = []
    for before, after in zip(unique, unique[1:]):
        missing = (after - before).days - 1
        if missing >= min_gap_days:
            start = before + timedelta(days=1)
            end = after - timedelta(days=1)
            gaps.append((start, end, missing))
    return gaps


def _clean_table(df, start=None, end=None):
    """Shared cleaning for one table.

    Filters to start..end (either bound may be None), drops
    duplicates on (date, campaign) keeping the first, flags rows,
    and adds per-campaign active counts and first/last active
    dates. Returns (cleaned DataFrame, stats dict).
    """
    stats = {"rows_before": len(df)}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    if start is not None:
        start = pd.to_datetime(start).date()
    if end is not None:
        end = pd.to_datetime(end).date()
    in_range = df["date"].apply(
        lambda d: (start is None or d >= start)
        and (end is None or d <= end)
    )
    stats["rows_outside_range"] = int((~in_range).sum())
    df = df.loc[in_range].copy()

    duplicated = df.duplicated(subset=["date", "campaign"], keep="first")
    stats["duplicates_removed"] = int(duplicated.sum())
    df = df.loc[~duplicated].copy()

    df["flags"] = df.apply(lambda row: ";".join(_flag_row(row)), axis=1)
    stats["flagged_rows"] = int((df["flags"] != "").sum())

    # Per-campaign activity: count of active rows and first/last date.
    grouped = df.groupby("campaign")["date"]
    active_count = grouped.transform("size")
    first_active = grouped.transform("min")
    last_active = grouped.transform("max")
    df["active_days"] = active_count
    df["first_active_date"] = first_active
    df["last_active_date"] = last_active
    stats["rows_after"] = len(df)
    stats["first_active_date"] = (
        df["date"].min() if len(df) else None
    )
    stats["last_active_date"] = (
        df["date"].max() if len(df) else None
    )
    stats["sums"] = {
        column: float(df[column].sum(skipna=True))
        for column in FLAG_COLUMNS
    }
    return df, stats


def clean_day(df, daily_start, daily_end):
    """Clean the day table to the daily range."""
    return _clean_table(df, start=daily_start, end=daily_end)


def clean_month(df, monthly_end):
    """Clean the month table up to monthly_end (no start limit)."""
    cleaned, stats = _clean_table(df, start=None, end=monthly_end)
    # For the month table the count is active months, not days.
    cleaned = cleaned.rename(columns={"active_days": "active_months"})
    return cleaned, stats


def write_report(report_path, day_stats, month_stats, gaps):
    """Write the cleaning report: counts, sums and dates only."""
    lines = ["# Cleaning report", ""]
    for label, stats in (("Day table", day_stats),
                         ("Month table", month_stats)):
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"- Rows before: {stats['rows_before']}")
        lines.append(f"- Rows outside range: {stats['rows_outside_range']}")
        lines.append(f"- Duplicates removed: {stats['duplicates_removed']}")
        lines.append(f"- Flagged rows kept: {stats['flagged_rows']}")
        lines.append(f"- Rows after: {stats['rows_after']}")
        lines.append(f"- First active date: {stats['first_active_date']}")
        lines.append(f"- Last active date: {stats['last_active_date']}")
        for column, total in stats["sums"].items():
            lines.append(f"- Total {column}: {total}")
        lines.append("")
    lines.append("## Gaps in daily data (30 or more days, account level)")
    lines.append("")
    if not gaps:
        lines.append("- None")
    for start, end, days in gaps:
        lines.append(f"- {start} to {end}: {days} days")
    lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def print_summary(label, stats):
    """Print only a short summary for one cleaned table."""
    print(f"{label}: rows before: {stats['rows_before']}, "
          f"after: {stats['rows_after']}")
    print(f"  rows outside range: {stats['rows_outside_range']}")
    print(f"  duplicates removed: {stats['duplicates_removed']}")
    print(f"  flagged rows kept: {stats['flagged_rows']}")
    print(f"  first active date: {stats['first_active_date']}, "
          f"last active date: {stats['last_active_date']}")


def main(argv=None):
    """Clean both standardised tables and write the report."""
    parser = argparse.ArgumentParser(
        description="Clean the standardised Ads tables."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    analysis = config["analysis"]
    files = config["input"]["files"]
    outputs = analysis.get("outputs") or {}
    try:
        day_in = Path(files["day"]["output"])
        month_in = Path(files["month"]["output"])
        day_df = pd.read_csv(day_in)
        month_df = pd.read_csv(month_in)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc} (run the load stage first)", file=sys.stderr)
        return 1

    day_clean, day_stats = clean_day(
        day_df, analysis["daily_start"], analysis["daily_end"]
    )
    month_clean, month_stats = clean_month(
        month_df, analysis["monthly_end"]
    )
    gaps = detect_gaps(day_clean["date"])

    day_out = Path(outputs.get("day", "outputs/interim/clean_day.csv"))
    month_out = Path(outputs.get("month",
                                 "outputs/interim/clean_month.csv"))
    report_out = Path(outputs.get("report",
                                  "outputs/reports/cleaning-report.md"))
    day_out.parent.mkdir(parents=True, exist_ok=True)
    month_out.parent.mkdir(parents=True, exist_ok=True)
    day_clean.to_csv(day_out, index=False)
    month_clean.to_csv(month_out, index=False)
    write_report(report_out, day_stats, month_stats, gaps)

    print_summary("day", day_stats)
    print(f"  wrote: {day_out}")
    print_summary("month", month_stats)
    print(f"  wrote: {month_out}")
    if gaps:
        for start, end, days in gaps:
            print(f"  gap: {start} to {end}: {days} days")
    else:
        print("  gaps: none")
    print(f"  report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
