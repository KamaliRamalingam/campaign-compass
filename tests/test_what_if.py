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
        "upper bound: assumes weekend efficiency holds "
        "at the moved spend")


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
