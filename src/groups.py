"""Assign campaigns to groups from the config (T3).

A group in the config is either a list of exact campaign names,
or a mapping with "exact" (a list of names) and "prefix" (a name
starting with this prefix belongs to the group).

A campaign in no group goes to "ungrouped" and is reported, never
dropped silently. A campaign matching two groups is an error.

A mapping group may also have "display_name": the readable name
shown to people. It is display only: the key stays the group
value in every output, and a group without display_name is shown
by its key.
"""

import re

UNGROUPED = "ungrouped"
UNGROUPED_DISPLAY_NAME = "Not in any group"


def _matches(name, rule):
    """Return True if a campaign name matches one group's rule."""
    if isinstance(rule, list):
        return name in rule
    if isinstance(rule, dict):
        exact = rule.get("exact") or []
        if name in exact:
            return True
        prefix = rule.get("prefix")
        if prefix and name.startswith(prefix):
            return True
        return False
    raise ValueError(f"invalid campaign group rule: {rule!r}")


def assign_group(campaign, groups):
    """Assign one campaign to a group, or "ungrouped".

    Raises ValueError if the campaign matches two groups.
    """
    matched = [
        group for group, rule in (groups or {}).items()
        if _matches(campaign, rule)
    ]
    if len(matched) > 1:
        raise ValueError(
            f"campaign {campaign!r} matches two groups: "
            f"{', '.join(matched)}"
        )
    if matched:
        return matched[0]
    return UNGROUPED


def assign_groups(campaigns, groups):
    """Assign each campaign in a list to a group.

    Returns a dict of campaign -> group. Raises ValueError on a
    double match, naming the campaign and the two groups.
    """
    return {campaign: assign_group(campaign, groups)
            for campaign in campaigns}


def display_name(group, groups):
    """Readable name of a group: its display_name, else its key.

    "ungrouped" is not a config group; it reads "Not in any group".
    """
    rule = (groups or {}).get(group)
    if isinstance(rule, dict) and rule.get("display_name"):
        return str(rule["display_name"])
    if group == UNGROUPED:
        return UNGROUPED_DISPLAY_NAME
    return str(group)


def display_names(groups):
    """{group key: readable name} for every group and "ungrouped"."""
    names = {str(key): display_name(key, groups) for key in groups or {}}
    names.setdefault(UNGROUPED, display_name(UNGROUPED, groups))
    return names


def replace_group_keys(text, names):
    """A text with each group key replaced by its readable name.

    names is {key: readable name}, as from display_names. Only
    whole words are replaced (no letter, digit or underscore
    directly before or after), longest key first, so "core" is
    never replaced inside "core_pmax" or "score". A value that
    is not text, or a text without any key, is returned as is.
    """
    if not isinstance(text, str) or not names:
        return text
    keys = sorted((key for key, name in names.items() if key != name),
                  key=len, reverse=True)
    if not keys:
        return text
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(key) for key in keys) + r")(?!\w)")
    return pattern.sub(lambda match: names[match.group(1)], text)
