"""Break-even visit rate per core campaign (T12).

Usage:
    python src/break_even.py --config config/restaurant.yaml

Reads outputs/results/journey_by_campaign.csv and, only when
analysis.break_even.avg_revenue_per_visit is set, writes:
- outputs/results/break_even.csv: per core campaign,
  cost_per_tracked_action, avg_revenue_per_visit,
  break_even_visit_rate (cost per tracked action divided by
  average revenue per visit), and note. When the rate is
  above 1 the note says "cannot pay for itself at this cost".
  Every note carries the label "illustration: tracked
  actions are not visits".

While avg_revenue_per_visit is null (the owner has not given
a revenue value yet) the output is skipped with a printed
message, and any stale break_even.csv is removed so the
dashboard never shows an outdated table.

Also writes outputs/reports/journey-report.md: counts only
(journey rows, core campaigns, daily range; the what-if
scenario and delta; break-even status). No campaign names.

Only counts are printed, never campaign names or rows.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src.journey import CORE_GROUP_LABEL
    from src.metrics import _safe_divide
except ImportError:  # running as `python src/break_even.py`
    from clean import load_config
    from paths import apply_output_root
    from journey import CORE_GROUP_LABEL
    from metrics import _safe_divide

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
ILLUSTRATION = "illustration: tracked actions are not visits"
CANNOT_PAY = "cannot pay for itself at this cost"


def break_even_table(journey, avg_revenue_per_visit):
    """Break-even rows for the core campaigns in the journey.

    The core-group row is not a campaign and is left out.
    """
    rows = []
    campaigns = journey.loc[
        journey["campaign"] != CORE_GROUP_LABEL]
    for _, row in campaigns.iterrows():
        cost = row["cost_per_tracked_action"]
        rate = _safe_divide(cost, avg_revenue_per_visit)
        note = ILLUSTRATION
        if rate is not None and rate > 1:
            note = f"{CANNOT_PAY}; {ILLUSTRATION}"
        rows.append({
            "campaign": row["campaign"],
            "cost_per_tracked_action": cost,
            "avg_revenue_per_visit": avg_revenue_per_visit,
            "break_even_visit_rate": rate,
            "note": note,
        })
    columns = ["campaign", "cost_per_tracked_action",
               "avg_revenue_per_visit", "break_even_visit_rate",
               "note"]
    return pd.DataFrame(rows, columns=columns)


def write_journey_report(report_path, journey, what_if_row,
                         daily_start, daily_end, skipped,
                         break_even_rows):
    """Write the journey report: counts only, no names."""
    lines = ["# Acquisition journey report", ""]
    campaigns = len(journey) - 1 if not journey.empty else 0
    lines.append(f"- Core campaigns: {campaigns}")
    lines.append(f"- Journey rows: {len(journey)}")
    lines.append(f"- Daily range: {daily_start} to {daily_end}")
    if not journey.empty:
        above_one = int((
            (journey["directions_share"] > 1)
            | (journey["calls_share"] > 1)
            | (journey["store_visits_share"] > 1)
        ).sum())
        lines.append(
            f"- Journey rows with an intent share above 1: "
            f"{above_one} (the monthly conversion export counts "
            f"more conversions than the daily file for a "
            f"low-volume campaign)")
    lines.append("")
    lines.append("## What-if: weekday spend to the weekend")
    lines.append("")
    lines.append(f"- Scenario: {what_if_row['scenario']}")
    lines.append(
        f"- Spend moved: {float(what_if_row['spend_moved']):.2f}")
    lines.append(
        f"- Tracked actions: "
        f"{float(what_if_row['tracked_actions_before']):.2f} -> "
        f"{float(what_if_row['tracked_actions_after']):.2f} "
        f"(delta {float(what_if_row['delta']):+.2f})")
    lines.append(f"- Note: {what_if_row['note']}")
    lines.append("")
    lines.append("## Break-even")
    lines.append("")
    if skipped:
        lines.append(
            "- Skipped: avg_revenue_per_visit is not set in the "
            "config (the owner has not given a revenue value "
            "yet).")
    else:
        lines.append(f"- Break-even rows: {len(break_even_rows)}")
        above = int(
            (break_even_rows["break_even_visit_rate"] > 1).sum()
        ) if not break_even_rows.empty else 0
        lines.append(
            f"- Campaigns above 1 (cannot pay for itself at "
            f"this cost): {above}")
        lines.append(f"- {ILLUSTRATION}.")
    lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Compute the break-even table and the journey report."""
    parser = argparse.ArgumentParser(
        description="Compute the break-even visit rate."
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
    revenue = (analysis.get("break_even") or {}).get(
        "avg_revenue_per_visit")
    try:
        journey = pd.read_csv(outputs["journey_by_campaign"])
        what_if = pd.read_csv(outputs["what_if_weekday_shift"])
        clean_day = pd.read_csv(outputs["day"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    out = Path(outputs.get(
        "break_even", "outputs/results/break_even.csv"))
    report_out = Path(outputs.get(
        "journey_report", "outputs/reports/journey-report.md"))
    dates = pd.to_datetime(clean_day["date"]).dt.date
    daily_start, daily_end = dates.min(), dates.max()
    what_if_row = what_if.iloc[0].to_dict()
    if revenue is None:
        print("Break-even skipped: avg_revenue_per_visit is not "
              "set in the config (the owner has not given a "
              "revenue value yet).")
        if out.is_file():
            out.unlink()
            print(f"Removed stale output: {out}")
        write_journey_report(
            report_out, journey, what_if_row, daily_start,
            daily_end, skipped=True,
            break_even_rows=pd.DataFrame())
        print(f"report: {report_out}")
        return 0
    try:
        revenue = float(revenue)
    except (TypeError, ValueError):
        print("ERROR: analysis.break_even.avg_revenue_per_visit "
              f"is not a number: {revenue!r}", file=sys.stderr)
        return 1
    if revenue <= 0:
        print("ERROR: analysis.break_even.avg_revenue_per_visit "
              "must be above 0", file=sys.stderr)
        return 1
    try:
        table = break_even_table(journey, revenue)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    write_journey_report(
        report_out, journey, what_if_row, daily_start, daily_end,
        skipped=False, break_even_rows=table)
    above = int((table["break_even_visit_rate"] > 1).sum())
    print(f"Break-even rows: {len(table)}")
    print(f"Campaigns above 1 (cannot pay for itself at this "
          f"cost): {above}")
    print(f"wrote: {out}")
    print(f"report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
