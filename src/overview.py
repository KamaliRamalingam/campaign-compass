"""Campaign overview table (T3a).

Usage:
    python src/overview.py --config config/restaurant.yaml

Reads the cleaned day and month tables written by src/clean.py
(their paths come from the config) and writes one row per
campaign to outputs/reports/campaign-overview.csv (git-ignored),
so the student can decide which campaigns belong to the
restaurant analysis.

One row per campaign:
- campaign
- first_active_date, last_active_date (from the daily data when
  the campaign has any, otherwise from the monthly data)
- active_days (daily data), active_months (monthly data)
- total_clicks, total_cost, total_conversions (daily range)
- monthly_total_cost, monthly_total_conversions (monthly data)

Campaign selection from the config (analysis.include_campaigns
and analysis.exclude_campaigns) is applied here as well as in
cleaning. Both empty means all campaigns are used.

Only the number of campaigns and where the file was written are
printed, never campaign names or rows.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

try:
    from src.clean import filter_campaigns, load_config
except ImportError:  # running as `python src/overview.py`
    from clean import filter_campaigns, load_config

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
DEFAULT_OUTPUT = "outputs/reports/campaign-overview.csv"


def build_overview(day_df, month_df, include=None, exclude=None):
    """Build one overview row per campaign from the cleaned tables."""
    day = day_df.copy()
    month = month_df.copy()
    day["date"] = pd.to_datetime(day["date"]).dt.date
    month["date"] = pd.to_datetime(month["date"]).dt.date
    day, _ = filter_campaigns(day, include, exclude)
    month, _ = filter_campaigns(month, include, exclude)

    daily = day.groupby("campaign").agg(
        first_active_date=("date", "min"),
        last_active_date=("date", "max"),
        active_days=("date", "nunique"),
        total_clicks=("clicks", "sum"),
        total_cost=("cost", "sum"),
        total_conversions=("conversions", "sum"),
    )
    monthly = month.groupby("campaign").agg(
        monthly_first_active_date=("date", "min"),
        monthly_last_active_date=("date", "max"),
        active_months=("date", "nunique"),
        monthly_total_cost=("cost", "sum"),
        monthly_total_conversions=("conversions", "sum"),
    )
    overview = daily.join(monthly, how="outer").reset_index()
    # First/last active date: daily when present, else monthly.
    overview["first_active_date"] = overview["first_active_date"].fillna(
        overview["monthly_first_active_date"]
    )
    overview["last_active_date"] = overview["last_active_date"].fillna(
        overview["monthly_last_active_date"]
    )
    overview = overview.drop(columns=[
        "monthly_first_active_date", "monthly_last_active_date",
    ])
    for column in ("active_days", "active_months", "total_clicks",
                   "total_cost", "total_conversions",
                   "monthly_total_cost", "monthly_total_conversions"):
        overview[column] = overview[column].fillna(0)
    overview["active_days"] = overview["active_days"].astype("int64")
    overview["active_months"] = overview["active_months"].astype("int64")
    overview["total_clicks"] = overview["total_clicks"].astype("int64")
    overview = overview.sort_values("campaign").reset_index(drop=True)
    return overview[[
        "campaign", "first_active_date", "last_active_date",
        "active_days", "active_months", "total_clicks", "total_cost",
        "total_conversions", "monthly_total_cost",
        "monthly_total_conversions",
    ]]


def main(argv=None):
    """Write the campaign overview table."""
    parser = argparse.ArgumentParser(
        description="Write the campaign overview table."
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
    # clean.py writes cleaned tables to analysis.outputs; fall back
    # to the load outputs if those paths are not in the config.
    day_path = outputs.get("day") or files["day"]["output"]
    month_path = outputs.get("month") or files["month"]["output"]
    try:
        day_df = pd.read_csv(day_path)
        month_df = pd.read_csv(month_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc} (run the load and clean stages first)",
              file=sys.stderr)
        return 1
    overview = build_overview(
        day_df, month_df,
        include=analysis.get("include_campaigns"),
        exclude=analysis.get("exclude_campaigns"),
    )
    out_path = Path(outputs.get("overview", DEFAULT_OUTPUT))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    overview.to_csv(out_path, index=False)
    print(f"campaigns: {len(overview)}")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
