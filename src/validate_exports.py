"""Check raw Google Ads exports against totals shown in the Ads UI.

Only reads raw files, never changes them. Prints and writes only
counts, sums, dates, file sizes and hashes -- never data rows,
title-line text, or any other cell value.

Usage:
    python src/validate_exports.py --config config/validation.yaml \
        --out docs/validation-report.md

Config lists one entry per core file, with actual column names from
that file's header, title lines to skip, and UI totals (ui_expected).
Fill ui_expected in after the Ads exports. Leave a value empty (null)
to skip that one check.

A lower row count than the UI is INFO, not FAIL: the UI may list a
full campaign x period grid, including rows with no activity, while
the downloaded file may only contain rows where something happened.
"""

import argparse
import csv
import hashlib
import sys
from datetime import date, datetime
from pathlib import Path

import yaml


def parse_number(text, decimal=".", thousands=","):
    """Parse one number from a CSV cell.

    Handles thousands separators and currency symbols. Empty counts
    as 0. Raises ValueError on anything else, so a bad value fails
    loudly instead of being silently treated as 0.
    """
    if text is None:
        return 0.0
    value = str(text).strip()
    if not value:
        return 0.0
    value = value.replace("SEK", "").strip()
    if thousands:
        value = value.replace(thousands, "")
    if decimal and decimal != ".":
        value = value.replace(decimal, ".")
    if "%" in value:
        raise ValueError(f"unexpected percentage value: {text!r}")
    return float(value)


def parse_date(text):
    """Parse a date cell. Returns a date, or None if unparseable.

    Accepts YYYY-MM-DD (day files) and "Month YYYY" (month files,
    for example "November 2026", read as the 1st of that month).
    """
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        parsed = datetime.strptime(value, "%B %Y")
        return date(parsed.year, parsed.month, 1)
    except ValueError:
        return None


def load_config(config_path):
    """Read the validation config. Fail clearly if it is bad."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {config_path}")
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or not config.get("files"):
        raise ValueError(
            f"config file {config_path} must contain a non-empty 'files' list"
        )
    return config


def _find_header_index(lines, clicks_column, title_lines):
    """Return the line number of the header row."""
    if isinstance(title_lines, int):
        return title_lines
    for index, line in enumerate(lines[:10]):
        if clicks_column in line:
            return index
    raise ValueError(
        "could not find a header row containing "
        f"the clicks column {clicks_column!r} in the first 10 lines"
    )


def read_file(entry):
    """Read one raw export. Return only counts, sums and dates.

    Raises FileNotFoundError if the file is missing, and ValueError
    naming any configured column missing from the header.
    """
    path = Path(entry["path"])
    if not path.is_file():
        raise FileNotFoundError(f"raw file not found: {entry['path']}")
    raw_bytes = path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    encoding = entry.get("encoding") or "utf-8-sig"
    lines = raw_bytes.decode(encoding).splitlines()
    columns = entry["columns"]
    header_index = _find_header_index(
        lines, columns["clicks"], entry.get("title_lines", 2)
    )
    delimiter = entry.get("delimiter") or ","
    reader = csv.DictReader(lines[header_index:], delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError(f"no header row found in {entry['path']}")
    needed = {k: v for k, v in columns.items() if v}
    missing = [v for v in needed.values() if v not in reader.fieldnames]
    if missing:
        raise ValueError(
            f"missing column(s) {missing} in {entry['path']}; "
            f"header is {reader.fieldnames}"
        )
    decimal = entry.get("decimal") or "."
    thousands = entry.get("thousands")
    if thousands is None:
        thousands = ","
    rows = 0
    total_rows_dropped = 0
    clicks = cost = conversions = 0.0
    dates = []
    campaigns = set()
    for row in reader:
        first = next(iter(row.values()), "") or ""
        if str(first).strip().lower().startswith("total"):
            total_rows_dropped += 1
            continue
        if not any((v or "").strip() for v in row.values()):
            continue
        rows += 1
        clicks += parse_number(row.get(needed["clicks"]), decimal, thousands)
        cost += parse_number(row.get(needed["cost"]), decimal, thousands)
        conversions += parse_number(
            row.get(needed["conversions"]), decimal, thousands
        )
        parsed = parse_date(row.get(needed["date"]))
        if parsed is not None:
            dates.append(parsed)
        if needed.get("campaign"):
            campaigns.add((row.get(needed["campaign"]) or "").strip())
    return {
        "path": entry["path"],
        "kind": entry.get("kind", ""),
        "rows": rows,
        "clicks": clicks,
        "cost": cost,
        "conversions": conversions,
        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
        "campaigns": len(campaigns),
        "sha256": sha256,
        "size": len(raw_bytes),
        "line_count": len(lines),
        "total_rows_dropped": total_rows_dropped,
        "columns": list(reader.fieldnames),
    }


def _status(actual, expected, tolerance, exact=False):
    """Compare one metric. Returns (status, difference or None)."""
    if expected is None:
        return "SKIP", None
    diff = actual - expected
    if exact:
        return ("PASS", diff) if diff == 0 else ("FAIL", diff)
    return ("PASS", diff) if abs(diff) <= tolerance else ("FAIL", diff)


def validate_file(entry, result):
    """Compare one file's counts with ui_expected. Return metric rows."""
    expected = entry.get("ui_expected") or {}
    tolerance = entry.get("tolerance") or {}
    cost_tol = tolerance.get("cost", 0.05)
    conv_tol = tolerance.get("conversions", 0.01)
    metrics = []
    # Rows: lower than UI is INFO, not FAIL (full grid vs active rows).
    exp_rows = expected.get("rows")
    if exp_rows is None:
        metrics.append(("rows", None, result["rows"], None, "SKIP"))
    elif result["rows"] == exp_rows:
        metrics.append(("rows", exp_rows, result["rows"], 0, "PASS"))
    elif result["rows"] < exp_rows:
        metrics.append(
            ("rows", exp_rows, result["rows"], result["rows"] - exp_rows, "INFO")
        )
    else:
        metrics.append(
            ("rows", exp_rows, result["rows"], result["rows"] - exp_rows, "FAIL")
        )
    for name, key, tol, exact in [
        ("clicks", "clicks", 0, True),
        ("cost", "cost", cost_tol, False),
        ("conversions", "conversions", conv_tol, False),
    ]:
        status, diff = _status(result[key], expected.get(name), tol, exact)
        metrics.append((name, expected.get(name), result[key], diff, status))
    for name, key in [("date_start", "date_start"), ("date_end", "date_end")]:
        exp = expected.get(name)
        if exp is None:
            metrics.append((name, None, result[key], None, "SKIP"))
        else:
            exp_date = parse_date(str(exp))
            status = "PASS" if result[key] == exp_date else "FAIL"
            metrics.append((name, exp_date, result[key], None, status))
    metrics.append(
        ("distinct_campaigns", None, result["campaigns"], None, "INFO")
    )
    return metrics


def cross_file_check(results, tolerance=None):
    """Compare day + month totals with monthly totals, within tolerance.

    Tolerance comes from config cross_file_tolerance (absolute values).
    Defaults are the placeholders in config/validation.yaml, for the
    student to confirm: clicks 2, cost 5.00, conversions 0.05.
    Overlap is only reported if the two date ranges actually intersect.
    """
    if tolerance is None:
        tolerance = {"clicks": 2, "cost": 5.00, "conversions": 0.05}
    by_kind = {r["kind"]: r for r in results}
    day = by_kind.get("campaign_by_day")
    month = by_kind.get("campaign_by_month")
    totals = by_kind.get("monthly_totals")
    date_ranges = {
        kind: (r["date_start"], r["date_end"]) for kind, r in by_kind.items()
    }
    if not (day and month and totals):
        return {
            "status": "SKIP",
            "note": "needs all three kinds",
            "rows": [],
            "tolerance": tolerance,
            "date_ranges": date_ranges,
            "overlap": None,
        }
    combined = {
        "clicks": day["clicks"] + month["clicks"],
        "cost": day["cost"] + month["cost"],
        "conversions": day["conversions"] + month["conversions"],
    }
    rows = []
    overall = "PASS"
    for name in ("clicks", "cost", "conversions"):
        tol = tolerance.get(name, 0)
        status, diff = _status(combined[name], totals[name], tol, False)
        if status == "FAIL":
            overall = "FAIL"
        rows.append((name, totals[name], combined[name], diff, status))
    overlap = None
    if (
        day["date_start"] and day["date_end"]
        and month["date_start"] and month["date_end"]
    ):
        start = max(day["date_start"], month["date_start"])
        end = min(day["date_end"], month["date_end"])
        if start <= end:
            overlap = f"{start} to {end}"
    return {
        "status": overall,
        "rows": rows,
        "tolerance": tolerance,
        "date_ranges": date_ranges,
        "overlap": overlap,
    }


def _fmt(value):
    """Format a value for the report. Dates, numbers, or '-' for none."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def write_report(results, cross, out_path, generated_at):
    """Write the markdown report. Only dates, counts and sums appear."""
    lines = []
    lines.append("# Export validation report")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append("")
    overall = "PASS"
    for result in results:
        if any(m[4] == "FAIL" for m in result["metrics"]):
            overall = "FAIL"
    if cross["status"] == "FAIL":
        overall = "FAIL"
    lines.append(f"Overall: **{overall}**")
    lines.append("")
    lines.append(
        "Note: a lower row count than the UI is INFO, not FAIL. "
        "The UI may list a full campaign x period grid, including "
        "rows with no activity, while a downloaded file may only "
        "contain rows where something happened."
    )
    lines.append("")
    for result in results:
        lines.append(f"## {result['kind']} — {result['path']}")
        lines.append("")
        lines.append(f"- Size: {result['size']} bytes")
        lines.append(f"- Lines in file: {result['line_count']}")
        lines.append(f"- SHA-256: {result['sha256']}")
        lines.append(f"- Totals rows dropped: {result['total_rows_dropped']}")
        lines.append(
            f"- Date range in file: {_fmt(result['date_start'])} "
            f"to {_fmt(result['date_end'])}"
        )
        lines.append("")
        lines.append("| Metric | Expected | Actual | Difference | Result |")
        lines.append("|---|---|---|---|---|")
        for name, exp, act, diff, status in result["metrics"]:
            lines.append(
                f"| {name} | {_fmt(exp)} | {_fmt(act)} | "
                f"{_fmt(diff)} | {status} |"
            )
        lines.append("")
    lines.append("## Cross-file check")
    lines.append("")
    lines.append(
        "campaign_by_day + campaign_by_month compared with monthly_totals."
    )
    tol = cross.get("tolerance") or {}
    lines.append(
        "Tolerances used (absolute): "
        f"clicks {_fmt(tol.get('clicks'))}, "
        f"cost {_fmt(tol.get('cost'))}, "
        f"conversions {_fmt(tol.get('conversions'))}."
    )
    for kind, (start, end) in (cross.get("date_ranges") or {}).items():
        lines.append(f"- {kind}: {_fmt(start)} to {_fmt(end)}")
    if cross.get("overlap"):
        lines.append(f"Date ranges overlap: {cross['overlap']}.")
        lines.append(
            "Overlap must be handled in cleaning (deduplicate on "
            "date + campaign) so it is not double-counted."
        )
    else:
        lines.append("No overlap: date ranges do not intersect.")
    lines.append("")
    lines.append(f"Result: **{cross['status']}**")
    lines.append("")
    if cross["rows"]:
        lines.append("| Metric | Monthly totals | Day + month | Difference | Result |")
        lines.append("|---|---|---|---|---|")
        for name, exp, act, diff, status in cross["rows"]:
            lines.append(
                f"| {name} | {_fmt(exp)} | {_fmt(act)} | "
                f"{_fmt(diff)} | {status} |"
            )
        lines.append("")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return overall


def main(argv=None):
    """Run the validation. Exit 1 if any check FAILs."""
    parser = argparse.ArgumentParser(description="Validate raw Ads exports.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    results = []
    failed = False
    for entry in config["files"]:
        try:
            result = read_file(entry)
        except (FileNotFoundError, ValueError) as exc:
            print(f"FAIL {entry.get('path')}: {exc}", file=sys.stderr)
            failed = True
            continue
        result["metrics"] = validate_file(entry, result)
        if any(m[4] == "FAIL" for m in result["metrics"]):
            failed = True
        print(f"{result['kind']}: rows={result['rows']} "
              f"clicks={result['clicks']:.2f} cost={result['cost']:.2f} "
              f"conversions={result['conversions']:.2f}")
        for name, exp, act, diff, status in result["metrics"]:
            print(f"  {name}: {_fmt(exp)} vs {_fmt(act)} -> {status}")
        results.append(result)
    cross = cross_file_check(results, config.get("cross_file_tolerance"))
    if cross["status"] == "FAIL":
        failed = True
    generated_at = datetime.now().isoformat(timespec="seconds")
    overall = write_report(results, cross, args.out, generated_at)
    print(f"Cross-file check: {cross['status']} "
          f"(tolerances: {cross.get('tolerance')})")
    print(f"Overall: {overall} (report: {args.out})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
