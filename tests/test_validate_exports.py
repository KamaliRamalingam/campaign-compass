"""Tests for src/validate_exports.py.

All files here are tiny made-up rows written to tmp_path. No real
client data, no real campaign names, no real rows from the exports.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from validate_exports import (  # noqa: E402
    cross_file_check,
    read_file,
    validate_file,
    write_report,
)

DAY_HEADER = "Campaign,Day,Clicks,Impr.,Cost,Conversions\n"
MONTH_HEADER = "Campaign,Month,Clicks,Impr.,Cost,Conversions\n"
TOTALS_HEADER = "Month,Clicks,Impr.,Cost,Conversions\n"


def _write(path, header, rows):
    # Two title lines, then the header, then data rows, then a totals row.
    text = "Made-up report title\n1 Jan 2026 - 3 Jan 2026\n" + header + "".join(rows)
    text += "Total,0,0,0,0\n"
    Path(path).write_text(text, encoding="utf-8")


def _day_entry(path, rows=None, clicks=10, cost=20.0, conversions=4.0):
    return {
        "path": str(path),
        "kind": "campaign_by_day",
        "columns": {
            "clicks": "Clicks",
            "cost": "Cost",
            "conversions": "Conversions",
            "date": "Day",
            "campaign": "Campaign",
        },
        "title_lines": 2,
        "ui_expected": {
            "rows": rows,
            "clicks": clicks,
            "cost": cost,
            "conversions": conversions,
            "date_start": "2026-01-01",
            "date_end": "2026-01-02",
        },
        "tolerance": {"cost": 0.05, "conversions": 0.01},
    }


def _day_rows():
    return [
        "Alpha,2026-01-01,6,100,12.00,2.00\n",
        "Alpha,2026-01-02,4,80,8.00,2.00\n",
    ]


def test_matching_totals_give_pass(tmp_path):
    path = tmp_path / "day.csv"
    _write(path, DAY_HEADER, _day_rows())
    entry = _day_entry(path, rows=2)
    result = read_file(entry)
    assert result["rows"] == 2
    assert result["clicks"] == 10
    assert result["cost"] == 20.0
    assert result["conversions"] == 4.0
    metrics = dict((m[0], m[4]) for m in validate_file(entry, result))
    assert metrics["rows"] == "PASS"
    assert metrics["clicks"] == "PASS"
    assert metrics["cost"] == "PASS"
    assert metrics["conversions"] == "PASS"
    assert metrics["date_start"] == "PASS"
    assert metrics["date_end"] == "PASS"


def test_missing_row_fails_with_correct_difference(tmp_path):
    path = tmp_path / "day.csv"
    _write(path, DAY_HEADER, _day_rows()[:1])
    entry = _day_entry(path, rows=2)
    result = read_file(entry)
    metrics = {m[0]: m for m in validate_file(entry, result)}
    assert metrics["clicks"][4] == "FAIL"
    assert metrics["clicks"][3] == -4.0
    assert metrics["cost"][3] == -8.0
    assert metrics["conversions"][3] == -2.0


def test_lower_row_count_is_info_not_fail(tmp_path):
    path = tmp_path / "day.csv"
    _write(path, DAY_HEADER, _day_rows())
    # UI lists a full grid (5 rows), file only has the 2 active rows.
    entry = _day_entry(path, rows=5)
    result = read_file(entry)
    metrics = {m[0]: m for m in validate_file(entry, result)}
    assert metrics["rows"][4] == "INFO"
    assert metrics["rows"][3] == -3
    # The sums still match, so no other metric fails.
    assert metrics["clicks"][4] == "PASS"


def _result(kind, rows, clicks, cost, conversions, start, end):
    return {
        "kind": kind,
        "rows": rows,
        "clicks": clicks,
        "cost": cost,
        "conversions": conversions,
        "date_start": start,
        "date_end": end,
    }


def test_cross_file_check_passes_and_fails(tmp_path):
    from datetime import date

    day = _result("campaign_by_day", 2, 10, 20.0, 4.0, date(2026, 1, 1), date(2026, 1, 2))
    month = _result("campaign_by_month", 1, 5, 10.0, 1.0, date(2025, 12, 1), date(2025, 12, 1))
    totals = _result("monthly_totals", 3, 15, 30.0, 5.0, date(2025, 12, 1), date(2026, 1, 2))
    assert cross_file_check([day, month, totals])["status"] == "PASS"
    # Change the monthly totals so the combined total no longer matches.
    bad = _result("monthly_totals", 3, 99, 30.0, 5.0, date(2025, 12, 1), date(2026, 1, 2))
    failed = cross_file_check([day, month, bad])
    assert failed["status"] == "FAIL"
    clicks_row = [r for r in failed["rows"] if r[0] == "clicks"][0]
    assert clicks_row[3] == -84.0


def test_report_contains_no_data_rows_or_title_text(tmp_path):
    path = tmp_path / "day.csv"
    _write(path, DAY_HEADER, _day_rows())
    entry = _day_entry(path, rows=2)
    result = read_file(entry)
    result["metrics"] = validate_file(entry, result)
    out = tmp_path / "report.md"
    write_report([result], {"status": "SKIP", "rows": []}, out, "2026-11-12T12:00:00")
    text = out.read_text(encoding="utf-8")
    # No campaign name, no title line, no data row values in the report.
    assert "Alpha" not in text
    assert "Made-up report title" not in text
    assert "2026-01-01" in text  # dates are allowed
    assert "PASS" in text


def test_missing_column_fails_with_clear_message(tmp_path):
    path = tmp_path / "day.csv"
    _write(path, DAY_HEADER, _day_rows())
    entry = _day_entry(path, rows=2)
    entry["columns"]["clicks"] = "NoSuchColumn"
    try:
        read_file(entry)
    except ValueError as exc:
        assert "NoSuchColumn" in str(exc)
    else:
        raise AssertionError("expected ValueError for a missing column")
