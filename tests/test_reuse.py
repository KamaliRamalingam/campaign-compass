"""Tests for the synthetic Company B reuse test (T7).

All data is generated at run time by src/make_synthetic.py
with a fixed seed, in tmp_path. No real data is used.
run.sh creates .venv if missing; the test pre-creates a fake
.venv pointing at the current Python, with a no-op pip, so no
install runs over the network.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO / "src"))
import make_synthetic  # noqa: E402

sys.path.insert(0, str(REPO / "dashboard"))
import data as dashboard_data  # noqa: E402

def _restaurant_campaigns():
    """Every campaign name and prefix in the restaurant config.

    Read at test time so no real campaign name is written in the
    tests; the synthetic outputs must contain none of them.
    """
    config = yaml.safe_load(
        (REPO / "config" / "restaurant.yaml").read_text(encoding="utf-8"))
    groups = config["analysis"]["campaign_groups"]
    names = []
    for members in groups.values():
        if isinstance(members, dict):
            names += list(members.get("exact") or [])
            if members.get("prefix"):
                names.append(members["prefix"])
        else:
            names += list(members or [])
    # Generic words also appear in the synthetic export headers
    # ("Campaign name"), so they are not a sign of leaked names.
    names = [name for name in names
             if str(name).strip().lower() not in {"campaign"}]
    assert names, "no campaign names found in config/restaurant.yaml"
    return names


RESTAURANT_CAMPAIGNS = _restaurant_campaigns()


def _make_project(tmp_path):
    """Copy the files run.sh needs into tmp_path/project."""
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "config").mkdir()
    for name in (REPO / "src").glob("*.py"):
        shutil.copy(name, project / "src" / name.name)
    for name in ("synthetic_b.yaml", "validation_synthetic_b.yaml",
                 "restaurant.yaml"):
        shutil.copy(REPO / "config" / name, project / "config" / name)
    shutil.copy(REPO / "run.sh", project / "run.sh")
    (project / "run.sh").chmod(0o755)
    (project / "requirements.txt").write_text("")
    # A sentinel in the restaurant outputs folder: the synthetic
    # run must leave it exactly as it is.
    sentinel = project / "outputs" / "results" / "sentinel.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("do not touch")
    # Fake .venv: python is the current interpreter, pip does nothing.
    venv_bin = project / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    pip = venv_bin / "pip"
    pip.write_text("#!/bin/sh\nexit 0\n")
    pip.chmod(0o755)
    return project


def _read_csv(path):
    import csv
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_synthetic_pipeline_exits_0(tmp_path):
    project = _make_project(tmp_path)
    sentinel = project / "outputs" / "results" / "sentinel.txt"
    sentinel_mtime = sentinel.stat().st_mtime_ns
    result = subprocess.run(
        ["./run.sh", "--client", "synthetic_b"],
        cwd=project, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: all stages passed" in result.stdout
    # Location and hour analyses are skipped with a message.
    assert "Skipping location analysis" in result.stdout
    assert "Skipping hour analysis" in result.stdout
    # The validation report passed.
    report = (project / "outputs" / "synthetic_b" / "reports"
              / "validation-report.md")
    assert report.is_file()
    assert "Overall: **PASS**" in report.read_text()
    # The reuse report exists and lists the skips.
    reuse = (project / "outputs" / "synthetic_b" / "reports"
             / "reuse-report.md")
    assert reuse.is_file()
    reuse_text = reuse.read_text()
    assert "location: skipped" in reuse_text
    assert "hour: skipped" in reuse_text
    assert "Config keys that had to differ" in reuse_text
    assert "### Keys synthetic_b had to set" in reuse_text
    assert ("### Restaurant-only optional keys not set by "
            "synthetic_b") in reuse_text
    # The low-volume campaign is insufficient_data.
    recs = _read_csv(project / "outputs" / "synthetic_b" / "results"
                     / "recommendations_by_campaign.csv")
    by_campaign = {row["campaign"]: row for row in recs}
    assert by_campaign["Red Kettle"]["label"] == "insufficient_data"
    # The ended campaign has status ended.
    assert by_campaign["Green Fork"]["status_now"] == "ended"
    # Duplicates are removed and counted.
    cleaning = (project / "outputs" / "synthetic_b" / "reports"
                / "cleaning-report.md").read_text()
    assert "Duplicates removed: 6" in cleaning
    clean_day = _read_csv(project / "outputs" / "synthetic_b"
                          / "interim" / "clean_day.csv")
    keys = [(row["date"], row["campaign"]) for row in clean_day]
    assert len(keys) == len(set(keys))
    # The totals row is dropped: no campaign called Total.
    assert not any(row["campaign"] == "Total" for row in clean_day)
    # Missing days are not filled: the generator's missing days
    # for Blue Spoon are absent from the cleaned table.
    _, metadata = make_synthetic.generate(tmp_path / "regen" / "raw")
    missing = metadata["missing_days"]["Blue Spoon"]
    present = {(row["date"], row["campaign"]) for row in clean_day}
    for day in missing:
        assert (day, "Blue Spoon") not in present
    # The restaurant outputs folder is untouched.
    assert sentinel.read_text() == "do not touch"
    assert sentinel.stat().st_mtime_ns == sentinel_mtime
    assert [path.name for path in
            (project / "outputs" / "results").iterdir()] == [
        "sentinel.txt"]
    # No restaurant campaign name appears in any synthetic output.
    for path in (project / "outputs" / "synthetic_b").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in RESTAURANT_CAMPAIGNS:
            assert name not in text, (path, name)


def test_generator_reproduces_config_totals(tmp_path):
    """The seeded generator still matches the committed totals."""
    totals, _ = make_synthetic.generate(tmp_path / "raw")
    project = _make_project(tmp_path)
    validation = yaml.safe_load(
        (project / "config" / "validation_synthetic_b.yaml")
        .read_text())
    by_kind = {entry["kind"]: entry for entry in validation["files"]}
    for kind, key in (("campaign_by_day", "day"),
                      ("campaign_by_month", "month"),
                      ("monthly_totals", "totals")):
        expected = by_kind[kind]["ui_expected"]
        actual = totals[key]
        assert expected["rows"] == actual["rows"]
        assert expected["clicks"] == actual["clicks"]
        assert expected["cost"] == actual["cost"]
        assert expected["conversions"] == actual["conversions"]
    client = yaml.safe_load(
        (project / "config" / "synthetic_b.yaml").read_text())
    expected = client["conversion_breakdown"]["ui_expected"]
    assert expected["conversions"] == totals["conversion"]["conversions"]
    assert expected["all_conversions"] == \
        totals["conversion"]["all_conversions"]


def test_dashboard_lists_synthetic_client(tmp_path):
    """The dashboard finds a client folder under outputs/."""
    outputs = tmp_path / "outputs"
    results = outputs / "synthetic_b" / "results"
    results.mkdir(parents=True)
    (results / "recommendations_by_campaign.csv").write_text(
        "campaign\nBlue Spoon\n")
    assert dashboard_data.list_clients(outputs) == [
        "restaurant", "synthetic_b"]
    config = {"analysis": {"outputs": {
        "recommendations_by_campaign":
            "outputs/results/recommendations_by_campaign.csv"}}}
    paths = dashboard_data.table_paths(
        config, output_root=outputs / "synthetic_b")
    assert paths["recommendations_by_campaign"] == (
        outputs / "synthetic_b" / "results"
        / "recommendations_by_campaign.csv")


def test_split_differing_separates_base_only_keys(tmp_path):
    import reuse_report
    base = {"a": {"x": 1, "only_base": True, "items": ["p", "q"]},
            "same": 5}
    other = {"a": {"x": 2, "items": ["p"]}, "same": 5,
             "only_other": "z"}
    differing, identical = reuse_report.config_diff(base, other)
    had_to_set, base_only = reuse_report.split_differing(
        base, other, differing)
    # A different value, or a key only the other config has.
    assert had_to_set == ["a.x", "only_other"]
    # Keys only the base has: optional, the other leaves unset.
    assert base_only == ["a.items[1]", "a.only_base"]
    assert identical == ["a.items[0]", "same"]
    report = tmp_path / "reuse-report.md"
    reuse_report.write_report(report, [], had_to_set, base_only,
                              identical)
    text = report.read_text()
    assert ("- 4 leaf keys differ from config/restaurant.yaml: 2 "
            "that synthetic_b had to set, and 2 restaurant-only "
            "optional keys") in text
    assert "### Keys synthetic_b had to set (2)" in text
    assert ("### Restaurant-only optional keys not set by "
            "synthetic_b (2)") in text
