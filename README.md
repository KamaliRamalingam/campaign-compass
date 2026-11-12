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

## Reuse test
The pipeline reruns on a different Google Ads account by changing only the
data files and one config file, proved on a synthetic Company B dataset
(`bash run.sh --client synthetic_b`):
- The data is generated at run time by `src/make_synthetic.py` (fixed seed 42)
  into the ignored `outputs/synthetic_b/raw/` folder, and is never committed.
  It uses different header names, different campaign and conversion action
  names, EUR instead of SEK, a shorter date range, an ended campaign, a
  low-volume campaign, missing days, duplicate rows and a gap of more than
  14 days.
- What changed to run it: `config/synthetic_b.yaml` (its own column mapping,
  paths, groups, action groups, totals and `output_root: outputs/synthetic_b`)
  and `config/validation_synthetic_b.yaml` (its own UI totals, computed once
  from the seeded generator). No restaurant output is touched.
- What did not change: the volume rule, the recommendation thresholds and
  the recent-trend thresholds are identical to the restaurant config.
- Code changes the reuse needed (see the reuse report and the T7 pull
  request): a new `src/paths.py` so every stage writes under the config's
  `output_root`; the currency stripping in the two number parsers now
  handles EUR as well as SEK (it was hard-coded to SEK); the dashboard
  takes its currency from the config instead of hard-coding SEK, and has
  a sidebar client selector.
- Location and hour analyses are skipped with a printed message, because
  the synthetic export has no location column and no hour-of-day data.
  They are never faked.
- Known limitation: the dashboard conversion page still names the
  restaurant's engagement actions in one sentence, even for Company B.
  The reuse report (`outputs/synthetic_b/reports/reuse-report.md`) lists
  the skipped analyses and every config key that had to differ.

## How to run the dashboard
Run `bash run.sh` first, then `bash dashboard.sh` and open the address it prints.

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
