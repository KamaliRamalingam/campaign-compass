"""Tests for run.sh and the default validation output path.

All data is tiny and made up, in tmp_path. No real data.
run.sh creates .venv if missing; the test pre-creates a fake .venv
pointing at the current Python, with a no-op pip, so no install
runs over the network.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _make_project(tmp_path, clicks=10, cost=20.0, conversions=4.0):
    """Copy the minimal files run.sh needs into tmp_path."""
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "config").mkdir()
    (project / "data" / "raw").mkdir(parents=True)
    shutil.copy(REPO / "src" / "validate_exports.py",
                project / "src" / "validate_exports.py")
    shutil.copy(REPO / "src" / "load.py",
                project / "src" / "load.py")
    shutil.copy(REPO / "run.sh", project / "run.sh")
    # The copy must be executable: git stores run.sh as 100644 when
    # pushed through the GitHub API (the API tools cannot set the
    # executable bit), so a checked-out copy may not be executable.
    # The test makes its copy executable, as the student does once
    # on her Mac with `chmod +x run.sh`.
    (project / "run.sh").chmod(0o755)
    (project / "requirements.txt").write_text("")
    # Tiny made-up raw file. Campaign name "Alpha" is made up.
    (project / "data" / "raw" / "day.csv").write_text(
        "Made-up title\n"
        "1 Jan 2026 - 2 Jan 2026\n"
        "Campaign,Day,Clicks,Impr.,Cost,Conversions\n"
        "Alpha,2026-01-01,6,100,12.00,2.00\n"
        "Alpha,2026-01-02,4,80,8.00,2.00\n"
        "Total,0,0,0,0\n"
    )
    # Tiny made-up month file, for the load stage in run.sh.
    (project / "data" / "raw" / "month.csv").write_text(
        "Made-up title\n"
        "Made-up date range line\n"
        "Campaign,Month,Clicks,Cost,Conversions\n"
        "Alpha,December 2025,10,20.00,5.00\n"
    )
    (project / "config" / "restaurant.yaml").write_text(
        "input:\n"
        "  title_lines: 2\n"
        "  encoding: utf-8-sig\n"
        "  delimiter: ','\n"
        "  decimal: '.'\n"
        "  thousands: ','\n"
        "  files:\n"
        "    day:\n"
        "      path: data/raw/day.csv\n"
        "      output: outputs/interim/campaign_by_day.csv\n"
        "    month:\n"
        "      path: data/raw/month.csv\n"
        "      output: outputs/interim/campaign_by_month.csv\n"
        "columns:\n"
        "  date: {day: Day, month: Month}\n"
        "  campaign: Campaign\n"
        "  cost: Cost\n"
        "  clicks: Clicks\n"
        "  conversions: Conversions\n"
        "  impressions: null\n"
        "required_columns: [date, campaign, cost, clicks, conversions]\n"
    )
    (project / "config" / "validation.yaml").write_text(
        "cross_file_tolerance: {clicks: 2, cost: 5.00, conversions: 0.05}\n"
        "files:\n"
        "  - path: data/raw/day.csv\n"
        "    kind: campaign_by_day\n"
        "    columns: {clicks: Clicks, cost: Cost, conversions: Conversions, date: Day, campaign: Campaign}\n"
        "    title_lines: 2\n"
        f"    ui_expected: {{rows: 2, clicks: {clicks}, cost: {cost}, conversions: {conversions}, date_start: '2026-01-01', date_end: '2026-01-02'}}\n"
        "    tolerance: {cost: 0.05, conversions: 0.01}\n"
    )
    # Fake .venv: python is the current interpreter, pip does nothing.
    venv_bin = project / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    pip = venv_bin / "pip"
    pip.write_text("#!/bin/sh\nexit 0\n")
    pip.chmod(0o755)
    return project


def test_run_sh_exits_0_and_writes_report(tmp_path):
    project = _make_project(tmp_path)
    result = subprocess.run(
        ["./run.sh"], cwd=project, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = project / "outputs" / "reports" / "validation-report.md"
    assert report.is_file()
    assert "Overall: **PASS**" in report.read_text()
    # The load stage also ran: standardised tables under outputs/.
    assert (project / "outputs" / "interim" / "campaign_by_day.csv").is_file()
    assert (project / "outputs" / "interim" / "campaign_by_month.csv").is_file()
    # No row values in the printed output: the made-up campaign
    # name must not appear, only counts/sums/dates.
    assert "Alpha" not in result.stdout
    assert "Report: outputs/reports/validation-report.md" in result.stdout


def test_run_sh_exits_1_on_mismatch(tmp_path):
    project = _make_project(tmp_path, clicks=999)
    result = subprocess.run(
        ["./run.sh"], cwd=project, capture_output=True, text=True
    )
    assert result.returncode == 1
    report = project / "outputs" / "reports" / "validation-report.md"
    assert report.is_file()


def test_validate_default_output_path(tmp_path):
    project = _make_project(tmp_path)
    result = subprocess.run(
        [sys.executable, "src/validate_exports.py",
         "--config", "config/validation.yaml"],
        cwd=project, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = project / "outputs" / "reports" / "validation-report.md"
    assert report.is_file()
    assert "Overall: **PASS**" in report.read_text()
