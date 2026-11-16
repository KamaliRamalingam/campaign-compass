"""Acquisition journey per core campaign and core group (T12).

Usage:
    python src/journey.py --config config/restaurant.yaml

Reads outputs/interim/clean_day.csv (daily range), the
conversion mix by campaign and month
(outputs/results/conversion_mix_by_campaign_month.csv) and
the conversion export itself (for the action-level intent
split, through the shared loader in src/conversion_mix.py),
and writes, all git-ignored:
- outputs/results/journey_by_campaign.csv: one row per
  campaign in analysis.time_groups (default core, assigned
  through the config groups) plus one row for those groups
  together (campaign "core group"): spend, clicks, cost_per_click,
  tracked_actions (Conversions), engagement_actions
  (All conv. of the engagement action group),
  directions_share, calls_share, store_visits_share (shares
  of tracked actions, as fractions), tracked_actions_per_click,
  engagement_per_tracked_action, cost_per_tracked_action.

The conversion data is restricted to the months the daily
range touches: the month file's months and the daily file's
months do not overlap in the restaurant account, and some
campaigns have older history that must not count here. The
mix file supplies the engagement actions; the raw export
supplies the intent split, because the mix file has no
per-action rows. Both come from the same export, so they
agree. The intent shares use the monthly conversion export
while tracked actions come from the daily file, so the shares
are approximate where the two sources disagree (the known
small cross-file gap). On the restaurant account the two
sources agree, so the shares are meaningful. On synthetic
Company B they do not: the generator creates conversion rows
independently of daily volume, so Red Kettle (5 tracked
actions) has intent shares above 1. The same effect is
already visible in the T10 output
campaign_summary_intent.csv (share_high_intent 49.2 for Red
Kettle). The journey report counts rows with a share above 1
instead of hiding them.

Intent categories come from
conversion_breakdown.intent_categories in the config. A
category may be empty (share 0.0).

Only counts are printed, never campaign names or rows.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src.conversion_mix import (
        _normalise_action,
        load_breakdown,
    )
    from src.metrics import _safe_divide
    from src.groups import assign_group
except ImportError:  # running as `python src/journey.py`
    from clean import load_config
    from paths import apply_output_root
    from conversion_mix import _normalise_action, load_breakdown
    from metrics import _safe_divide
    from groups import assign_group

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
CORE_GROUP_LABEL = "core group"
ENGAGEMENT_GROUP = "engagement"
INTENT_CATEGORIES = ("directions", "calls", "store_visits")


def months_in_range(start, end):
    """First days of the months from start's month to end's month."""
    months = []
    current = date(start.year, start.month, 1)
    while current <= date(end.year, end.month, 1):
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def build_intent_map(intent_categories):
    """Map normalised action names to their intent category."""
    mapping = {}
    for category, names in (intent_categories or {}).items():
        for name in names or []:
            mapping[_normalise_action(name)] = category
    return mapping


def _row(campaign, spend, clicks, tracked, engagement,
         intent_totals):
    """One journey row from summed values."""
    return {
        "campaign": campaign,
        "spend": spend,
        "clicks": clicks,
        "cost_per_click": _safe_divide(spend, clicks),
        "tracked_actions": tracked,
        "engagement_actions": engagement,
        "directions_share": _safe_divide(
            intent_totals.get("directions", 0.0), tracked),
        "calls_share": _safe_divide(
            intent_totals.get("calls", 0.0), tracked),
        "store_visits_share": _safe_divide(
            intent_totals.get("store_visits", 0.0), tracked),
        "tracked_actions_per_click": _safe_divide(tracked, clicks),
        "engagement_per_tracked_action": _safe_divide(
            engagement, tracked),
        "cost_per_tracked_action": _safe_divide(spend, tracked),
    }


def journey_table(clean_day, month_mix, intent_table,
                  core_campaigns, start, end):
    """Journey rows for each core campaign and the core group.

    clean_day is the cleaned daily table; month_mix is the
    conversion mix by campaign and month; intent_table is the
    parsed conversion export with an intent category per row.
    Only the months the daily range touches are used.
    """
    wanted_months = months_in_range(start, end)
    day = clean_day.loc[
        clean_day["campaign"].isin(core_campaigns)].copy()
    daily = day.groupby("campaign", as_index=False).agg(
        spend=("cost", "sum"),
        clicks=("clicks", "sum"),
        tracked_actions=("conversions", "sum"),
    )
    mix = month_mix.copy()
    mix["month"] = pd.to_datetime(mix["month"]).dt.date
    mix = mix.loc[
        (mix["campaign"].isin(core_campaigns))
        & (mix["month"].isin(wanted_months))
        & (mix["action_group"] == ENGAGEMENT_GROUP)
    ]
    engagement = mix.groupby("campaign")["all_conversions"].sum()
    intent = intent_table.copy()
    intent = intent.loc[
        (intent["campaign"].isin(core_campaigns))
        & (intent["month"].isin(wanted_months))
    ]
    intent_totals = intent.groupby(
        ["campaign", "intent_category"], as_index=False).agg(
        conversions=("conversions", "sum"))
    rows = []
    for _, row in daily.iterrows():
        campaign = row["campaign"]
        part = intent_totals.loc[
            intent_totals["campaign"] == campaign]
        totals = {
            category: float(part.loc[
                part["intent_category"] == category,
                "conversions"].sum())
            for category in INTENT_CATEGORIES
        }
        rows.append(_row(
            campaign,
            float(row["spend"]),
            int(row["clicks"]),
            float(row["tracked_actions"]),
            float(engagement.get(campaign, 0.0)),
            totals,
        ))
    table = pd.DataFrame(rows)
    if not table.empty:
        # The group intent totals come from the intent table,
        # not from the campaign shares, so rounding cannot
        # creep in.
        group_intent = intent.groupby(
            "intent_category")["conversions"].sum()
        group_totals = {
            category: float(group_intent.get(category, 0.0))
            for category in INTENT_CATEGORIES
        }
        group_row = _row(
            CORE_GROUP_LABEL,
            float(table["spend"].sum()),
            int(table["clicks"].sum()),
            float(table["tracked_actions"].sum()),
            float(table["engagement_actions"].sum()),
            group_totals,
        )
        table = pd.concat(
            [table, pd.DataFrame([group_row])], ignore_index=True)
    columns = ["campaign", "spend", "clicks", "cost_per_click",
               "tracked_actions", "engagement_actions",
               "directions_share", "calls_share",
               "store_visits_share", "tracked_actions_per_click",
               "engagement_per_tracked_action",
               "cost_per_tracked_action"]
    return table[columns].sort_values(
        "campaign").reset_index(drop=True)


def main(argv=None):
    """Build the journey table and write it."""
    parser = argparse.ArgumentParser(
        description="Compute the acquisition journey."
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
    section = config.get("conversion_breakdown") or {}
    groups = analysis.get("campaign_groups") or {}
    time_groups = analysis.get("time_groups") or ["core"]
    intent_categories = section.get("intent_categories")
    if intent_categories is None:
        print("ERROR: conversion_breakdown.intent_categories "
              "is not set in the config", file=sys.stderr)
        return 1
    try:
        clean_day = pd.read_csv(outputs["day"])
        month_mix = pd.read_csv(
            section["outputs"]["mix_by_campaign_month"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    # The journey covers the campaigns in analysis.time_groups,
    # assigned through the config groups (default: core).
    try:
        core_campaigns = sorted(
            name for name in clean_day["campaign"].unique()
            if assign_group(name, groups) in time_groups)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not core_campaigns:
        print("ERROR: no campaigns in the daily data belong to "
              f"analysis.time_groups ({', '.join(time_groups)})",
              file=sys.stderr)
        return 1
    try:
        intent_table, _ = load_breakdown(section)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    intent_map = build_intent_map(intent_categories)
    intent_table["intent_category"] = intent_table["action"].apply(
        lambda name: intent_map.get(_normalise_action(name)))
    intent_table = intent_table.loc[
        intent_table["intent_category"].notna()].copy()
    dates = pd.to_datetime(clean_day["date"]).dt.date
    start, end = dates.min(), dates.max()
    try:
        table = journey_table(
            clean_day, month_mix, intent_table, core_campaigns,
            start, end)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out = Path(outputs.get(
        "journey_by_campaign",
        "outputs/results/journey_by_campaign.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    print(f"Daily range: {start} to {end}")
    campaigns = len(table) - 1 if not table.empty else 0
    print(f"Core campaigns with daily data: {campaigns}")
    print(f"Journey rows: {len(table)}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
