"""Assign campaigns to groups from the config (T3).

A group in the config is either a list of exact campaign names,
or a mapping with "exact" (a list of names) and "prefix" (a name
starting with this prefix belongs to the group).

A campaign in no group goes to "ungrouped" and is reported, never
dropped silently. A campaign matching two groups is an error.
"""

UNGROUPED = "ungrouped"


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
