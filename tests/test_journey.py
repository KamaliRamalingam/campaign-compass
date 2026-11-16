"""Tests for the acquisition journey (T12).

All data is tiny and made up. No real data, no real campaign
names.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import journey  # noqa: E402


def _clean_day():
    # Made-up daily rows. Alpha and Beta are core; Gamma is not.
    return pd.DataFrame([
        {"date": "2026-01-05", "campaign": "Alpha", "cost": 100.0,
         "clicks": 50, "conversions": 10.0},
        {"date": "2026-01-06", "campaign": "Alpha", "cost": 100.0,
         "clicks": 50, "conversions": 10.0},
        {"date": "2026-01-05", "campaign": "Beta", "cost": 50.0,
         "clicks": 25, "conversions": 5.0},
        {"date": "2026-01-05", "campaign": "Gamma", "cost": 999.0,
         "clicks": 99, "conversions": 9.0},
    ])


def _month_mix():
    # Made-up mix by campaign and month. December 2025 and
    # February 2026 are outside the daily range (January 2026)
    # and must not count.
    return pd.DataFrame([
        {"campaign": "Alpha", "group": "core",
         "month": "2026-01-01", "action_group": "engagement",
         "conversions": 10.0, "all_conversions": 400.0},
        {"campaign": "Alpha", "group": "core",
         "month": "2025-12-01", "action_group": "engagement",
         "conversions": 99.0, "all_conversions": 999.0},
        {"campaign": "Alpha", "group": "core",
         "month": "2026-02-01", "action_group": "engagement",
         "conversions": 88.0, "all_conversions": 888.0},
        {"campaign": "Beta", "group": "core",
         "month": "2026-01-01", "action_group": "engagement",
         "conversions": 5.0, "all_conversions": 100.0},
        {"campaign": "Gamma", "group": "core",
         "month": "2026-01-01", "action_group": "engagement",
         "conversions": 9.0, "all_conversions": 777.0},
    ])


def _intent_table():
    # Made-up parsed conversion export, already categorised.
    # The December row is outside the daily range.
    return pd.DataFrame([
        {"campaign": "Alpha", "month": date(2026, 1, 1),
         "action": "Local actions - Directions",
         "conversions": 8.0, "all_conversions": 80.0,
         "intent_category": "directions"},
        {"campaign": "Alpha", "month": date(2026, 1, 1),
         "action": "Clicks to call",
         "conversions": 2.0, "all_conversions": 20.0,
         "intent_category": "calls"},
        {"campaign": "Alpha", "month": date(2025, 12, 1),
         "action": "Local actions - Directions",
         "conversions": 100.0, "all_conversions": 1000.0,
         "intent_category": "directions"},
        {"campaign": "Beta", "month": date(2026, 1, 1),
         "action": "Store visits",
         "conversions": 5.0, "all_conversions": 50.0,
         "intent_category": "store_visits"},
    ])


def _table():
    return journey.journey_table(
        _clean_day(), _month_mix(), _intent_table(),
        ["Alpha", "Beta"], date(2026, 1, 5), date(2026, 1, 6))


def test_months_in_range():
    assert journey.months_in_range(
        date(2026, 1, 5), date(2026, 1, 6)) == [date(2026, 1, 1)]
    assert journey.months_in_range(
        date(2025, 12, 15), date(2026, 1, 10)) == [
        date(2025, 12, 1), date(2026, 1, 1)]


def test_journey_rows_and_group():
    table = _table()
    assert list(table["campaign"]) == ["Alpha", "Beta", "core group"]
    alpha = table[table["campaign"] == "Alpha"].iloc[0]
    assert alpha["spend"] == 200.0
    assert alpha["clicks"] == 100
    assert alpha["cost_per_click"] == pytest.approx(2.0)
    assert alpha["tracked_actions"] == 20.0
    # Engagement is All conv. of the engagement group, in
    # January only: 400, not the December or February rows.
    assert alpha["engagement_actions"] == 400.0
    assert alpha["directions_share"] == pytest.approx(8.0 / 20.0)
    assert alpha["calls_share"] == pytest.approx(2.0 / 20.0)
    assert alpha["store_visits_share"] == pytest.approx(0.0)
    assert alpha["tracked_actions_per_click"] == pytest.approx(0.2)
    assert alpha["engagement_per_tracked_action"] == pytest.approx(
        20.0)
    assert alpha["cost_per_tracked_action"] == pytest.approx(10.0)
    beta = table[table["campaign"] == "Beta"].iloc[0]
    assert beta["spend"] == 50.0
    assert beta["engagement_actions"] == 100.0
    assert beta["store_visits_share"] == pytest.approx(1.0)
    assert beta["directions_share"] == pytest.approx(0.0)
    group = table[table["campaign"] == "core group"].iloc[0]
    assert group["spend"] == 250.0
    assert group["clicks"] == 125
    assert group["tracked_actions"] == 25.0
    assert group["engagement_actions"] == 500.0
    assert group["directions_share"] == pytest.approx(8.0 / 25.0)
    assert group["calls_share"] == pytest.approx(2.0 / 25.0)
    assert group["store_visits_share"] == pytest.approx(5.0 / 25.0)
    assert group["cost_per_tracked_action"] == pytest.approx(10.0)


def test_non_core_campaign_is_excluded():
    table = _table()
    assert "Gamma" not in list(table["campaign"])


def test_intent_map_normalises_dashes_and_case():
    mapping = journey.build_intent_map({
        "directions": ["Local actions - Directions"],
        "calls": ["Clicks to call"],
        "store_visits": ["Store visits"],
    })
    # En dash and upper case match the hyphen lower-case entry.
    assert mapping[journey._normalise_action(
        "Local actions \u2013 Directions")] == "directions"
    assert mapping[journey._normalise_action(
        "CLICKS TO CALL")] == "calls"
    assert mapping[journey._normalise_action(
        "store visits")] == "store_visits"
    # An action in no category is not in the map.
    assert "menu view" not in mapping
