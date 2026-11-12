"""Core metrics per campaign (T3).

Usage:
    python src/metrics.py --config config/restaurant.yaml

Reads the cleaned day and month tables written by src/clean.py
(their paths come from the config) and writes, all git-ignored:
- outputs/results/campaign_summary_day.csv: per campaign in the
  daily table: spend, clicks, conversions, active_days, first and
  last active date, cost_per_conversion, conversion_rate, ctr
  (only if impressions exists), group, volume_flag.
- outputs/results/campaign_summary_month.csv: same metrics per
  campaign in the monthly table (spend, clicks, conversions,
  active_months, cost_per_conversion, conversion_rate), but only
  for groups core and monthly_history_only.
- outputs/results/group_summary.csv: one row per group: campaigns,
  spend, clicks, conversions, share of total spend and conversions.
- outputs/reports/metrics-report.md: counts per group and the
  number of campaigns flagged insufficient_data. No rows, only
  counts and sums.

Definitions:
- cost_per_conversion = cost / conversions (empty if conversions
  is 0); conversion_rate = conversions / clicks (empty if clicks
  is 0); ctr = clicks / impressions (only if impressions exists,
  empty if impressions is 0).
- volume_flag = insufficient_data if conversions < min_conversions
  or active_days < min_days_active, otherwise ok.
- Metrics use active days only. Missing days are not filled and
  gaps are not treated as poor performance.

Only group counts are printed, never campaign names or rows.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src.groups import UNGROUPED, assign_group
except ImportError:  # running as `python src/metrics.py`
    from clean import load_config
    from paths import apply_output_root
    from groups import UNGROUPED, assign_group

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
MONTHLY_GROUPS = ("core", "monthly_history_only")


def _safe_divide(numerator, denominator):
    """Divide, returning None when the denominator is 0."""
    if denominator == 0 or pd.isna(denominator):
        return None
    return numerator / denominator


def compute_campaign_metrics(df, groups, volume_rule,
                             active_column="active_days"):
    """Compute the core metrics per campaign from a cleaned table.

    Returns a DataFrame with one row per campaign. The input must
    have date, campaign, clicks, cost and conversions columns.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    has_impressions = "impressions" in df.columns
    grouped = df.groupby("campaign")
    rows = []
    for campaign, part in grouped:
        spend = float(part["cost"].sum())
        clicks = int(part["clicks"].sum())
        conversions = float(part["conversions"].sum())
        active = int(part["date"].nunique())
        impressions = (
            int(part["impressions"].sum()) if has_impressions else None
        )
        row = {
            "campaign": campaign,
            "group": assign_group(campaign, groups),
            "first_active_date": part["date"].min(),
            "last_active_date": part["date"].max(),
            active_column: active,
            "spend": spend,
            "clicks": clicks,
            "conversions": conversions,
            "cost_per_conversion": _safe_divide(spend, conversions),
            "conversion_rate": _safe_divide(conversions, clicks),
        }
        if has_impressions:
            row["impressions"] = impressions
            row["ctr"] = _safe_divide(clicks, impressions)
        min_conversions = (volume_rule or {}).get("min_conversions", 0)
        min_days = (volume_rule or {}).get("min_days_active", 0)
        if conversions < min_conversions or active < min_days:
            row["volume_flag"] = "insufficient_data"
        else:
            row["volume_flag"] = "ok"
        rows.append(row)
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values("campaign").reset_index(drop=True)


def compute_monthly_metrics(df, groups, volume_rule):
    """Monthly metrics, only for core and monthly_history_only."""
    summary = compute_campaign_metrics(
        df, groups, volume_rule, active_column="active_months"
    )
    if summary.empty:
        return summary
    summary = summary.loc[
        summary["group"].isin(MONTHLY_GROUPS)
    ].reset_index(drop=True)
    # The monthly table has no volume flag and no ctr.
    columns = ["campaign", "group", "first_active_date",
               "last_active_date", "active_months", "spend", "clicks",
               "conversions", "cost_per_conversion",
               "conversion_rate"]
    return summary[columns]


def compute_group_summary(day_summary):
    """One row per group from the daily campaign summary."""
    if day_summary.empty:
        return pd.DataFrame(columns=[
            "group", "campaigns", "spend", "clicks", "conversions",
            "share_of_spend", "share_of_conversions",
        ])
    total_spend = float(day_summary["spend"].sum())
    total_conversions = float(day_summary["conversions"].sum())
    grouped = day_summary.groupby("group")
    rows = []
    for group, part in grouped:
        spend = float(part["spend"].sum())
        conversions = float(part["conversions"].sum())
        rows.append({
            "group": group,
            "campaigns": int(len(part)),
            "spend": spend,
            "clicks": int(part["clicks"].sum()),
            "conversions": conversions,
            "share_of_spend": (
                spend / total_spend * 100 if total_spend else 0.0
            ),
            "share_of_conversions": (
                conversions / total_conversions * 100
                if total_conversions else 0.0
            ),
        })
    summary = pd.DataFrame(rows)
    return summary.sort_values("group").reset_index(drop=True)


def write_metrics_report(report_path, day_summary, group_summary):
    """Write the metrics report: counts and sums only, no rows."""
    lines = ["# Metrics report", ""]
    lines.append(f"- Campaigns in daily data: {len(day_summary)}")
    if not day_summary.empty:
        insufficient = int(
            (day_summary["volume_flag"] == "insufficient_data").sum()
        )
        lines.append(
            f"- Campaigns flagged insufficient_data: {insufficient}"
        )
        lines.append(f"- Total spend: {day_summary['spend'].sum():.2f}")
        lines.append(f"- Total clicks: {int(day_summary['clicks'].sum())}")
        lines.append(
            f"- Total conversions: {day_summary['conversions'].sum():.2f}"
        )
    lines.append("")
    lines.append("## Campaigns per group")
    lines.append("")
    for _, row in group_summary.iterrows():
        lines.append(f"- {row['group']}: {int(row['campaigns'])} campaigns")
    lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Compute the metrics and write the result tables and report."""
    parser = argparse.ArgumentParser(
        description="Compute core metrics per campaign."
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
    volume_rule = analysis.get("volume_rule") or {}
    try:
        day_df = pd.read_csv(outputs["day"])
        month_df = pd.read_csv(outputs["month"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the load and clean stages first)",
              file=sys.stderr)
        return 1
    try:
        day_summary = compute_campaign_metrics(
            day_df, groups, volume_rule
        )
        month_summary = compute_monthly_metrics(
            month_df, groups, volume_rule
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    group_summary = compute_group_summary(day_summary)

    day_out = Path(outputs.get(
        "campaign_summary_day", "outputs/results/campaign_summary_day.csv"
    ))
    month_out = Path(outputs.get(
        "campaign_summary_month",
        "outputs/results/campaign_summary_month.csv",
    ))
    group_out = Path(outputs.get(
        "group_summary", "outputs/results/group_summary.csv"
    ))
    report_out = Path(outputs.get(
        "metrics_report", "outputs/reports/metrics-report.md"
    ))
    for path in (day_out, month_out, group_out, report_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    day_summary.to_csv(day_out, index=False)
    month_summary.to_csv(month_out, index=False)
    group_summary.to_csv(group_out, index=False)
    write_metrics_report(report_out, day_summary, group_summary)

    print("Group counts:")
    for _, row in group_summary.iterrows():
        print(f"  {row['group']}: {int(row['campaigns'])} campaigns")
    print(f"campaigns: {len(day_summary)}")
    print(f"wrote: {day_out}")
    print(f"wrote: {month_out}")
    print(f"wrote: {group_out}")
    print(f"report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
