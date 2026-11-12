#!/usr/bin/env bash
# Local runner (T0c). One command for the student:
#   bash run.sh [--config config/validation.yaml]
#
# Creates .venv if missing, installs requirements.txt, then runs the
# stages that exist so far (validation, load, clean, overview, metrics, time, recommend, conversion).
# Outputs go under outputs/ (git-ignored) and never go to GitHub.
#
# Config: --config defaults to config/validation.yaml. If a file with
# the same name exists under config/local/ (for example
# config/local/validation.yaml), that local file is used instead.
# config/local/ is git-ignored and optional; nothing requires it.
# The load stage uses config/restaurant.yaml (or
# config/local/restaurant.yaml if it exists).
#
# Prints only PASS/FAIL/INFO lines, counts, sums and dates. Never
# rows, title lines or file contents. Exit 1 if any stage fails.
set -euo pipefail
cd "$(dirname "$0")"

CONFIG="config/validation.yaml"
while [ $# -gt 0 ]; do
    case "$1" in
        --config)
            CONFIG="$2"
            shift 2
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            echo "Usage: bash run.sh [--config config/validation.yaml]" >&2
            exit 1
            ;;
    esac
done

LOCAL_CONFIG="config/local/$(basename "$CONFIG")"
if [ -f "$LOCAL_CONFIG" ]; then
    CONFIG="$LOCAL_CONFIG"
fi
echo "Config: $CONFIG"

if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv..."
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

STATUS=0

# Stage 1: export validation (T0b). Report under outputs/reports/.
REPORT="outputs/reports/validation-report.md"
mkdir -p "$(dirname "$REPORT")"
if ! .venv/bin/python src/validate_exports.py --config "$CONFIG" --out "$REPORT"; then
    STATUS=1
fi
echo "Report: $REPORT"

# Stage 2: load the exports (T1). Writes standardised tables under
# outputs/interim/. Uses config/restaurant.yaml, or its local
# override config/local/restaurant.yaml if it exists.
LOAD_CONFIG="config/restaurant.yaml"
if [ -f "config/local/restaurant.yaml" ]; then
    LOAD_CONFIG="config/local/restaurant.yaml"
fi
echo "Load config: $LOAD_CONFIG"
if ! .venv/bin/python src/load.py --config "$LOAD_CONFIG"; then
    STATUS=1
fi

# Stage 3: clean the standardised tables (T2). Writes cleaned
# tables under outputs/interim/ and a report under outputs/reports/.
# Uses the same config as the load stage.
if ! .venv/bin/python src/clean.py --config "$LOAD_CONFIG"; then
    STATUS=1
fi

# Stage 4: campaign overview (T3a). Writes one row per campaign
# to outputs/reports/campaign-overview.csv. Prints only the
# number of campaigns and where the file was written.
if ! .venv/bin/python src/overview.py --config "$LOAD_CONFIG"; then
    STATUS=1
fi

# Stage 5: campaign groups and metrics (T3). Writes result tables
# under outputs/results/ and a report under outputs/reports/.
# Prints group counts only.
if ! .venv/bin/python src/metrics.py --config "$LOAD_CONFIG"; then
    STATUS=1
fi

# Stage 6: time patterns, trends and runs (T4). Writes result
# tables under outputs/results/ and a report under outputs/reports/.
# Prints counts only.
if ! .venv/bin/python src/time_patterns.py --config "$LOAD_CONFIG"; then
    STATUS=1
fi

# Stage 7: recommendations (T5). Writes result tables under
# outputs/results/ and a report under outputs/reports/.
# Prints counts per label only.
if ! .venv/bin/python src/recommend.py --config "$LOAD_CONFIG"; then
    STATUS=1
fi

# Stage 8: conversion breakdown by action (T10). Writes result
# tables under outputs/results/ and a report under
# outputs/reports/. Prints PASS or FAIL and the group totals only.
if ! .venv/bin/python src/conversion_mix.py --config "$LOAD_CONFIG"; then
    STATUS=1
fi

# Later stages (charts, dashboard, etc.) run here, setting
# STATUS=1 on failure.

if [ "$STATUS" -ne 0 ]; then
    echo "FAIL: one or more stages failed (see above)"
    exit 1
fi
echo "PASS: all stages passed"
