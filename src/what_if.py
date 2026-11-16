"""What-if: move weekday spend to the weekend (T12).

Usage:
    python src/what_if.py --config config/restaurant.yaml

Reads outputs/results/weekday_core.csv and moves
analysis.what_if.shift_share of Mon-Fri spend to Sat-Sun,
at the current Sat-Sun cost per tracked action. Writes:
- outputs/results/what_if_weekday_shift.csv: one row with
  scenario, spend_moved, tracked_actions_before,
  tracked_actions_after, delta, delta_pct (percent),
  note "upper bound: assumes weekend efficiency holds at the
  moved spend".

The moved spend buys fewer or more tracked actions
depending on weekend vs weekday efficiency. The result is
an upper bound, because weekend efficiency may not hold as
spend grows. Tracked actions are the Conversions column,
renamed so the wording is "tracked actions" everywhere.

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
    from src.metrics import _safe_divide
except ImportError:  # running as `python src/what_if.py`
    from clean import load_config
    from paths import apply_output_root
    from metrics import _safe_divide

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_SET = {"Mon", "Tue", "Wed", "Thu", "Fri"}
WEEKEND_SET = {"Sat", "Sun"}
NOTE = ("upper bound: assumes weekend efficiency holds "
        "at the moved spend")


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
        "note": NOTE,
    }


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
    try:
        weekday_core = pd.read_csv(outputs["weekday_core"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    try:
        row = what_if_table(weekday_core, float(shift_share))
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    table = pd.DataFrame([row])
    out = Path(outputs.get(
        "what_if_weekday_shift",
        "outputs/results/what_if_weekday_shift.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    print(f"Scenario: {row['scenario']}")
    print(f"Spend moved: {row['spend_moved']:.2f}")
    if row["delta_pct"] is not None:
        print(f"Tracked actions: {row['tracked_actions_before']:.2f} "
              f"-> {row['tracked_actions_after']:.2f} "
              f"(delta {row['delta']:+.2f}, "
              f"{row['delta_pct']:+.2f}%)")
    else:
        print(f"Tracked actions: {row['tracked_actions_before']:.2f} "
              f"-> {row['tracked_actions_after']:.2f} "
              f"(delta {row['delta']:+.2f})")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
