"""Tests for scripts/check_no_data.py.

All paths and contents are made up. No real data, no real IDs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_no_data import find_offending, main


def test_clean_list_passes():
    files = [
        ("src/validate_exports.py", "print('hello')\n"),
        ("README.md", "# Project\nNo IDs here.\n"),
        ("data/raw/.gitkeep", ""),
        ("config/validation.yaml", "files: []\n"),
    ]
    assert find_offending(files) == []


def test_tracked_csv_under_data_raw_fails():
    files = [("data/raw/campaign_by_day.csv", "Campaign,Day\n")]
    assert find_offending(files) == ["data/raw/campaign_by_day.csv"]


def test_file_under_outputs_fails():
    files = [("outputs/reports/validation-report.md", "# Report\n")]
    assert find_offending(files) == ["outputs/reports/validation-report.md"]


def test_customer_id_pattern_fails_and_lists_path_only(tmp_path, capsys):
    # A made-up ID-like pattern, not a real customer ID. Built with
    # join() so the literal pattern never appears in this file itself
    # (otherwise the guard would flag its own test file in CI).
    fake_id = "-".join(["123", "456", "7890"])
    files = [("docs/notes.md", f"account {fake_id} was checked\n")]
    assert find_offending(files) == ["docs/notes.md"]
    note = tmp_path / "notes.md"
    note.write_text(f"account {fake_id} was checked\n")
    assert main([str(note)]) == 1
    out = capsys.readouterr().out
    assert "notes.md" in out
    # The matched text itself must never be printed.
    assert fake_id not in out


def test_data_extension_anywhere_fails():
    files = [("notes/export.xlsx", None)]
    assert find_offending(files) == ["notes/export.xlsx"]


def test_main_passes_on_clean_files(tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1\n")
    assert main([str(clean)]) == 0
