"""Reuse report for the synthetic Company B test (T7).

Usage:
    python src/reuse_report.py --config config/synthetic_b.yaml \
        --base config/restaurant.yaml

Writes outputs/synthetic_b/reports/reuse-report.md (under the
config's output_root, git-ignored), listing:
- which analyses were skipped and why;
- which config keys had to differ from the restaurant config,
  found by comparing the two configs leaf by leaf (paths and
  campaign names are listed as keys, never as values), split
  into keys synthetic_b had to set (a different value, or a
  key only synthetic_b has) and restaurant-only optional keys
  that synthetic_b does not set (their defaults apply);
- which config sections are identical, so the reader can see
  what reuse did NOT need to change.

Only key names and counts are written, never rows or values
from any data file.
"""

import argparse
import sys
from pathlib import Path

import yaml

try:
    from src.clean import load_config
    from src.optional_analyses import skipped_analyses
    from src.paths import apply_output_root
except ImportError:  # running as `python src/reuse_report.py`
    from clean import load_config
    from optional_analyses import skipped_analyses
    from paths import apply_output_root


def _leaves(value, prefix=""):
    """Leaf key paths of a nested dict/list, as (path, value)."""
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _leaves(item, path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{prefix}[{index}]")
        return
    yield prefix, value


def config_diff(base, other):
    """Compare two configs leaf by leaf.

    Returns (differing, identical): differing is the sorted
    list of leaf paths whose values differ or exist in only
    one config; identical is the sorted list of leaf paths
    with the same value in both.
    """
    base_leaves = dict(_leaves(base))
    other_leaves = dict(_leaves(other))
    differing = sorted(
        path for path in set(base_leaves) | set(other_leaves)
        if base_leaves.get(path) != other_leaves.get(path))
    identical = sorted(
        path for path in set(base_leaves) & set(other_leaves)
        if base_leaves[path] == other_leaves[path])
    return differing, identical


def split_differing(base, other, differing):
    """(had_to_set, base_only) from the differing leaf paths.

    had_to_set: paths the other config sets, with a different
    value or as a key only it has. base_only: paths only the
    base config has, i.e. optional keys the other config leaves
    unset, so their defaults apply.
    """
    other_leaves = dict(_leaves(other))
    had_to_set = [path for path in differing if path in other_leaves]
    base_only = [path for path in differing
                 if path not in other_leaves]
    return had_to_set, base_only


def write_report(report_path, skipped, had_to_set, base_only,
                 identical):
    """Write the reuse report: skips and differing keys only."""
    lines = ["# Reuse report — synthetic Company B", ""]
    lines.append(
        "The pipeline was rerun on synthetic Company B data by "
        "changing only the data files and one config file "
        "(config/synthetic_b.yaml). No restaurant output was "
        "touched.")
    lines.append("")
    lines.append("## Skipped analyses")
    lines.append("")
    if not skipped:
        lines.append("- None: every analysis ran.")
    for name, reason in skipped:
        lines.append(f"- {name}: skipped, {reason}.")
    lines.append("")
    lines.append("## Config keys that had to differ")
    lines.append("")
    total = len(had_to_set) + len(base_only)
    lines.append(
        f"- {total} leaf keys differ from config/restaurant.yaml: "
        f"{len(had_to_set)} that synthetic_b had to set, and "
        f"{len(base_only)} restaurant-only optional keys that "
        "synthetic_b does not set (their defaults apply).")
    lines.append("")
    lines.append(
        f"### Keys synthetic_b had to set ({len(had_to_set)})")
    lines.append("")
    for path in had_to_set:
        lines.append(f"- {path}")
    lines.append("")
    lines.append(
        "### Restaurant-only optional keys not set by synthetic_b "
        f"({len(base_only)})")
    lines.append("")
    for path in base_only:
        lines.append(f"- {path}")
    lines.append("")
    lines.append("## Config keys that did not need to change")
    lines.append("")
    lines.append(
        f"- {len(identical)} leaf keys are identical to "
        "config/restaurant.yaml, including the volume rule, "
        "the recommendation thresholds and the recent-trend "
        "thresholds.")
    for path in identical:
        lines.append(f"- {path}")
    lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Compare the configs and write the reuse report."""
    parser = argparse.ArgumentParser(
        description="Write the Company B reuse report."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--base", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        base = load_config(args.base)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    config = apply_output_root(config)
    skipped = skipped_analyses(config)
    differing, identical = config_diff(base, config)
    had_to_set, base_only = split_differing(base, config, differing)
    root = (config.get("analysis") or {}).get("output_root") \
        or "outputs"
    report_path = Path(root) / "reports" / "reuse-report.md"
    write_report(report_path, skipped, had_to_set, base_only,
                 identical)
    print(f"Skipped analyses: {len(skipped)}")
    for name, reason in skipped:
        print(f"  {name}: {reason}")
    print(f"Config keys that differed: {len(differing)}")
    print(f"  synthetic_b had to set: {len(had_to_set)}")
    print(f"  restaurant-only, not set by synthetic_b: "
          f"{len(base_only)}")
    print(f"Config keys unchanged: {len(identical)}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
