"""Tests for PR 3 S5: partial-month flags in the monthly and
timeline tables.

All data is tiny and made up. No real data, no real campaign
names, no real rows from the exports.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.time_patterns import monthly_table, timeline_table

GROUPS = {"core": ["Alpha", "Beta"]}


def _days(campaign, start, end, skip=()):
    rows, day = [], start
    while day <= end:
        if day not in skip:
            rows.append({"date": day.isoformat(), "campaign": campaign,
                         "clicks": 10, "cost": 10.0,
                         "conversions": 1.0})
        day += timedelta(days=1)
    return rows


def _day_df():
    # Alpha: 2026-01-10 to 2026-03-31, with a gap on 2026-02-10..12.
    # Beta: 2026-01-01 to 2026-02-15. Data ends 2026-03-31.
    gap = {date(2026, 2, 10), date(2026, 2, 11), date(2026, 2, 12)}
    rows = _days("Alpha", date(2026, 1, 10), date(2026, 3, 31), gap)
    rows += _days("Beta", date(2026, 1, 1), date(2026, 2, 15))
    return pd.DataFrame(rows)


def _by_key(table):
    return table.set_index(["campaign", "month"])


def test_partial_and_lagged_flags():
    table = _by_key(monthly_table(_day_df(), GROUPS, ["core"],
                                  lag_days=3))
    jan = table.loc[("Alpha", "2026-01")]
    # Started on the 10th: 22 of 31 days.
    assert (jan["days_in_month"], jan["days_covered"]) == (31, 22)
    assert jan["is_partial"] and not jan["is_lagged"]
    feb = table.loc[("Alpha", "2026-02")]
    # A gap inside the month does not make it partial: the
    # campaign's span covers the whole month.
    assert feb["days_covered"] == 28 and not feb["is_partial"]
    assert feb["active_days"] == 25
    mar = table.loc[("Alpha", "2026-03")]
    # Full month, but its last 3 days are in the lag window.
    assert not mar["is_partial"] and mar["is_lagged"]
    beta_feb = table.loc[("Beta", "2026-02")]
    assert beta_feb["days_covered"] == 15 and beta_feb["is_partial"]
    assert not beta_feb["is_lagged"]


def test_data_end_caps_the_last_month():
    df = _day_df()
    df = df.loc[df["date"] <= "2026-03-20"]
    mar = _by_key(monthly_table(df, GROUPS, ["core"], lag_days=3)) \
        .loc[("Alpha", "2026-03")]
    assert mar["days_covered"] == 20
    assert mar["is_partial"] and mar["is_lagged"]


def test_no_lag_means_never_lagged():
    table = monthly_table(_day_df(), GROUPS, ["core"])
    assert not table["is_lagged"].any()


def test_metrics_are_unchanged_and_columns_appended():
    table = monthly_table(_day_df(), GROUPS, ["core"], lag_days=3)
    assert list(table.columns)[:2] == ["campaign", "month"]
    assert list(table.columns)[-4:] == [
        "days_in_month", "days_covered", "is_partial", "is_lagged"]
    alpha_jan = _by_key(table).loc[("Alpha", "2026-01")]
    assert alpha_jan["active_days"] == 22
    assert alpha_jan["spend"] == 220.0


def test_timeline_month_rows_have_empty_flags():
    month_df = pd.DataFrame([{"date": "2025-12-01", "campaign": "Alpha",
                              "clicks": 5, "cost": 5.0,
                              "conversions": 1.0}])
    table = _by_key(timeline_table(_day_df(), month_df, GROUPS,
                                   ["core"], lag_days=3))
    history = table.loc[("Alpha", "2025-12")]
    assert history["source"] == "month"
    assert pd.isna(history["days_covered"])
    assert pd.isna(history["is_partial"])
    assert bool(table.loc[("Alpha", "2026-03"), "is_lagged"])
