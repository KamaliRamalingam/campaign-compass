"""Tests for PR 5: the label-period figures in
recommendations_by_campaign (label_spend, label_tracked_actions,
label_cost_per_tracked_action, label_benchmark).

Reuses the made-up data of test_recent_label.py. No real data,
no real campaign names.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import recommend  # noqa: E402
from test_recent_label import (  # noqa: E402
    RULES, _run_recs, _summary, _windows)

FIGURES = ["label_spend", "label_tracked_actions",
           "label_cost_per_tracked_action", "label_benchmark"]


def _empty(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def test_recent_window_figures():
    recs = recommend.recommend_campaigns(
        _run_recs(), _summary(), RULES, "caveat",
        _windows()).set_index("campaign")
    alpha = recs.loc["Alpha"]
    # Last 30 days: 30 days at 15.00 spend and 1 conversion.
    assert alpha["label_spend"] == 450.0
    assert alpha["label_tracked_actions"] == 30.0
    assert alpha["label_cost_per_tracked_action"] == 15.0
    assert alpha["label_benchmark"] == 10.0


def test_latest_run_figures():
    recs = recommend.recommend_campaigns(
        _run_recs(), _summary(), RULES, "caveat",
        _windows()).set_index("campaign")
    beta = recs.loc["Beta"]
    assert beta["label_basis"] == "latest_run"
    assert beta["label_spend"] == 31 * 15.0
    assert beta["label_tracked_actions"] == 31.0
    assert beta["label_cost_per_tracked_action"] == 15.0
    assert beta["label_benchmark"] == 10.0


def test_figures_agree_with_label_ratio():
    recs = recommend.recommend_campaigns(
        _run_recs(), _summary(), RULES, "caveat", _windows())
    rated = recs.loc[recs["label_ratio"].notna()]
    assert len(rated) > 0
    for _, row in rated.iterrows():
        assert math.isclose(
            row["label_cost_per_tracked_action"]
            / row["label_benchmark"], row["label_ratio"])


def test_fixed_label_has_no_figures():
    rules = dict(RULES, not_comparable_groups=["core_pmax"])
    recs = recommend.recommend_campaigns(
        _run_recs(rules), _summary(), rules, "caveat",
        _windows(rules=rules)).set_index("campaign")
    assert recs.loc["Pmax", "label"] == "not_comparable"
    for column in FIGURES:
        assert _empty(recs.loc["Pmax", column])


def test_insufficient_recent_window_has_no_figures():
    recs = recommend.recommend_campaigns(
        _run_recs(), _summary(), RULES, "caveat",
        _windows(window_days=5)).set_index("campaign")
    assert recs.loc["Alpha", "label"] == "insufficient_data"
    for column in FIGURES:
        assert _empty(recs.loc["Alpha", column])
