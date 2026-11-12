"""Conversion breakdown by action (T10).

Usage:
    python src/conversion_mix.py --config config/restaurant.yaml

Reads the conversion-by-campaign-month export described in
config/conversion_breakdown (2 title lines, then a header;
column names come from the config and the run fails naming any
that are missing) and writes, all git-ignored:
- outputs/results/conversion_mix_by_campaign.csv: per campaign,
  conversions by action group and by action, and each group's
  share of the campaign.
- outputs/results/conversion_mix_by_campaign_month.csv: per
  campaign and month, conversions by action group.
- outputs/results/conversion_mix_by_run.csv: for each run in
  outputs/results/runs.csv, the conversions by group from the
  months the run touches, with approximate = true when the run
  starts or ends mid-month.
- outputs/results/campaign_summary_intent.csv: per campaign in
  the daily range, using spend from outputs/interim/clean_day.csv:
  spend, conversions, high_intent_conversions,
  engagement_conversions, share_high_intent,
  cost_per_high_intent_conversion. The intent conversions come
  from the breakdown rows in the months the daily range touches.
- outputs/reports/conversion-breakdown-report.md: validation
  result, counts, and the list of actions with their group and
  total. Action names are fine. No campaign names.

Validation: the file totals for Conversions and All conv. are
checked against conversion_breakdown.ui_expected (tolerance in
the config). PASS or FAIL is printed and written in the report;
a FAIL makes this stage exit 1.

Action groups come from the config. Names are compared
case-insensitively, and hyphen, en dash and em dash count as
equal. Any other action goes to "unmapped" and is reported,
never dropped.

Wording: conversions in this account are Google local actions
and calls, not bookings or orders. The outputs say "tracked
actions", never "bookings" or "orders".

Only PASS/FAIL and group totals are printed, never campaign
names or rows.
"""

import argparse
import calendar
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src.groups import assign_group
except ImportError:  # running as `python src/conversion_mix.py`
    from clean import load_config
    from paths import apply_output_root
    from groups import assign_group

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
UNMAPPED = "unmapped"
DASHES = ("\u2013", "\u2014")  # en dash, em dash


def parse_month(value):
    """Parse a month value to the first day of that month.

    Accepts "June 2009" (%B %Y) and ISO dates (2024-01-01).
    Anything else raises ValueError naming the value.
    """
    text = str(value).strip()
    for fmt in ("%B %Y", "%Y-%m-%d", "%Y-%m"):
        try:
            from datetime import datetime
            parsed = datetime.strptime(text, fmt)
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            continue
    raise ValueError(
        f"cannot parse month value {value!r}: expected "
        f"'June 2009' or an ISO date"
    )


def _normalise_action(name):
    """Lower-case an action name, treating all dash types equal."""
    text = str(name).strip().lower()
    for dash in DASHES:
        text = text.replace(dash, "-")
    return text


def build_action_map(action_groups):
    """Map normalised action names to their group."""
    mapping = {}
    for group, names in (action_groups or {}).items():
        for name in names:
            mapping[_normalise_action(name)] = group
    return mapping


def assign_action_group(action, action_map):
    """Assign one action to a group, or "unmapped"."""
    return action_map.get(_normalise_action(action), UNMAPPED)


def load_breakdown(section):
    """Load the conversion export. Returns (table, dropped).

    Fails naming any configured column that is missing from the
    header. Rows whose first cell starts with "Total" are dropped
    and counted.
    """
    columns = section["columns"]
    path = section["file"]["path"]
    title_lines = section["file"].get("title_lines", 2)
    try:
        raw = pd.read_csv(
            path, skiprows=title_lines, encoding="utf-8-sig",
            delimiter=",", thousands=",", dtype=str, keep_default_na=False,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"conversion export not found: {path}") from exc
    missing = [
        logical for logical, header in columns.items()
        if header not in raw.columns
    ]
    if missing:
        raise ValueError(
            "Missing required column(s) in the conversion export: "
            + ", ".join(
                f"{logical} ({columns[logical]!r})"
                for logical in missing
            )
        )
    first = raw.iloc[:, 0].astype(str)
    dropped = int(first.str.startswith("Total").sum())
    raw = raw.loc[~first.str.startswith("Total")].copy()
    table = pd.DataFrame({
        "campaign": raw[columns["campaign"]].astype(str).str.strip(),
        "month": raw[columns["month"]].apply(parse_month),
        "action": raw[columns["action"]].astype(str).str.strip(),
        "conversions": pd.to_numeric(
            raw[columns["conversions"]].str.replace(",", ""),
            errors="coerce"),
        "all_conversions": pd.to_numeric(
            raw[columns["all_conversions"]].str.replace(",", ""),
            errors="coerce"),
    })
    if table["conversions"].isna().any() \
            or table["all_conversions"].isna().any():
        raise ValueError(
            "conversion export has non-numeric Conversions or "
            "All conv. values"
        )
    return table, dropped


def validate_totals(table, ui_expected):
    """Check the file totals against ui_expected.

    Returns {column: "PASS"/"FAIL"} for Conversions and All conv.
    """
    tolerance = ui_expected.get("tolerance", 0.05)
    result = {}
    for logical, key in (("conversions", "conversions"),
                         ("all_conversions", "all_conversions")):
        total = float(table[logical].sum())
        expected = float(ui_expected[key])
        result[logical] = (
            "PASS" if abs(total - expected) <= tolerance else "FAIL"
        )
    return result


def mix_by_campaign(table):
    """Per campaign, conversions by action group and by action."""
    grouped = table.groupby(
        ["campaign", "group", "action_group", "action"],
        as_index=False).agg(
        conversions=("conversions", "sum"),
        all_conversions=("all_conversions", "sum"),
    )
    group_totals = grouped.groupby(
        ["campaign", "action_group"], as_index=False).agg(
        group_conversions=("conversions", "sum"),
        group_all_conversions=("all_conversions", "sum"),
    )
    merged = grouped.merge(
        group_totals, on=["campaign", "action_group"])
    campaign_totals = merged.groupby("campaign", as_index=False).agg(
        campaign_conversions=("conversions", "sum"),
        campaign_all_conversions=("all_conversions", "sum"),
    )
    merged = merged.merge(campaign_totals, on="campaign")
    merged["share_group_conversions"] = (
        merged["group_conversions"]
        / merged["campaign_conversions"])
    merged["share_group_all_conversions"] = (
        merged["group_all_conversions"]
        / merged["campaign_all_conversions"])
    columns = ["campaign", "group", "action_group", "action",
               "conversions", "all_conversions", "group_conversions",
               "group_all_conversions", "share_group_conversions",
               "share_group_all_conversions"]
    return merged[columns].sort_values(
        ["campaign", "action_group", "action"]).reset_index(drop=True)


def mix_by_campaign_month(table):
    """Per campaign and month, conversions by action group."""
    grouped = table.groupby(
        ["campaign", "group", "month", "action_group"],
        as_index=False).agg(
        conversions=("conversions", "sum"),
        all_conversions=("all_conversions", "sum"),
    )
    month_totals = grouped.groupby(
        ["campaign", "month"], as_index=False).agg(
        month_conversions=("conversions", "sum"),
        month_all_conversions=("all_conversions", "sum"),
    )
    merged = grouped.merge(month_totals, on=["campaign", "month"])
    merged["share_month_conversions"] = (
        merged["conversions"] / merged["month_conversions"])
    merged["share_month_all_conversions"] = (
        merged["all_conversions"] / merged["month_all_conversions"])
    columns = ["campaign", "group", "month", "action_group",
               "conversions", "all_conversions",
               "share_month_conversions",
               "share_month_all_conversions"]
    return merged[columns].sort_values(
        ["campaign", "month", "action_group"]).reset_index(drop=True)


def _months_touched(start, end):
    """First days of the months a run touches."""
    months = []
    current = date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def mix_by_run(month_mix, runs_df):
    """Per run, conversions by group from the months it touches.

    approximate is true when the run starts or ends mid-month.
    """
    rows = []
    for _, run in runs_df.iterrows():
        start = pd.to_datetime(run["start"]).date()
        end = pd.to_datetime(run["end"]).date()
        last_day = calendar.monthrange(end.year, end.month)[1]
        approximate = start.day != 1 or end.day != last_day
        touched = _months_touched(start, end)
        part = month_mix.loc[
            (month_mix["campaign"] == run["campaign"])
            & (month_mix["month"].isin(touched))
        ]
        for action_group, group_rows in part.groupby("action_group"):
            rows.append({
                "campaign": run["campaign"],
                "group": run["group"],
                "run_number": int(run["run_number"]),
                "start": run["start"],
                "end": run["end"],
                "action_group": action_group,
                "conversions": float(group_rows["conversions"].sum()),
                "all_conversions": float(
                    group_rows["all_conversions"].sum()),
                "approximate": approximate,
            })
    return pd.DataFrame(rows)


def campaign_summary_intent(clean_day, table, daily_start, daily_end):
    """Per campaign in the daily range: spend and intent mix.

    Spend and conversions come from clean_day.csv. The intent
    conversions come from the breakdown rows in the months the
    daily range touches.
    """
    day = clean_day.groupby("campaign", as_index=False).agg(
        spend=("cost", "sum"),
        conversions=("conversions", "sum"),
    )
    start_month = date(daily_start.year, daily_start.month, 1)
    end_month = date(daily_end.year, daily_end.month, 1)
    in_range = table.loc[
        (table["month"] >= start_month)
        & (table["month"] <= end_month)
    ]
    intent = in_range.groupby(
        ["campaign", "action_group"], as_index=False).agg(
        group_conversions=("conversions", "sum"))
    pivoted = intent.pivot(
        index="campaign", columns="action_group",
        values="group_conversions").fillna(0.0)
    merged = day.copy()
    for group in ("high_intent", "engagement", UNMAPPED):
        if group in pivoted:
            merged[f"{group}_conversions"] = merged["campaign"].map(
                pivoted[group]).fillna(0.0)
        else:
            merged[f"{group}_conversions"] = 0.0
    merged["share_high_intent"] = (
        merged["high_intent_conversions"] / merged["conversions"])
    merged["cost_per_high_intent_conversion"] = merged.apply(
        lambda row: (
            row["spend"] / row["high_intent_conversions"]
            if row["high_intent_conversions"] > 0 else None
        ), axis=1)
    columns = ["campaign", "spend", "conversions",
               "high_intent_conversions", "engagement_conversions",
               "unmapped_conversions", "share_high_intent",
               "cost_per_high_intent_conversion"]
    return merged[columns].sort_values("campaign").reset_index(
        drop=True)


def write_conversion_report(report_path, validation, table, dropped):
    """Write the breakdown report: validation, counts, actions.

    Action names are fine. No campaign names.
    """
    lines = ["# Conversion breakdown report", ""]
    lines.append("## Validation")
    lines.append("")
    lines.append(
        f"- Conversions: {validation['conversions']} "
        f"(total {float(table['conversions'].sum()):.2f})")
    lines.append(
        f"- All conv.: {validation['all_conversions']} "
        f"(total {float(table['all_conversions'].sum()):.2f})")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Rows: {len(table)}")
    lines.append(f"- Dropped Total rows: {dropped}")
    lines.append(
        f"- Distinct campaigns: {table['campaign'].nunique()}")
    lines.append(f"- Distinct actions: {table['action'].nunique()}")
    lines.append(
        f"- Month range: {table['month'].min()} to "
        f"{table['month'].max()}")
    lines.append("")
    lines.append("## Conversions by action group")
    lines.append("")
    for group, part in table.groupby("action_group"):
        lines.append(
            f"- {group}: {float(part['conversions'].sum()):.2f} "
            f"conversions, "
            f"{float(part['all_conversions'].sum()):.2f} all conv.")
    lines.append("")
    lines.append("## Actions")
    lines.append("")
    actions = table.groupby(
        ["action", "action_group"], as_index=False).agg(
        conversions=("conversions", "sum"),
        all_conversions=("all_conversions", "sum"),
    ).sort_values("conversions", ascending=False)
    for _, row in actions.iterrows():
        lines.append(
            f"- {row['action']} ({row['action_group']}): "
            f"{float(row['conversions']):.2f} conversions, "
            f"{float(row['all_conversions']):.2f} all conv.")
    lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Build the conversion breakdown and write its outputs."""
    parser = argparse.ArgumentParser(
        description="Break down conversions by action."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        config = apply_output_root(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    section = config.get("conversion_breakdown") or {}
    analysis = config["analysis"]
    outputs = section.get("outputs") or {}
    try:
        table, dropped = load_breakdown(section)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    action_map = build_action_map(section.get("action_groups"))
    table["action_group"] = table["action"].apply(
        lambda name: assign_action_group(name, action_map))
    table["group"] = table["campaign"].apply(
        lambda name: assign_group(
            name, analysis.get("campaign_groups")))
    validation = validate_totals(table, section["ui_expected"])
    try:
        runs_df = pd.read_csv(analysis["outputs"]["runs"])
        clean_day = pd.read_csv(analysis["outputs"]["day"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    month_mix = mix_by_campaign_month(table)
    campaign_mix = mix_by_campaign(table)
    run_mix = mix_by_run(month_mix, runs_df)
    from datetime import datetime
    daily_start = datetime.strptime(
        analysis["daily_start"], "%Y-%m-%d").date()
    daily_end = datetime.strptime(
        analysis["daily_end"], "%Y-%m-%d").date()
    intent = campaign_summary_intent(
        clean_day, table, daily_start, daily_end)

    mix_out = Path(outputs.get(
        "mix_by_campaign",
        "outputs/results/conversion_mix_by_campaign.csv"))
    month_out = Path(outputs.get(
        "mix_by_campaign_month",
        "outputs/results/conversion_mix_by_campaign_month.csv"))
    run_out = Path(outputs.get(
        "mix_by_run", "outputs/results/conversion_mix_by_run.csv"))
    intent_out = Path(outputs.get(
        "campaign_summary_intent",
        "outputs/results/campaign_summary_intent.csv"))
    report_out = Path(outputs.get(
        "report", "outputs/reports/conversion-breakdown-report.md"))
    for path in (mix_out, month_out, run_out, intent_out, report_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    campaign_mix.to_csv(mix_out, index=False)
    month_mix.to_csv(month_out, index=False)
    run_mix.to_csv(run_out, index=False)
    intent.to_csv(intent_out, index=False)
    write_conversion_report(report_out, validation, table, dropped)

    overall = ("PASS" if all(value == "PASS"
                             for value in validation.values())
               else "FAIL")
    print(f"Conversion breakdown: {overall}")
    for logical in ("conversions", "all_conversions"):
        print(f"  {logical}: {validation[logical]}")
    print("Conversions by action group:")
    for group, part in table.groupby("action_group"):
        print(f"  {group}: {float(part['conversions'].sum()):.2f}")
    print(f"wrote: {mix_out}")
    print(f"wrote: {month_out}")
    print(f"wrote: {run_out}")
    print(f"wrote: {intent_out}")
    print(f"report: {report_out}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
