"""Tests for the weekday-shift what-if (T12).

All data is tiny and made up. No real data, no real campaign
names.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import what_if  # noqa: E402


def _weekday_core():
    # Made-up pooled core weekday table. Mon-Fri: spend 500,
    # 50 tracked actions (cost 10 each). Sat-Sun: spend 200,
    # 40 tracked actions (cost 5 each).
    rows = []
    for weekday, spend, conversions in [
            ("Mon", 100.0, 10.0), ("Tue", 100.0, 10.0),
            ("Wed", 100.0, 10.0), ("Thu", 100.0, 10.0),
            ("Fri", 100.0, 10.0), ("Sat", 100.0, 20.0),
            ("Sun", 100.0, 20.0)]:
        rows.append({"weekday": weekday, "active_days": 1,
                     "spend": spend, "clicks": 10,
                     "conversions": conversions,
                     "cost_per_conversion": spend / conversions,
                     "conversion_rate": 1.0,
                     "share_of_campaign_conversions": 0.0,
                     "volume_flag": "ok"})
    return pd.DataFrame(rows)


def test_shift_arithmetic():
    row = what_if.what_if_table(_weekday_core(), 0.10)
    assert row["scenario"] == (
        "Move 10% of Mon-Fri spend to Sat-Sun")
    # 10% of 500 Mon-Fri spend = 50 moved.
    assert row["spend_moved"] == pytest.approx(50.0)
    assert row["tracked_actions_before"] == pytest.approx(90.0)
    # The moved spend loses 50 / 10 = 5 weekday actions and
    # gains 50 / 5 = 10 weekend actions: +5, 90 -> 95.
    assert row["delta"] == pytest.approx(5.0)
    assert row["tracked_actions_after"] == pytest.approx(95.0)
    assert row["delta_pct"] == pytest.approx(5.0 / 90.0 * 100)
    assert row["note"] == (
        "linear estimate, not a bound: uses average cost per "
        "action, ignores diminishing returns and campaign mix")
    assert row["display"] == "+5 tracked actions (+5.6%)"


def test_zero_shift_moves_nothing():
    row = what_if.what_if_table(_weekday_core(), 0.0)
    assert row["spend_moved"] == pytest.approx(0.0)
    assert row["delta"] == pytest.approx(0.0)
    assert row["tracked_actions_after"] == pytest.approx(
        row["tracked_actions_before"])


def test_no_weekend_actions_is_an_error():
    table = _weekday_core()
    table.loc[table["weekday"].isin(["Sat", "Sun"]),
              "conversions"] = 0.0
    with pytest.raises(ValueError, match="no Sat-Sun tracked"):
        what_if.what_if_table(table, 0.10)


def test_unknown_weekday_value_is_an_error():
    table = _weekday_core()
    table.loc[table["weekday"] == "Mon", "weekday"] = "Funday"
    with pytest.raises(ValueError, match="Funday"):
        what_if.what_if_table(table, 0.10)


# --- PR 3 M6: variants, range and rounded display --------------

GROUPS = {"core": ["Alpha"], "core_pmax": ["Pmax"]}
VARIANTS = {"core_only": ["core"], "core_and_pmax": ["core", "core_pmax"]}


def _weekday_by_campaign():
    # Alpha (core): the _weekday_core table. Pmax (core_pmax):
    # weekday cost 10, weekend cost 20 (weekends are dearer).
    alpha = _weekday_core().assign(campaign="Alpha")
    rows = []
    for weekday in what_if.WEEKDAYS:
        weekend = weekday in what_if.WEEKEND_SET
        rows.append({"campaign": "Pmax", "weekday": weekday,
                     "spend": 100.0,
                     "conversions": 5.0 if weekend else 10.0})
    return pd.concat([alpha, pd.DataFrame(rows)], ignore_index=True)


def test_display_rounds_without_false_precision():
    assert what_if.display_text(739.32, 2.0624) == \
        "+739 tracked actions (+2.1%)"
    assert what_if.display_text(-0.4, -0.04) == \
        "+0 tracked actions (-0.0%)"
    assert what_if.display_text(-12.6, None) == "-13 tracked actions"


def test_variants_and_range():
    rows = what_if.what_if_variants(
        _weekday_by_campaign(), GROUPS, VARIANTS, 0.10,
        ["core", "core_pmax"])
    assert [row["variant"] for row in rows] == [
        "core_only", "core_and_pmax", "range"]
    core_only, both, span = rows
    # Core only is the Alpha table: +5 actions on 90.
    assert core_only["delta"] == pytest.approx(5.0)
    assert core_only["groups"] == "core"
    # Core + PMax pools both: Mon-Fri 1000 spend / 100 actions
    # (10 each), Sat-Sun 400 / 50 (8 each). 100 moved: -10 +12.5.
    assert both["delta"] == pytest.approx(2.5)
    assert both["groups"] == "core+core_pmax"
    assert span["delta_min"] == pytest.approx(2.5)
    assert span["delta_max"] == pytest.approx(5.0)
    assert span["display"] == (
        "+2 to +5 tracked actions (+1.7% to +5.6%)")
    assert span["note"] == what_if.NOTE


def test_all_groups_variant_equals_the_pooled_table():
    pooled = (_weekday_by_campaign().groupby("weekday", as_index=False)
              [["spend", "conversions"]].sum())
    expected = what_if.what_if_table(pooled, 0.10)
    row = what_if.what_if_variants(
        _weekday_by_campaign(), GROUPS,
        {"all": ["core", "core_pmax"]}, 0.10,
        ["core", "core_pmax"])[0]
    for key in ("spend_moved", "tracked_actions_before", "delta"):
        assert row[key] == pytest.approx(expected[key])


def test_variant_group_outside_time_groups_is_an_error():
    with pytest.raises(ValueError, match="not in time_groups"):
        what_if.what_if_variants(
            _weekday_by_campaign(), GROUPS, VARIANTS, 0.10, ["core"])


def _main(tmp_path, what_if_settings):
    import yaml
    core = tmp_path / "weekday_core.csv"
    by_campaign = tmp_path / "weekday_by_campaign.csv"
    _weekday_core().to_csv(core, index=False)
    _weekday_by_campaign().to_csv(by_campaign, index=False)
    out = tmp_path / "what_if.csv"
    config = {"analysis": {
        "campaign_groups": GROUPS,
        "time_groups": ["core", "core_pmax"],
        "what_if": what_if_settings,
        "outputs": {"weekday_core": str(core),
                    "weekday_by_campaign": str(by_campaign),
                    "what_if_weekday_shift": str(out)}}}
    path = tmp_path / "config.yaml"
    # Keep the variants in config order (safe_dump sorts keys).
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    assert what_if.main(["--config", str(path)]) == 0
    return pd.read_csv(out)


def test_main_default_keeps_one_row(tmp_path, capsys):
    table = _main(tmp_path, {"shift_share": 0.10})
    assert len(table) == 1
    assert "variant" not in table.columns
    assert table["delta"].iloc[0] == pytest.approx(5.0)
    out = capsys.readouterr().out
    assert "(+5 tracked actions (+5.6%))" in out
    assert "Alpha" not in out


def test_main_with_variants_writes_rows_and_range(tmp_path, capsys):
    table = _main(tmp_path, {"shift_share": 0.10,
                             "variants": VARIANTS})
    assert list(table["variant"]) == [
        "core_only", "core_and_pmax", "range"]
    out = capsys.readouterr().out
    assert "range: +2 to +5 tracked actions" in out
    assert "Alpha" not in out and "Pmax" not in out


def test_journey_report_lists_variants(tmp_path):
    from break_even import write_journey_report
    journey = pd.DataFrame([{
        "campaign": "core group", "directions_share": 0.5,
        "calls_share": 0.1, "store_visits_share": 0.0}])
    rows = pd.DataFrame(what_if.what_if_variants(
        _weekday_by_campaign(), GROUPS, VARIANTS, 0.10,
        ["core", "core_pmax"]))
    report = tmp_path / "journey.md"
    write_journey_report(report, journey, rows, "2026-01-01",
                         "2026-01-31", skipped=True,
                         break_even_rows=pd.DataFrame())
    text = report.read_text()
    assert "- core_only (core): spend moved 50; tracked actions " \
        "90 -> 95 (+5 tracked actions (+5.6%))" in text
    assert "- Range across variants: +2 to +5 tracked actions" in text
    assert "linear estimate, not a bound" in text
