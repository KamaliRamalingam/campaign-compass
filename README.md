# Google Ads Campaign Analysis (DA27 Individual Project)

> Status: work in progress. Course: Data Analyst 27, Course 11. Deadline 27 Nov 2026.

## Problem
(1-2 sentences: who has the problem, what decision it supports.)

## What this project does
Analyses Google Ads campaign data (tracked conversions, cost per conversion,
trend, weekday/hour/location where available) and recommends which campaigns to
continue, test or pause.

## What it cannot show
- Real bookings, walk-ins, phone orders or profit.
- That an offer caused extra customers. Results are tracked conversions only.
- Campaigns below the minimum-volume threshold are not ranked.

## Method
(Numbered steps. Link to docs/method.md.)

## How to rerun
1. Create a virtual environment and install `requirements.txt`.
2. Put the Google Ads export (campaign-by-day CSV) in `data/raw/`.
3. Copy a config from `config/` and set the conversion actions, thresholds and
   optional location/offer patterns.
4. Run the pipeline (commands added once the scripts exist).

Reuse: change the data file and the config file. Tested on: (restaurant account;
synthetic Company B dataset, clearly labelled synthetic).

## Workflow
- Muse builds on branches, and CI checks every pull request.
- I merge in the GitHub web UI.
- I run `bash run.sh` locally. It creates `.venv` if needed, installs
  `requirements.txt`, and runs the stages that exist so far
  (validation now; the pipeline later).
- Outputs stay in the ignored `outputs/` folder and never go to GitHub.

## Data
Client data is not included in this repository. See `docs/data-dictionary.md`.

## Repository structure
- `config/`: client-specific settings
- `src/`: pipeline code
- `results/`: result tables
- `docs/`: method, decision log, AI usage log
- `tests/`: checks
- `mcp_server/`: optional read-only server over the result tables

## AI use
See `docs/ai-usage-log.md`.
