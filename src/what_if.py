"""What-if: move weekday spend to the weekend (T12).

Usage:
    python src/what_if.py --config config/restaurant.yaml

Reads outputs/results/weekday_core.csv and moves
analysis.what_if.shift_share of Mon-Fri spend to Sat-Sun,
at the current Sat-Sun cost per tracked action. Writes:
- outputs/results/what_if_weekday_shift.csv: one row with
  scenario, spend_moved, tracked_actions_before,
  tracked_actions_after, delta, delta_pct (percent), display
  (rounded: whole actions, one decimal for the percent) and
  the note.

The moved spend buys fewer or more tracked actions depending
on weekend vs weekday efficiency, at today's AVERAGE cost per
action on each side. That is a linear estimate, not a bound:
it ignores diminishing returns (marginal cost is not average
cost, on either side) and campaign mix. Tracked actions are
the Conversions column, renamed so the wording is "tracked
actions" everywhere.

Variants (analysis.what_if.variants, default none): a mapping
{name: [groups]}. Each variant is computed from
outputs/results/weekday_by_campaign.csv, pooling only the
campaigns in those groups (they must be in time_groups), and
gets its own row (variant, groups), followed by one "range"
row with delta_min / delta_max and delta_pct_min /
delta_pct_max across the variants. Without variants the file
has the single row from the pooled weekday_core.csv, as before.

Only the scenario and the numbers are printed, never
campaign names or rows.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src.groups import assign_group
    from src.metrics import _safe_divide
except ImportError:  # running as `python src/what_if.py`
    from clean import load_config
    from paths import apply_output_root
    from groups import assign_group
    from metrics import _safe_divide

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_SET = {"Mon", "Tue", "Wed", "Thu", "Fri"}
WEEKEND_SET = {"Sat", "Sun"}
NOTE = ("linear estimate, not a bound: uses average cost per "
        "action, ignores diminishing returns and campaign mix")
RANGE = "range"


def display_text(delta, delta_pct):
    """Rounded text: whole tracked actions, one-decimal percent."""
    text = f"{round(delta):+d} tracked actions"
    if delta_pct is not None and not pd.isna(delta_pct):
        text += f" ({delta_pct:+.1f}%)"
    return text


def what_if_table(weekday_core, shift_share):
    """One what-if row from the pooled core weekday table.

    weekday_core has one row per weekday with spend and
    conversions. Returns the row as a dict.
    """
    unknown = sorted(
        set(weekday_core["weekday"]) - set(WEEKDAYS))
    if unknown:
        raise ValueError(
            "Unknown weekday value(s) in weekday_core.csv: "
            + ", ".join(unknown))
    weekday = weekday_core.loc[
        weekday_core["weekday"].isin(WEEKDAY_SET)]
    weekend = weekday_core.loc[
        weekday_core["weekday"].isin(WEEKEND_SET)]
    weekday_spend = float(weekday["spend"].sum())
    weekday_actions = float(weekday["conversions"].sum())
    weekend_spend = float(weekend["spend"].sum())
    weekend_actions = float(weekend["conversions"].sum())
    before = float(weekday_core["conversions"].sum())
    spend_moved = shift_share * weekday_spend
    weekday_cpa = _safe_divide(weekday_spend, weekday_actions)
    weekend_cpa = _safe_divide(weekend_spend, weekend_actions)
    if spend_moved and weekday_cpa is None:
        raise ValueError(
            "cannot compute what-if: no Mon-Fri tracked actions")
    if spend_moved and weekend_cpa is None:
        raise ValueError(
            "cannot compute what-if: no Sat-Sun tracked actions")
    lost = (spend_moved / weekday_cpa
            if weekday_cpa is not None else 0.0)
    gained = (spend_moved / weekend_cpa
              if weekend_cpa is not None else 0.0)
    delta = gained - lost
    after = before + delta
    delta_pct = _safe_divide(delta, before)
    delta_pct = delta_pct * 100.0 if delta_pct is not None else None
    return {
        "scenario": (f"Move {shift_share:.0%} of Mon-Fri spend "
                     "to Sat-Sun"),
        "spend_moved": spend_moved,
        "tracked_actions_before": before,
        "tracked_actions_after": after,
        "delta": delta,
        "delta_pct": delta_pct,
        "display": display_text(delta, delta_pct),
        "note": NOTE,
    }


def variant_weekday_table(weekday_by_campaign, groups,
                          variant_groups):
    """Pooled weekday spend and conversions for one variant.

    Sums weekday_by_campaign over the campaigns whose group (from
    the config groups) is in variant_groups.
    """
    table = weekday_by_campaign.copy()
    table["group"] = table["campaign"].apply(
        lambda name: assign_group(name, groups))
    part = table.loc[table["group"].isin(variant_groups)]
    if part.empty:
        raise ValueError(
            "what-if variant has no campaigns in groups "
            + ", ".join(variant_groups))
    return part.groupby("weekday", as_index=False)[
        ["spend", "conversions"]].sum()


def what_if_variants(weekday_by_campaign, groups, variants,
                     shift_share, time_groups):
    """One row per variant plus a range row.

    variants is {name: [groups]}; every group must be in
    time_groups, because weekday_by_campaign only holds those
    campaigns.
    """
    rows = []
    for name, variant_groups in variants.items():
        missing = [group for group in variant_groups
                   if group not in time_groups]
        if missing:
            raise ValueError(
                f"what_if.variants.{name}: group(s) "
                f"{', '.join(missing)} not in time_groups "
                f"({', '.join(time_groups)})")
        row = what_if_table(variant_weekday_table(
            weekday_by_campaign, groups, variant_groups), shift_share)
        rows.append({"variant": name,
                     "groups": "+".join(variant_groups), **row})
    deltas = [row["delta"] for row in rows]
    pcts = [row["delta_pct"] for row in rows
            if row["delta_pct"] is not None]
    low_pct = min(pcts) if pcts else None
    high_pct = max(pcts) if pcts else None
    pct_text = (f" ({low_pct:+.1f}% to {high_pct:+.1f}%)"
                if pcts else "")
    rows.append({
        "variant": RANGE, "groups": "",
        "scenario": rows[0]["scenario"],
        "delta_min": min(deltas), "delta_max": max(deltas),
        "delta_pct_min": low_pct, "delta_pct_max": high_pct,
        "display": (f"{round(min(deltas)):+d} to "
                    f"{round(max(deltas)):+d} tracked actions"
                    f"{pct_text}"),
        "note": NOTE,
    })
    return rows


def main(argv=None):
    """Compute the what-if and write it."""
    parser = argparse.ArgumentParser(
        description="Move weekday spend to the weekend, as a "
                    "what-if."
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
    what_if = analysis.get("what_if") or {}
    shift_share = what_if.get("shift_share")
    if shift_share is None:
        print("ERROR: analysis.what_if.shift_share is not set "
              "in the config", file=sys.stderr)
        return 1
    variants = what_if.get("variants")
    try:
        if variants:
            weekday = pd.read_csv(outputs["weekday_by_campaign"])
        else:
            weekday = pd.read_csv(outputs["weekday_core"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    try:
        if variants:
            rows = what_if_variants(
                weekday, analysis.get("campaign_groups") or {},
                variants, float(shift_share),
                analysis.get("time_groups") or [])
        else:
            rows = [what_if_table(weekday, float(shift_share))]
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    table = pd.DataFrame(rows)
    out = Path(outputs.get(
        "what_if_weekday_shift",
        "outputs/results/what_if_weekday_shift.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    print(f"Scenario: {rows[0]['scenario']}")
    for row in rows:
        prefix = (f"  {row['variant']} ({row['groups']}): "
                  if "variant" in row and row["variant"] != RANGE
                  else "  range: " if "variant" in row else "  ")
        if row.get("variant") == RANGE:
            print(f"{prefix}{row['display']}")
            continue
        print(f"{prefix}spend moved {row['spend_moved']:,.0f}; "
              f"tracked actions {row['tracked_actions_before']:,.0f}"
              f" -> {row['tracked_actions_after']:,.0f} "
              f"({row['display']})")
    print(f"Note: {NOTE}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
