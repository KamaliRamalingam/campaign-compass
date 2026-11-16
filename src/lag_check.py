"""Lag check: rerun the recent signals with other lags (PR 2, M3).

Usage:
    python src/lag_check.py --config config/restaurant.yaml

Tracked actions can be reported days after the click, so the
last days of data are undercounted. The pipeline excludes the
last analysis.recent_trend.conversion_lag_days (unverified).
This stage reruns, for each lag in
analysis.recent_trend.lag_check_days (e.g. [3, 7, 14]):

1. the recent-window label (src/recommend.py, when
   recommendation_rules.recent_label is set),
2. the recent trend (src/recent_trend.py),
3. the trend overrides,

with the same functions the pipeline uses, and counts how many
recent trends and final labels differ from the run with the
configured lag. The configured lag is not changed.

Writes, aggregate counts only (no campaign names):
- outputs/results/lag_check.csv: lag, measure, value,
  campaigns. measure is recent_trend or label (counts per
  value), or recent_trend_change / label_change (value
  "old -> new" against the configured lag).
- outputs/reports/lag-check-report.md: the same as tables.

When lag_check_days is not set the stage is skipped with a
message, so other configs are unchanged.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src import recommend
    from src import recent_trend
except ImportError:  # running as `python src/lag_check.py`
    from clean import load_config
    from paths import apply_output_root
    import recommend
    import recent_trend

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
DEFAULT_CSV = "outputs/results/lag_check.csv"
DEFAULT_REPORT = "outputs/reports/lag-check-report.md"


def final_labels(day_df, runs_df, run_recs, day_summary, analysis,
                 lag):
    """(trend table, final recommendations) with one lag.

    Rebuilds the campaign recommendations (recent-window label
    with this lag), the recent trend with this lag, and applies
    the trend overrides, as the pipeline does.
    """
    rules = analysis.get("recommendation_rules") or {}
    settings = dict(analysis.get("recent_trend") or {})
    settings["conversion_lag_days"] = lag
    groups, leave_one_out = recommend.benchmark_settings(rules)
    benchmark = recommend.compute_benchmark(day_summary, groups)
    per_campaign = recommend.benchmarks_by_campaign(
        day_summary, groups, leave_one_out)
    window_days = recommend.recent_label_settings(rules)
    recent_windows = (
        recommend.recent_window_results(
            day_df, day_summary["campaign"], window_days, lag,
            per_campaign, benchmark, rules,
            analysis.get("volume_rule") or {})
        if window_days else None)
    recs = recommend.recommend_campaigns(
        run_recs, day_summary, rules, analysis.get("caveat_text", ""),
        recent_windows)
    trend = recent_trend.compute_recent_trend(
        day_df, runs_df, recs, settings)
    final = recent_trend.apply_to_recommendations(recs, trend, settings)
    return trend, final


def lag_check_table(day_df, runs_df, run_recs, day_summary,
                    analysis, lags):
    """Aggregate rows: counts per value, and changes against the
    configured lag. No campaign names leave this function."""
    configured = int((analysis.get("recent_trend") or {}).get(
        "conversion_lag_days", 0))
    _, reference = final_labels(day_df, runs_df, run_recs,
                                day_summary, analysis, configured)
    reference = reference.set_index("campaign")
    rows = []
    for lag in lags:
        _, final = final_labels(day_df, runs_df, run_recs,
                                day_summary, analysis, int(lag))
        final = final.set_index("campaign")
        for measure in ("recent_trend", "label"):
            for value, count in final[measure].value_counts() \
                    .sort_index().items():
                rows.append({"lag": int(lag), "measure": measure,
                             "value": value, "campaigns": int(count)})
            old = reference[measure].reindex(final.index)
            changed = final.loc[old != final[measure], measure]
            pairs = pd.Series([f"{old[c]} -> {changed[c]}"
                               for c in changed.index], dtype=object)
            for value, count in pairs.value_counts().sort_index() \
                    .items():
                rows.append({"lag": int(lag),
                             "measure": f"{measure}_change",
                             "value": value, "campaigns": int(count)})
            rows.append({"lag": int(lag),
                         "measure": f"{measure}_changes_total",
                         "value": f"vs lag {configured}",
                         "campaigns": int(len(changed))})
    return pd.DataFrame(rows, columns=["lag", "measure", "value",
                                       "campaigns"]), configured


def write_lag_report(path, table, configured, lags, bounds_by_lag):
    """Write the lag-check report: counts only, no names."""
    lines = ["# Lag check report", ""]
    lines.append(
        f"- Configured lag (unchanged): {configured} days. Each row "
        f"compares a lag with the configured lag.")
    lines.append(
        "- Reruns the recent-window label, the recent trend and the "
        "trend overrides; nothing else changes.")
    lines.append("")
    lines.append("| Lag (days) | Recent window | Prior window | "
                 "Trend changes | Label changes |")
    lines.append("|---|---|---|---|---|")
    for lag in lags:
        part = table.loc[table["lag"] == int(lag)]
        total = part.set_index("measure")["campaigns"]
        recent_start, recent_end, prior_start, prior_end = \
            bounds_by_lag[int(lag)]
        lines.append(
            f"| {lag} | {recent_start} to {recent_end} | "
            f"{prior_start} to {prior_end} | "
            f"{int(total.get('recent_trend_changes_total', 0))} | "
            f"{int(total.get('label_changes_total', 0))} |")
    lines.append("")
    for measure, title in (("recent_trend", "Recent trend"),
                           ("label", "Final label")):
        lines.append(f"## {title} per lag")
        lines.append("")
        for lag in lags:
            part = table.loc[(table["lag"] == int(lag))
                             & (table["measure"] == measure)]
            counts = ", ".join(f"{row.value}: {row.campaigns}"
                               for row in part.itertuples())
            lines.append(f"- lag {lag}: {counts or '(none)'}")
            changes = table.loc[(table["lag"] == int(lag))
                                & (table["measure"]
                                   == f"{measure}_change")]
            for row in changes.itertuples():
                lines.append(f"  - {row.value}: {row.campaigns}")
        lines.append("")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Run the lag check and write the table and report."""
    parser = argparse.ArgumentParser(
        description="Rerun the recent signals with other lags.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        config = apply_output_root(load_config(args.config))
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    analysis = config["analysis"]
    lags = (analysis.get("recent_trend") or {}).get("lag_check_days")
    if not lags:
        print("Lag check skipped: analysis.recent_trend.lag_check_days "
              "is not set in the config.")
        return 0
    outputs = analysis.get("outputs") or {}
    try:
        day_df = pd.read_csv(outputs["day"])
        runs_df = pd.read_csv(outputs["runs"])
        run_recs = pd.read_csv(outputs["recommendations_by_run"])
        day_summary = pd.read_csv(outputs["campaign_summary_day"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    try:
        table, configured = lag_check_table(
            day_df, runs_df, run_recs, day_summary, analysis, lags)
        last_date = pd.to_datetime(day_df["date"]).dt.date.max()
        window = (analysis.get("recent_trend") or {})[
            "recent_window_days"]
        bounds_by_lag = {int(lag): recent_trend.window_bounds(
            last_date, window, int(lag)) for lag in lags}
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    csv_out = Path(outputs.get("lag_check", DEFAULT_CSV))
    report_out = Path(outputs.get("lag_check_report", DEFAULT_REPORT))
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(csv_out, index=False)
    write_lag_report(report_out, table, configured, lags,
                     bounds_by_lag)
    print(f"Configured lag: {configured} days (unchanged)")
    for lag in lags:
        part = table.loc[table["lag"] == int(lag)].set_index("measure")
        print(f"  lag {lag}: trend changes "
              f"{int(part.loc['recent_trend_changes_total', 'campaigns'])}"
              f", label changes "
              f"{int(part.loc['label_changes_total', 'campaigns'])}")
    print(f"wrote: {csv_out}")
    print(f"report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
