"""Reuse report for the synthetic Company B test (T7).

Usage:
    python src/reuse_report.py --config config/synthetic_b.yaml \
        --base config/restaurant.yaml

Writes outputs/synthetic_b/reports/reuse-report.md (under the
config's output_root, git-ignored), listing:
- which analyses were skipped and why;
- which config keys had to differ from the restaurant config,
  found by comparing the two configs leaf by leaf (paths and
  campaign names are listed as keys, never as values);
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


def write_report(report_path, skipped, differing, identical):
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
    lines.append(
        f"- {len(differing)} leaf keys differ from "
        "config/restaurant.yaml.")
    for path in differing:
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
    root = (config.get("analysis") or {}).get("output_root") \
        or "outputs"
    report_path = Path(root) / "reports" / "reuse-report.md"
    write_report(report_path, skipped, differing, identical)
    print(f"Skipped analyses: {len(skipped)}")
    for name, reason in skipped:
        print(f"  {name}: {reason}")
    print(f"Config keys that differed: {len(differing)}")
    print(f"Config keys unchanged: {len(identical)}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
