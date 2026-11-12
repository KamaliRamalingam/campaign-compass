"""Analyses that cannot run on this export (T7).

Usage:
    python src/optional_analyses.py --config config/synthetic_b.yaml

Location and hour-of-day analyses need a location column and
an hour column in the export. This export has neither, so both
are skipped with a clear printed message. Skipping never fails
and never invents values: the analyses simply do not run, and
the reuse report lists them as skipped.

The check is config-driven: it looks for a "location" or
"hour" entry in the config's columns mapping. A future export
with those columns would not be skipped by this step.
"""

import argparse
import sys
from pathlib import Path

import yaml

try:
    from src.clean import load_config
except ImportError:  # running as `python src/optional_analyses.py`
    from clean import load_config

OPTIONAL_ANALYSES = (
    ("location", "location",
     "no location column in the export"),
    ("hour", "hour",
     "no hour-of-day data in the export"),
)


def skipped_analyses(config):
    """Return the (name, reason) pairs that cannot run."""
    columns = (config or {}).get("columns") or {}
    skipped = []
    for name, column, reason in OPTIONAL_ANALYSES:
        if not columns.get(column):
            skipped.append((name, reason))
    return skipped


def main(argv=None):
    """Print the skip messages. Always exits 0."""
    parser = argparse.ArgumentParser(
        description="Skip analyses this export cannot support."
    )
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for name, reason in skipped_analyses(config):
        print(f"Skipping {name} analysis: {reason}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
