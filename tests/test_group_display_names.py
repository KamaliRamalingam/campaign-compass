"""Group display names: readable names on screen, keys everywhere else.

display_name in a config group is display only. A group without
one is shown by its key. The replacement helper swaps whole-word
keys in src/ texts, longest key first.
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard"))

import data as dd  # noqa: E402
from src.groups import (  # noqa: E402
    assign_group, display_name, display_names, replace_group_keys)

NAMES = {"core": "Core campaigns", "core_pmax": "Performance Max",
         "sep_2026_group": "September 2026 campaigns"}


def _config(name):
    return yaml.safe_load(
        (ROOT / "config" / name).read_text(encoding="utf-8"))


# --- display_name and its fallback --------------------------------

def test_group_without_display_name_falls_back_to_key():
    groups = {"core": ["Alpha", "Beta"],
              "spring": {"exact": ["Gamma"], "prefix": "Spring "}}
    assert display_name("core", groups) == "core"
    assert display_name("spring", groups) == "spring"
    assert display_names(groups) == {
        "core": "core", "spring": "spring",
        "ungrouped": "Not in any group"}


def test_empty_display_name_falls_back_to_key():
    groups = {"core": {"display_name": "", "exact": ["Alpha"]}}
    assert display_name("core", groups) == "core"


def test_display_name_from_restaurant_config():
    groups = _config("restaurant.yaml")["analysis"]["campaign_groups"]
    assert display_name("core_pmax", groups) == "Performance Max"
    assert display_name("ungrouped", groups) == "Not in any group"


def test_synthetic_b_core_display_name():
    groups = _config("synthetic_b.yaml")["analysis"]["campaign_groups"]
    assert display_names(groups)["core"] == "All campaigns"


def test_display_name_does_not_change_group_assignment():
    groups = {"core": {"display_name": "Core campaigns",
                       "exact": ["Alpha"]}}
    assert assign_group("Alpha", groups) == "core"
    assert assign_group("Core campaigns", groups) == "ungrouped"


# --- replace_group_keys -------------------------------------------

def test_replaces_whole_word_keys():
    text = ("group core_pmax is not comparable with the core benchmark "
            "(leave-one-out)")
    assert replace_group_keys(text, NAMES) == (
        "group Performance Max is not comparable with the Core "
        "campaigns benchmark (leave-one-out)")


def test_longest_key_first_core_not_inside_core_pmax():
    assert replace_group_keys("core_pmax", NAMES) == "Performance Max"
    assert replace_group_keys("core+core_pmax", NAMES) == (
        "Core campaigns+Performance Max")


def test_core_not_replaced_inside_other_words():
    text = "score, hardcore, cores, core1, Core and xcore stay"
    assert replace_group_keys(text, NAMES) == text


def test_text_without_any_key_is_unchanged():
    text = "no run had enough volume to judge: 1 runs, 0 with enough volume"
    assert replace_group_keys(text, NAMES) == text


def test_non_text_and_no_names_are_returned_as_is():
    assert replace_group_keys(None, NAMES) is None
    assert pd.isna(replace_group_keys(float("nan"), NAMES))
    assert replace_group_keys("core", {}) == "core"
    assert replace_group_keys("core", {"core": "core"}) == "core"


# --- dashboard helpers ----------------------------------------------

def test_with_group_names_is_display_only():
    table = pd.DataFrame({
        "campaign": ["A", "core group"],
        "group": ["core_pmax", "core"],
        "groups": ["core+core_pmax", None],
        "reason": ["group core_pmax not evaluated", "fine"],
    })
    before = table.copy()
    shown = dd.with_group_names(table, NAMES,
                                "Core campaigns + Performance Max")
    pd.testing.assert_frame_equal(table, before)
    assert shown["group"].tolist() == ["Performance Max", "Core campaigns"]
    assert shown["groups"].iloc[0] == "Core campaigns + Performance Max"
    assert pd.isna(shown["groups"].iloc[1])
    assert shown["reason"].iloc[0] == "group Performance Max not evaluated"
    assert shown["campaign"].tolist() == [
        "A", "Core campaigns + Performance Max"]


def test_filter_options_and_filter_stay_on_keys():
    recs = pd.DataFrame({"campaign": ["A", "B"],
                         "group": ["core", "core_pmax"],
                         "label": ["test", "not_comparable"]})
    assert dd.group_options(recs) == [dd.ALL_GROUPS, "core", "core_pmax"]
    assert dd.campaigns_in_group(recs, "core_pmax") == ["B"]


def test_rules_table_shows_group_lists_by_name():
    config = _config("restaurant.yaml")
    raw = dd.rules_table(config).set_index("setting")["value"]
    shown = dd.rules_table(config, dd.group_names(config)).set_index(
        "setting")["value"]
    assert raw["recommendation_rules.judged_groups"] == (
        "['core', 'sep_2026_group']")
    assert shown["recommendation_rules.judged_groups"] == (
        "Core campaigns, September 2026 campaigns")
    assert shown["recommendation_rules.benchmark.groups"] == (
        "Core campaigns")
    assert shown["recommendation_rules.continue_max_ratio"] == "1.0"


def test_journey_pool_label_names_the_time_groups():
    config = _config("restaurant.yaml")
    names = dd.group_names(config)
    assert dd.journey_pool_label(config, names) == (
        "Core campaigns + Performance Max")
    config_b = _config("synthetic_b.yaml")
    assert dd.journey_pool_label(
        config_b, dd.group_names(config_b)) == "All campaigns"
