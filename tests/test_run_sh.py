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
    shutil.copy(REPO / "src" / "clean.py",
                project / "src" / "clean.py")
    shutil.copy(REPO / "src" / "overview.py",
                project / "src" / "overview.py")
    shutil.copy(REPO / "src" / "groups.py",
                project / "src" / "groups.py")
    shutil.copy(REPO / "src" / "metrics.py",
                project / "src" / "metrics.py")
    shutil.copy(REPO / "src" / "time_patterns.py",
                project / "src" / "time_patterns.py")
    shutil.copy(REPO / "src" / "recommend.py",
                project / "src" / "recommend.py")
    shutil.copy(REPO / "src" / "conversion_mix.py",
                project / "src" / "conversion_mix.py")
    shutil.copy(REPO / "src" / "recent_trend.py",
                project / "src" / "recent_trend.py")
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
    # Tiny made-up conversion file, for the conversion stage.
    (project / "data" / "raw" / "conv.csv").write_text(
        "Made-up title\n"
        "Made-up date range line\n"
        "Campaign,Month,Conversion action,Conversions,All conv.\n"
        "Alpha,January 2026,Store visits,2,20\n"
        "Alpha,February 2026,Local actions - Menu views,2,20\n"
        "Total,0,0,0,0\n"
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
        "analysis:\n"
        "  caveat_text: 'Tracked actions only (mainly get-directions requests and phone calls), not bookings or orders. This shows campaign performance, not proof that an offer brought extra customers.'\n"
        "  daily_start: '2023-10-13'\n"
        "  daily_end: '2026-11-12'\n"
        "  monthly_end: '2023-09-30'\n"
        "  include_campaigns: []\n"
        "  exclude_campaigns: []\n"
        "  campaign_groups:\n"
        "    core: [Alpha]\n"
        "  volume_rule: {min_conversions: 10, min_days_active: 14}\n"
        "  time_groups: [core]\n"
        "  weekday_min_conversions: 5\n"
        "  run_gap_days: 14\n"
        "  recommendation_rules:\n"
        "    continue_max_ratio: 1.0\n"
        "    test_max_ratio: 2.0\n"
        "    pause_above_ratio: 2.0\n"
        "    repeat_min_runs: 2\n"
        "    active_window_days: 14\n"
        "    sensitivity_continue_max_ratio: [0.75, 1.0, 1.25, 1.5]\n"
        "    sensitivity_test_max_ratio: [1.5, 2.0, 3.0]\n"
        "  recent_trend:\n"
        "    recent_window_days: 28\n"
        "    conversion_lag_days: 3\n"
        "    worsening_ratio: 1.5\n"
        "    improving_ratio: 0.67\n"
        "    min_tracked_actions_in_window: 30\n"
        "  outputs:\n"
        "    day: outputs/interim/clean_day.csv\n"
        "    month: outputs/interim/clean_month.csv\n"
        "    report: outputs/reports/cleaning-report.md\n"
        "    overview: outputs/reports/campaign-overview.csv\n"
        "    campaign_summary_day: outputs/results/campaign_summary_day.csv\n"
        "    campaign_summary_month: outputs/results/campaign_summary_month.csv\n"
        "    group_summary: outputs/results/group_summary.csv\n"
        "    metrics_report: outputs/reports/metrics-report.md\n"
        "    weekday_by_campaign: outputs/results/weekday_by_campaign.csv\n"
        "    weekday_core: outputs/results/weekday_core.csv\n"
        "    monthly_by_campaign: outputs/results/monthly_by_campaign.csv\n"
        "    timeline_by_campaign: outputs/results/timeline_by_campaign.csv\n"
        "    runs: outputs/results/runs.csv\n"
        "    time_report: outputs/reports/time-report.md\n"
        "    recommendations_by_run: outputs/results/recommendations_by_run.csv\n"
        "    recommendations_by_campaign: outputs/results/recommendations_by_campaign.csv\n"
        "    recommendation_sensitivity: outputs/results/recommendation_sensitivity.csv\n"
        "    recommend_report: outputs/reports/recommend-report.md\n"
        "    recent_trend: outputs/results/recent_trend.csv\n"
        "    weekly_by_campaign: outputs/results/weekly_by_campaign.csv\n"
        "    recent_trend_report: outputs/reports/recent-trend-report.md\n"
        "conversion_breakdown:\n"
        "  file: {path: data/raw/conv.csv, title_lines: 2}\n"
        "  columns: {campaign: Campaign, month: Month, action: Conversion action, conversions: Conversions, all_conversions: 'All conv.'}\n"
        "  ui_expected: {conversions: 4.0, all_conversions: 40.0, tolerance: 0.05}\n"
        "  action_groups:\n"
        "    high_intent: [Store visits]\n"
        "    engagement: [Local actions - Menu views]\n"
        "  outputs:\n"
        "    mix_by_campaign: outputs/results/conversion_mix_by_campaign.csv\n"
        "    mix_by_campaign_month: outputs/results/conversion_mix_by_campaign_month.csv\n"
        "    mix_by_run: outputs/results/conversion_mix_by_run.csv\n"
        "    campaign_summary_intent: outputs/results/campaign_summary_intent.csv\n"
        "    report: outputs/reports/conversion-breakdown-report.md\n"
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
    # The clean stage also ran: cleaned tables and a report.
    assert (project / "outputs" / "interim" / "clean_day.csv").is_file()
    assert (project / "outputs" / "interim" / "clean_month.csv").is_file()
    assert (project / "outputs" / "reports" / "cleaning-report.md").is_file()
    # The overview stage also ran: one row per campaign.
    assert (project / "outputs" / "reports" / "campaign-overview.csv").is_file()
    # The metrics stage also ran: result tables and a report.
    assert (project / "outputs" / "results" / "campaign_summary_day.csv").is_file()
    assert (project / "outputs" / "results" / "campaign_summary_month.csv").is_file()
    assert (project / "outputs" / "results" / "group_summary.csv").is_file()
    assert (project / "outputs" / "reports" / "metrics-report.md").is_file()
    # The time stage also ran: time tables and a report.
    assert (project / "outputs" / "results" / "weekday_by_campaign.csv").is_file()
    assert (project / "outputs" / "results" / "weekday_core.csv").is_file()
    assert (project / "outputs" / "results" / "monthly_by_campaign.csv").is_file()
    assert (project / "outputs" / "results" / "timeline_by_campaign.csv").is_file()
    assert (project / "outputs" / "results" / "runs.csv").is_file()
    assert (project / "outputs" / "reports" / "time-report.md").is_file()
    # The recommend stage also ran: recommendations and a report.
    assert (project / "outputs" / "results" / "recommendations_by_run.csv").is_file()
    assert (project / "outputs" / "results" / "recommendations_by_campaign.csv").is_file()
    assert (project / "outputs" / "results" / "recommendation_sensitivity.csv").is_file()
    assert (project / "outputs" / "reports" / "recommend-report.md").is_file()
    # The conversion stage also ran: mix tables and a report.
    assert (project / "outputs" / "results" / "conversion_mix_by_campaign.csv").is_file()
    assert (project / "outputs" / "results" / "conversion_mix_by_campaign_month.csv").is_file()
    assert (project / "outputs" / "results" / "conversion_mix_by_run.csv").is_file()
    assert (project / "outputs" / "results" / "campaign_summary_intent.csv").is_file()
    assert (project / "outputs" / "reports" / "conversion-breakdown-report.md").is_file()
    # The recent trend stage also ran: trend and weekly tables,
    # a report, and the new columns on the recommendations.
    assert (project / "outputs" / "results" / "recent_trend.csv").is_file()
    assert (project / "outputs" / "results" / "weekly_by_campaign.csv").is_file()
    assert (project / "outputs" / "reports" / "recent-trend-report.md").is_file()
    recs = (project / "outputs" / "results" / "recommendations_by_campaign.csv").read_text()
    assert "recent_trend" in recs.splitlines()[0]
    assert "ratio_vs_run_average" in recs.splitlines()[0]
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
