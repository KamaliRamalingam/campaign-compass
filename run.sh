#!/usr/bin/env bash
# Local runner (T0c). One command for the student:
#   bash run.sh [--config config/validation.yaml]
#   bash run.sh --client synthetic_b
#
# Creates .venv if missing, installs requirements.txt, then runs the
# stages that exist so far (validation, load, clean, overview, metrics, time, recommend, conversion, recent trend, journey).
# Outputs go under outputs/ (git-ignored) and never go to GitHub.
#
# Config: --config defaults to config/validation.yaml. If a file with
# the same name exists under config/local/ (for example
# config/local/validation.yaml), that local file is used instead.
# config/local/ is git-ignored and optional; nothing requires it.
# The load stage uses config/restaurant.yaml (or
# config/local/restaurant.yaml if it exists).
#
# --client synthetic_b (T7) reruns the whole pipeline on the
# synthetic Company B test data: it generates the data first
# (src/make_synthetic.py, fixed seed, into the ignored
# outputs/synthetic_b/raw/ folder), then runs every stage with
# config/synthetic_b.yaml, whose output_root is
# outputs/synthetic_b, so the restaurant outputs are untouched.
# Without the flag, the runner behaves exactly as before.
#
# Prints only PASS/FAIL/INFO lines, counts, sums and dates. Never
# rows, title lines or file contents. Stops at the first failed
# stage: prints "FAIL: stage '<name>' failed; later stages were
# not run" and exits 1, so no later stage reads stale outputs.
set -euo pipefail
cd "$(dirname "$0")"

CONFIG="config/validation.yaml"
CONFIG_GIVEN=0
CLIENT="restaurant"
while [ $# -gt 0 ]; do
    case "$1" in
        --config)
            CONFIG="$2"
            CONFIG_GIVEN=1
            shift 2
            ;;
        --client)
            CLIENT="$2"
            shift 2
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            echo "Usage: bash run.sh [--config config/validation.yaml] [--client synthetic_b]" >&2
            exit 1
            ;;
    esac
done

if [ "$CLIENT" = "synthetic_b" ]; then
    LOAD_CONFIG="config/synthetic_b.yaml"
    VALIDATION_CONFIG="config/validation_synthetic_b.yaml"
    REPORT="outputs/synthetic_b/reports/validation-report.md"
elif [ "$CLIENT" = "restaurant" ]; then
    LOAD_CONFIG="config/restaurant.yaml"
    VALIDATION_CONFIG="$CONFIG"
    REPORT="outputs/reports/validation-report.md"
else
    echo "ERROR: unknown client: $CLIENT" >&2
    echo "Usage: bash run.sh [--config config/validation.yaml] [--client synthetic_b]" >&2
    exit 1
fi
# An explicit --config always wins for the validation config.
if [ "$CONFIG_GIVEN" -eq 1 ]; then
    VALIDATION_CONFIG="$CONFIG"
fi

LOCAL_CONFIG="config/local/$(basename "$VALIDATION_CONFIG")"
if [ -f "$LOCAL_CONFIG" ]; then
    VALIDATION_CONFIG="$LOCAL_CONFIG"
fi
echo "Config: $VALIDATION_CONFIG"
echo "Client: $CLIENT"

if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv..."
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

# Run one stage; on failure stop the whole run (no later stage
# runs on stale or missing outputs).
#   run_stage <name> <command...>
run_stage() {
    local name="$1"
    shift
    if ! "$@"; then
        echo "FAIL: stage '$name' failed; later stages were not run"
        exit 1
    fi
}

# Stage 0 (synthetic client only): generate the synthetic data.
if [ "$CLIENT" = "synthetic_b" ]; then
    run_stage generate .venv/bin/python src/make_synthetic.py --config "$LOAD_CONFIG"
fi

# Stage 1: export validation (T0b). Report under outputs/reports/
# (or outputs/synthetic_b/reports/ for the synthetic client).
mkdir -p "$(dirname "$REPORT")"
if ! .venv/bin/python src/validate_exports.py --config "$VALIDATION_CONFIG" --out "$REPORT"; then
    echo "Report: $REPORT"
    echo "FAIL: stage 'validation' failed; later stages were not run"
    exit 1
fi
echo "Report: $REPORT"

# Stage 2: load the exports (T1). Writes standardised tables under
# outputs/interim/ (or outputs/synthetic_b/interim/). Uses the
# client config, or its local override config/local/<name>.yaml
# if it exists.
if [ -f "config/local/$(basename "$LOAD_CONFIG")" ]; then
    LOAD_CONFIG="config/local/$(basename "$LOAD_CONFIG")"
fi
echo "Load config: $LOAD_CONFIG"
run_stage load .venv/bin/python src/load.py --config "$LOAD_CONFIG"

# Stage 3: clean the standardised tables (T2). Writes cleaned
# tables under outputs/interim/ and a report under outputs/reports/.
# Uses the same config as the load stage.
run_stage clean .venv/bin/python src/clean.py --config "$LOAD_CONFIG"

# Stage 4: campaign overview (T3a). Writes one row per campaign
# to outputs/reports/campaign-overview.csv. Prints only the
# number of campaigns and where the file was written.
run_stage overview .venv/bin/python src/overview.py --config "$LOAD_CONFIG"

# Stage 5: campaign groups and metrics (T3). Writes result tables
# under outputs/results/ and a report under outputs/reports/.
# Prints group counts only.
run_stage metrics .venv/bin/python src/metrics.py --config "$LOAD_CONFIG"

# Stage 6: time patterns, trends and runs (T4). Writes result
# tables under outputs/results/ and a report under outputs/reports/.
# Prints counts only.
run_stage time_patterns .venv/bin/python src/time_patterns.py --config "$LOAD_CONFIG"

# Stage 7: recommendations (T5). Writes result tables under
# outputs/results/ and a report under outputs/reports/.
# Prints counts per label only.
run_stage recommend .venv/bin/python src/recommend.py --config "$LOAD_CONFIG"

# Stage 8: conversion breakdown by action (T10). Writes result
# tables under outputs/results/ and a report under
# outputs/reports/. Prints PASS or FAIL and the group totals only.
run_stage conversion_mix .venv/bin/python src/conversion_mix.py --config "$LOAD_CONFIG"

# Stage 9: recent trend and weekly tables (T11). Writes
# result tables under outputs/results/ and a report under
# outputs/reports/. Prints counts only.
run_stage recent_trend .venv/bin/python src/recent_trend.py --config "$LOAD_CONFIG"

# Stage 10: acquisition journey, what-if and break-even
# (T12). Writes the journey table, the what-if table and the
# journey report under outputs/results/ and outputs/reports/.
# The break-even table is written only when
# analysis.break_even.avg_revenue_per_visit is set; while it
# is null the output is skipped with a message. Prints counts
# only.
run_stage journey .venv/bin/python src/journey.py --config "$LOAD_CONFIG"
run_stage what_if .venv/bin/python src/what_if.py --config "$LOAD_CONFIG"
run_stage break_even .venv/bin/python src/break_even.py --config "$LOAD_CONFIG"

# Stage 11 (synthetic client only): analyses this export cannot
# support are skipped with a message, never failed, and the
# reuse report is written. The restaurant run does not change.
if [ "$CLIENT" = "synthetic_b" ]; then
    run_stage optional_analyses .venv/bin/python src/optional_analyses.py --config "$LOAD_CONFIG"
    run_stage reuse_report .venv/bin/python src/reuse_report.py --config "$LOAD_CONFIG" --base config/restaurant.yaml
fi

# Later stages (charts, dashboard, etc.) run here, through
# run_stage.

echo "PASS: all stages passed"
