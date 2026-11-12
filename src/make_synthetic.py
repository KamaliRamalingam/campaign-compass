"""Generate the synthetic Company B test data (T7).

Usage:
    python src/make_synthetic.py --config config/synthetic_b.yaml

Writes, into the ignored outputs/synthetic_b/raw/ folder (never
committed), a campaign-by-day file, a campaign-by-month file, a
monthly-totals file and a conversion-by-campaign-month file, in
the same layout as the real exports: 2 title lines, a header,
utf-8-sig, comma delimiter, and a totals row at the bottom. The
files are labelled synthetic in the file name and in the title
line.

The data is generated from scratch with a fixed random seed
(default 42). It is never copied or derived from real rows.
It is deliberately different from the restaurant data:
- different header names ("Campaign name", "Date",
  "Impressions", "Cost (EUR)"), so the column mapping is really
  tested;
- different campaign names with no location in them, and
  different conversion action names, some of them not in the
  action groups (unmapped);
- currency EUR, a shorter date range, no hour data;
- awkward cases: a campaign that stops mid-year (ended), a
  campaign with very low volume, a few missing days, duplicate
  rows, and one gap of more than 14 days.

Only counts, sums and dates are printed, never rows.
generate() returns (totals, metadata): totals are the sums the
validation and conversion configs check against, and metadata
describes the awkward cases (missing days, duplicates, the
ended campaign) so tests can check them.
"""

import argparse
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

SEED = 42
# Campaign names are made up and carry no location.
CAMPAIGNS = ["Blue Spoon", "Green Fork", "Red Kettle",
             "Golden Ladle", "Silver Plate"]
DAY_START = date(2026, 1, 5)
DAY_END = date(2026, 6, 30)
MONTH_START = (2025, 7)
MONTH_END = (2025, 12)
# The ended campaign stops on this date, well before DAY_END.
ENDED_CAMPAIGN = "Green Fork"
ENDED_LAST_DAY = date(2026, 4, 15)
# The low-volume campaign has only this many active days and
# only a few conversions in total.
LOW_VOLUME_CAMPAIGN = "Red Kettle"
LOW_VOLUME_DAYS = 10
# The gap campaign has no rows in this stretch (21 days, more
# than the 14-day run gap).
GAP_CAMPAIGN = "Golden Ladle"
GAP_START = date(2026, 3, 1)
GAP_END = date(2026, 3, 21)
DUPLICATE_ROWS = 6
ACTIONS = [
    ("Get directions", 5, 40),
    ("Phone call", 5, 40),
    ("Menu view", 5, 40),
    ("Website visit", 5, 40),
    ("Table booking", 5, 40),
    ("Order online", 5, 40),
    ("Newsletter signup", 5, 40),
    ("App download", 5, 40),
]


def _days(start, end):
    """Every date from start to end, inclusive."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _months(start, end):
    """Every (year, month) from start to end, inclusive."""
    year, month = start
    while (year, month) <= end:
        yield year, month
        month += 1
        if month > 12:
            year, month = year + 1, 1


def _month_name(year, month):
    """Month as "July 2025", the format the exports use."""
    return date(year, month, 1).strftime("%B %Y")


def _money(value):
    """A cost as it appears in the export: EUR, thousands comma."""
    return f"€{value:,.2f}"


def _day_rows(rng):
    """Day rows (as dicts) plus the missing days per campaign."""
    rows = []
    missing = {}
    all_days = list(_days(DAY_START, DAY_END))
    for campaign in CAMPAIGNS:
        if campaign == ENDED_CAMPAIGN:
            active = [d for d in all_days if d <= ENDED_LAST_DAY]
            missing[campaign] = []
        elif campaign == LOW_VOLUME_CAMPAIGN:
            # Ten active days spread across the range.
            active = [DAY_START + timedelta(days=18 * i)
                      for i in range(LOW_VOLUME_DAYS)]
            missing[campaign] = []
        else:
            active = list(all_days)
            if campaign == GAP_CAMPAIGN:
                gap = [d for d in active if GAP_START <= d <= GAP_END]
                missing[campaign] = gap
                active = [d for d in active if d not in gap]
            # A few more missing days, picked by the seeded random.
            extra = rng.sample(active, 3)
            missing[campaign] = sorted(
                missing.get(campaign, []) + extra)
            active = [d for d in active if d not in extra]
        for day in active:
            if campaign == LOW_VOLUME_CAMPAIGN:
                clicks = rng.randint(2, 6)
                conversions = 1 if rng.random() < 0.3 else 0
            else:
                clicks = rng.randint(8, 60)
                conversions = round(
                    clicks * rng.uniform(0.05, 0.30))
            cost = round(clicks * rng.uniform(2.0, 8.0), 2)
            rows.append({
                "campaign": campaign,
                "date": day.isoformat(),
                "impressions": clicks * rng.randint(8, 20),
                "clicks": clicks,
                "cost": cost,
                "conversions": conversions,
            })
    # Duplicate rows: exact copies of a few rows, appended last.
    duplicates = rng.sample(rows, DUPLICATE_ROWS)
    rows = rows + [dict(row) for row in duplicates]
    return rows, missing


def _month_rows(rng):
    """Month rows (as dicts), one per campaign and month."""
    rows = []
    for year, month in _months(MONTH_START, MONTH_END):
        for campaign in CAMPAIGNS:
            clicks = rng.randint(200, 900)
            cost = round(clicks * rng.uniform(2.0, 8.0), 2)
            conversions = round(clicks * rng.uniform(0.05, 0.30))
            rows.append({
                "campaign": campaign,
                "date": _month_name(year, month),
                "impressions": clicks * rng.randint(8, 20),
                "clicks": clicks,
                "cost": cost,
                "conversions": conversions,
            })
    return rows


def _totals_rows(day_rows, month_rows):
    """Monthly-totals rows: per month, day + month rows summed."""
    per_month = {}
    for row in day_rows + month_rows:
        # Day dates are ISO ("2026-01-05"); month values are
        # "July 2025". Normalise both to (year, month).
        if "-" in row["date"]:
            year, month = int(row["date"][:4]), int(row["date"][5:7])
        else:
            parts = row["date"].split()
            year, month = int(parts[1]), _month_number(parts[0])
        entry = per_month.setdefault((year, month), {
            "clicks": 0, "cost": 0.0, "conversions": 0})
        entry["clicks"] += row["clicks"]
        entry["cost"] += row["cost"]
        entry["conversions"] += row["conversions"]
    rows = []
    for (year, month) in sorted(per_month):
        entry = per_month[(year, month)]
        rows.append({
            "campaign": "",
            "date": _month_name(year, month),
            "impressions": "",
            "clicks": entry["clicks"],
            "cost": round(entry["cost"], 2),
            "conversions": entry["conversions"],
        })
    return rows


def _month_number(name):
    """Month number for an English month name."""
    months = ["January", "February", "March", "April", "May",
              "June", "July", "August", "September", "October",
              "November", "December"]
    return months.index(name) + 1


def _conversion_rows(rng):
    """Conversion rows (as dicts) for every campaign and month."""
    rows = []
    for year, month in _months(MONTH_START, (2026, 6)):
        for campaign in CAMPAIGNS:
            for action, low, high in rng.sample(ACTIONS, 4):
                conversions = rng.randint(low, high)
                all_conversions = round(
                    conversions * rng.uniform(2.0, 6.0), 2)
                rows.append({
                    "campaign": campaign,
                    "month": _month_name(year, month),
                    "action": action,
                    "conversions": conversions,
                    "all_conversions": all_conversions,
                })
    return rows


def _write_csv(path, title_lines, header, rows, totals):
    """Write one export: title lines, header, rows, totals row."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        for line in title_lines:
            handle.write(line + "\n")
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in header})
        writer.writerow(totals)
    return len(rows)


def _day_header():
    return ["Campaign name", "Date", "Impressions", "Clicks",
            "Cost (EUR)", "Conversions"]


def _conversion_header():
    return ["Campaign name", "Month", "Conversion action",
            "Conversions", "All conv."]


def generate(raw_dir, seed=SEED):
    """Generate all four files into raw_dir.

    Returns (totals, metadata). totals holds the sums the
    configs check against; metadata describes the awkward cases.
    """
    rng = random.Random(seed)
    raw_dir = Path(raw_dir)
    day_rows, missing = _day_rows(rng)
    month_rows = _month_rows(rng)
    totals_rows = _totals_rows(day_rows, month_rows)
    conversion_rows = _conversion_rows(rng)

    def day_row(row):
        return {
            "Campaign name": row["campaign"],
            "Date": row["date"],
            "Impressions": row["impressions"],
            "Clicks": row["clicks"],
            "Cost (EUR)": _money(row["cost"]),
            "Conversions": row["conversions"],
        }

    def month_row(row):
        return {
            "Campaign name": row["campaign"],
            "Date": row["date"],
            "Impressions": row["impressions"],
            "Clicks": row["clicks"],
            "Cost (EUR)": _money(row["cost"]),
            "Conversions": row["conversions"],
        }

    def totals_row(row):
        return {
            "Campaign name": "",
            "Date": row["date"],
            "Impressions": "",
            "Clicks": row["clicks"],
            "Cost (EUR)": _money(row["cost"]),
            "Conversions": row["conversions"],
        }

    day_count = _write_csv(
        raw_dir / "synthetic_b_campaign_by_day.csv",
        ["Google Ads - Campaign by day - Synthetic Company B "
         "(test data, not real)",
         "Currency: EUR - Generated with a fixed random seed - "
         "Do not use for decisions"],
        _day_header(),
        [day_row(row) for row in day_rows],
        {"Campaign name": "Total", "Date": "",
         "Impressions": sum(r["impressions"] for r in day_rows),
         "Clicks": sum(r["clicks"] for r in day_rows),
         "Cost (EUR)": _money(sum(r["cost"] for r in day_rows)),
         "Conversions": sum(r["conversions"] for r in day_rows)},
    )
    month_count = _write_csv(
        raw_dir / "synthetic_b_campaign_by_month.csv",
        ["Google Ads - Campaign by month - Synthetic Company B "
         "(test data, not real)",
         "Currency: EUR - Generated with a fixed random seed - "
         "Do not use for decisions"],
        _day_header(),
        [month_row(row) for row in month_rows],
        {"Campaign name": "Total", "Date": "",
         "Impressions": sum(r["impressions"] for r in month_rows),
         "Clicks": sum(r["clicks"] for r in month_rows),
         "Cost (EUR)": _money(sum(r["cost"] for r in month_rows)),
         "Conversions": sum(r["conversions"] for r in month_rows)},
    )
    totals_count = _write_csv(
        raw_dir / "synthetic_b_monthly_totals.csv",
        ["Google Ads - Monthly totals - Synthetic Company B "
         "(test data, not real)",
         "Currency: EUR - Generated with a fixed random seed - "
         "Do not use for decisions"],
        ["Campaign name", "Date", "Clicks", "Cost (EUR)",
         "Conversions"],
        [{**totals_row(row),
          "Cost (EUR)": _money(row["cost"])}
         for row in totals_rows],
        {"Campaign name": "Total", "Date": "",
         "Clicks": sum(r["clicks"] for r in totals_rows),
         "Cost (EUR)": _money(sum(r["cost"] for r in totals_rows)),
         "Conversions": sum(r["conversions"] for r in totals_rows)},
    )
    conversion_count = _write_csv(
        raw_dir / "synthetic_b_conversion_by_campaign_month.csv",
        ["Google Ads - Conversion by campaign and month - "
         "Synthetic Company B (test data, not real)",
         "Currency: EUR - Generated with a fixed random seed - "
         "Do not use for decisions"],
        _conversion_header(),
        [{
            "Campaign name": row["campaign"],
            "Month": row["month"],
            "Conversion action": row["action"],
            "Conversions": row["conversions"],
            "All conv.": row["all_conversions"],
        } for row in conversion_rows],
        {"Campaign name": "Total", "Month": "",
         "Conversion action": "",
         "Conversions": sum(r["conversions"] for r in conversion_rows),
         "All conv.": round(sum(
             r["all_conversions"] for r in conversion_rows), 2)},
    )
    totals = {
        "day": {
            "rows": day_count,
            "clicks": sum(r["clicks"] for r in day_rows),
            "cost": round(sum(r["cost"] for r in day_rows), 2),
            "conversions": sum(r["conversions"] for r in day_rows),
            "date_start": DAY_START.isoformat(),
            "date_end": DAY_END.isoformat(),
        },
        "month": {
            "rows": month_count,
            "clicks": sum(r["clicks"] for r in month_rows),
            "cost": round(sum(r["cost"] for r in month_rows), 2),
            "conversions": sum(r["conversions"] for r in month_rows),
            "date_start": "2025-07-01",
            "date_end": "2025-12-01",
        },
        "totals": {
            "rows": totals_count,
            "clicks": sum(r["clicks"] for r in totals_rows),
            "cost": round(sum(r["cost"] for r in totals_rows), 2),
            "conversions": sum(r["conversions"] for r in totals_rows),
        },
        "conversion": {
            "rows": conversion_count,
            "conversions": sum(r["conversions"] for r in conversion_rows),
            "all_conversions": round(sum(
                r["all_conversions"] for r in conversion_rows), 2),
        },
    }
    metadata = {
        "missing_days": {
            campaign: [d.isoformat() for d in days]
            for campaign, days in missing.items() if days
        },
        "duplicates": DUPLICATE_ROWS,
        "ended_campaign": ENDED_CAMPAIGN,
        "ended_last_day": ENDED_LAST_DAY.isoformat(),
        "low_volume_campaign": LOW_VOLUME_CAMPAIGN,
        "gap_campaign": GAP_CAMPAIGN,
        "gap_start": GAP_START.isoformat(),
        "gap_end": GAP_END.isoformat(),
    }
    return totals, metadata


def main(argv=None):
    """Generate the synthetic files from the client config."""
    parser = argparse.ArgumentParser(
        description="Generate the synthetic Company B test data."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    with Path(args.config).open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    files = (config.get("input") or {}).get("files") or {}
    raw_dir = None
    for kind in ("day", "month", "totals"):
        entry = files.get(kind) or {}
        path = Path(entry.get("path", ""))
        if raw_dir is None:
            raw_dir = path.parent
        elif path.parent != raw_dir:
            print(f"ERROR: {kind} file is not in the same folder "
                  f"as the day file: {path}", file=sys.stderr)
            return 1
    if raw_dir is None:
        print("ERROR: config input.files has no day entry",
              file=sys.stderr)
        return 1
    conversion = ((config.get("conversion_breakdown") or {})
                  .get("file") or {})
    conversion_path = Path(conversion.get("path", ""))
    if conversion_path.parent != raw_dir:
        print("ERROR: conversion file is not in the same folder "
              f"as the day file: {conversion_path}", file=sys.stderr)
        return 1
    totals, metadata = generate(raw_dir, seed=args.seed)
    for kind in ("day", "month", "totals"):
        entry = totals[kind]
        print(f"{kind}: rows={entry['rows']} "
              f"clicks={entry['clicks']} cost={entry['cost']:.2f} "
              f"conversions={entry['conversions']}")
    print(f"conversion: rows={totals['conversion']['rows']} "
          f"conversions={totals['conversion']['conversions']} "
          f"all_conversions={totals['conversion']['all_conversions']:.2f}")
    print(f"duplicates in day file: {metadata['duplicates']}")
    print(f"ended campaign: {metadata['ended_campaign']} "
          f"(last active {metadata['ended_last_day']})")
    print(f"low-volume campaign: {metadata['low_volume_campaign']}")
    print(f"gap: {metadata['gap_campaign']} "
          f"{metadata['gap_start']} to {metadata['gap_end']}")
    print(f"wrote: {raw_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
