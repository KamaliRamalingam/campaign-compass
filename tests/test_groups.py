"""Tests for src/groups.py (T3).

All campaign names are made up. No real data.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.groups import assign_group, assign_groups

GROUPS = {
    "core": ["Alpha", "Beta"],
    "sep_2026_group": {
        "exact": ["Spring Offer"],
        "prefix": "Brand Campaign",
    },
    "exclude_pending_owner": ["Unrelated Event"],
}


def test_exact_match():
    assert assign_group("Alpha", GROUPS) == "core"
    assert assign_group("Spring Offer", GROUPS) == "sep_2026_group"


def test_prefix_match():
    assert assign_group("Brand Campaign - Test",
                        GROUPS) == "sep_2026_group"


def test_prefix_does_not_match_similar_name():
    # "Brand Sweden Campaign" does not start with the
    # prefix "Brand Campaign", so it is ungrouped here.
    assert assign_group("Brand Sweden Campaign",
                        GROUPS) == "ungrouped"


def test_ungrouped():
    assert assign_group("Something Else", GROUPS) == "ungrouped"


def test_double_match_is_an_error():
    groups = {
        "core": ["Alpha"],
        "other": ["Alpha"],
    }
    with pytest.raises(ValueError) as excinfo:
        assign_group("Alpha", groups)
    assert "Alpha" in str(excinfo.value)
    assert "core" in str(excinfo.value)
    assert "other" in str(excinfo.value)


def test_assign_groups():
    result = assign_groups(["Alpha", "Unknown"], GROUPS)
    assert result == {"Alpha": "core", "Unknown": "ungrouped"}
