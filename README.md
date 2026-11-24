# CampaignCompass

> Status: work in progress. Course: Data Analyst 27, Course 11. Deadline 27 Nov 2026.

Google Ads campaign performance analysis for a restaurant chain in Sweden, built as a reusable pipeline plus a local dashboard. It answers which campaigns to continue, test or pause, and when to run them, from the account's own Google Ads data.

## 2. The problem

The owner spends on Google Ads and on offers without knowing which campaigns bring extra tracked conversions, where, or when. This project supports one decision: which campaigns to continue, test or pause, and when to run them.

It can answer: which campaigns have the lowest cost per tracked action, how performance varies by weekday and over time, which campaigns have too little data to judge, and which campaigns are getting worse recently.

It cannot answer: how many real bookings, walk-ins or phone orders the ads caused, whether an offer caused extra customers, or how much profit a campaign made. Those need data this project does not have (bookings and orders), and the analysis never claims them.

## 3. What counts as a conversion here

A conversion here is a **tracked action** in Google Ads: mainly get-directions requests and phone calls, plus estimated store visits. It is not a booking or an order.

Engagement actions — menu views, website visits and other engagements — are **not** counted as tracked actions. They are reported separately, as a share of all conversions, so the reader can see how much of the account's activity they are.

Every output also shows the data date range, the last-updated date, and this caveat: "Tracked actions only (mainly get-directions requests and phone calls), not bookings or orders. This shows campaign performance, not proof that an offer brought extra customers."

## 4. Method

The pipeline runs in order, from one command. Each stage reads only the config and the outputs of the stage before it.

1. **Validate** (`src/validate_exports.py`): checks the raw exports against the totals shown in the Google Ads UI. Config: `config/validation.yaml` — `files`, `ui_expected`, `cross_file_tolerance`.
2. **Load** (`src/load.py`): reads the campaign-by-day and campaign-by-month exports into standardised tables, drops totals rows, and fails naming any missing required column. Config: `input.files`, `input.title_lines`, `encoding`, `delimiter`, `decimal`, `thousands`, `columns`, `required_columns`.
3. **Clean** (`src/clean.py`): keeps day rows inside the daily range and month rows up to the monthly end, drops duplicate rows on date and campaign, flags rows with missing or negative values, and keeps flagged rows. Missing days are not filled. Config: `analysis.daily_start`, `daily_end`, `monthly_end`, `include_campaigns`, `exclude_campaigns`.
4. **Campaign groups** (`src/groups.py`, `src/overview.py`): one overview row per campaign, then each campaign is assigned to a group from the config. A campaign in no group is "ungrouped" and reported, never dropped. Config: `analysis.campaign_groups`, `analysis.include_campaigns`, `analysis.exclude_campaigns`.
5. **Metrics** (`src/metrics.py`): per campaign, spend, clicks, tracked actions, cost per tracked action, tracked actions per click, and a volume flag. Metrics use active days only. Config: `analysis.volume_rule`, `analysis.campaign_groups`.
6. **Time patterns and runs** (`src/time_patterns.py`): weekday tables (pooled and per campaign), monthly tables, a timeline, and runs — a run is a stretch of activity split by a gap of more than `run_gap_days` with no activity. Config: `analysis.time_groups`, `weekday_min_conversions`, `run_gap_days`.
6b. **Weekday decomposition** (`src/weekday_decomposition.py`): splits the pooled weekday cells by campaign — click shares and actions per click against Mon–Thu, a leave-one-out check, and the top days. Aggregates only. Config: `analysis.weekday_decomposition`.
7. **Recommendations** (`src/recommend.py`): compares each run's cost per tracked action with the core benchmark (calculated, not typed in; each campaign is left out of its own benchmark) and labels it continue, test, pause_or_review, insufficient_data, not_comparable or not_judged, with a plain-language reason and the caveat on every row. Active campaigns are also labelled from their last 90 days, and a worsening trend never shows continue. Config: `analysis.recommendation_rules`, `analysis.caveat_text`.
8. **Conversion mix** (`src/conversion_mix.py`): breaks tracked actions down by conversion action and action group (high intent, engagement, unmapped), and checks the file totals against the config. Config: `conversion_breakdown.file`, `columns`, `ui_expected`, `action_groups`.
9. **Recent trend** (`src/recent_trend.py`): for each active campaign, compares the recent 28 days with the prior 28 days and with the current run's average, and labels the trend worsening, improving, stable or insufficient_data, with a plain-language reason. Config: `analysis.recent_trend`.
9b. **Lag check** (`src/lag_check.py`): reruns the recent-window label, the recent trend and the trend overrides with each lag in `analysis.recent_trend.lag_check_days` and reports how many change. The configured lag is not changed. Config: `analysis.recent_trend`.
10. **Acquisition journey, what-if and break-even** (`src/journey.py`, `src/what_if.py`, `src/break_even.py`): the journey table per core campaign and the core group, the what-if weekday shift (two variants, a linear estimate, not a bound), and the break-even table, written only when an average revenue per visit is set. Config: `analysis.what_if`, `analysis.break_even`, `conversion_breakdown.intent_categories`.
11. **Dashboard** (`dashboard/app.py`, `dashboard/data.py`, `dashboard/charts.py`): a local Streamlit report with three pages. **Act** asks which campaigns to continue, test or pause. It has a filter row (group, status, minimum tracked actions as a display filter), KPI cards with definitions, a bubble chart against the benchmark and the 1.0x / 2.0x ratio lines from the config, judged-only label counts, a ranked action table and a Not comparable box. **Context** asks whether we can trust the labels: recent change with partial or lagged months marked, the lag check, weekday differences and the decomposition, the what-if range and the acquisition journey, with method details in an expander. **Campaign detail** shows one campaign and opens from the Act ranking. Colours are colour-blind safe, and every label is also named in text. The dashboard reads only the result tables, never the raw exports, and recomputes nothing. Config: `analysis.outputs`, `analysis.caveat_text`, `analysis.footnote_text`.

## 5. How to run

Local only. Nothing is hosted, and no account is needed to run the pipeline once the exports are in place.

```bash
bash run.sh              # whole pipeline: validation to recent trend
bash dashboard.sh        # local dashboard, after bash run.sh
bash run.sh --client synthetic_b   # whole pipeline on the synthetic Company B test data
```

`bash run.sh` creates `.venv` if needed, installs `requirements.txt`, and runs every stage. Outputs go to the ignored `outputs/` folder (`outputs/synthetic_b/` for the synthetic client) and never go to GitHub. The dashboard has a sidebar Client selector; the default is the restaurant.

Muse builds on branches, and CI checks every pull request. I merge in the GitHub web UI.

## 6. How to refresh

1. Export new Google Ads files into `data/raw/` (campaign by day, campaign by month, conversion by campaign and month, monthly totals).
2. Update the paths in the config (`input.files` and `conversion_breakdown.file` in `config/restaurant.yaml`, and the matching entries in `config/validation.yaml`).
3. Run `bash run.sh`.

Overlapping exports do not double count: cleaning drops duplicate rows on date and campaign, keeping the first, and reports how many were removed. The validation stage also checks the new files against the Google Ads UI totals before anything else runs, so a bad export fails loudly instead of silently changing the results.

## 7. Reuse

For another account, change the data files and one config file: copy `config/restaurant.yaml` to a new client config, set its column mapping, file paths, campaign groups, action groups, totals and `output_root`, and run the pipeline with that config. No code changes are needed for a new account with the same export layout.

This was proved on a synthetic Company B dataset (`bash run.sh --client synthetic_b`). The data is generated at run time with a fixed seed into the ignored `outputs/synthetic_b/` folder and is never committed. Reuse needed three code changes, listed honestly in the reuse report (`outputs/synthetic_b/reports/reuse-report.md`) and in the T7 pull request: output-path handling under `output_root` (`src/paths.py`), currency handling for EUR as well as SEK in the number parsers, and the dashboard currency and client selector. The volume rule, the recommendation thresholds and the recent-trend thresholds did not need to change. See [docs/decision-log.md](docs/decision-log.md).

## 8. Decisions that are mine, not the code's

These values are my decisions, written in the config and logged in [docs/decision-log.md](docs/decision-log.md). The code calculates from them; it does not choose them.

- **Campaign groups** (`analysis.campaign_groups`): which campaigns belong together, and which are set aside until the owner answers the open questions.
- **Volume rules** (`analysis.volume_rule`): the minimum tracked actions and active days a campaign needs before it is judged.
- **Recommendation thresholds** (`analysis.recommendation_rules`): the ratios against the core benchmark that separate continue, test and pause_or_review, and how many runs make a repeat.
- **Recent-trend rule** (`analysis.recent_trend`): the window lengths, the reporting lag, and the ratios against the prior 28 days and the run average that separate worsening, improving and stable.

## 9. Limits

- **Tracked actions only.** The results say nothing about real bookings, walk-ins, phone orders or profit.
- **Not proof of cause.** A campaign with a low cost per tracked action did not prove that an offer brought extra customers.
- **Days without activity are not filled.** A missing day means no activity, not zero spend, and gaps are not treated as poor performance.
- **No hour-of-day data.** The exports used here have no hour column, so no hour analysis runs.
- **The last days of data may be incompletely reported.** Tracked actions can be reported with a delay, so the recent-trend stage excludes the last few days; that lag is unverified.
- **Campaign grouping is provisional** until the owner answers the open questions in [docs/decision-log.md](docs/decision-log.md).

## 10. Example questions and answers (synthetic example)

All numbers below come from the synthetic Company B test data (`bash run.sh --client synthetic_b`), daily data 2026-01-05 to 2026-06-30, five made-up campaigns, EUR. They are labelled **synthetic example** and describe no real account.

> Caveat, on every answer: tracked actions only (mainly get-directions requests and phone calls), not bookings or orders. This shows campaign performance, not proof that an offer brought extra customers.

1. **Which campaign has the lowest cost per tracked action?** — Green Fork, at €26.85 per tracked action (651 tracked actions over 101 active days). Next are Golden Ladle at €27.79 and Silver Plate at €28.92. Blue Spoon is highest of the campaigns with enough data, at €31.66.
2. **Which weekday is cheapest?** — Saturday, at €26.92 per tracked action in the pooled core table (625 tracked actions, 17.4% of the tracked actions). Monday is next at €27.15. Friday is the most expensive weekday, at €31.19.
3. **Which campaign is getting worse?** — None. All three active campaigns with enough data are stable. Blue Spoon is closest to worsening: its cost per tracked action is 1.20 times the prior 28 days and 1.01 times the run average, still below the 1.3 worsening threshold.
4. **Which campaigns lack enough data?** — Red Kettle. It has 10 active days and 5 tracked actions in total, below the minimum of 10 tracked actions and 14 active days, so it is labelled insufficient_data and is not ranked. Its recent trend is also insufficient_data (0 tracked actions in both the recent and the prior window).
5. **What should we do with Green Fork?** — It is labelled continue, and its action is "worked well when it ran; candidate to restart". It stopped on 2026-04-15, so its status is ended, and its latest run cost €26.85 per tracked action, 0.92 times the core benchmark — the cheapest of the campaigns with enough data.

## 11. Repository structure and AI use

- `config/`: client-specific settings — `restaurant.yaml` (the restaurant), `synthetic_b.yaml` (the synthetic test client), `validation.yaml` and `validation_synthetic_b.yaml` (UI totals to check exports against).
- `src/`: pipeline code — validation, load, clean, overview, groups, metrics, time patterns, recommendations, conversion mix, recent trend, synthetic data generator, skip and reuse-report stages.
- `dashboard/`: local Streamlit dashboard — `data.py` (all data preparation, testable), `charts.py` (Plotly figures, display only) and `app.py` (display only). Theme in `.streamlit/config.toml`.
- `tests/`: checks, all with made-up data. Run them with `pytest -q`.
- `docs/`: method, decision log, AI usage log.
- `scripts/`: CI guard that blocks data files from tracked files.
- `data/raw/`, `outputs/`, `config/local/`: git-ignored. Client data and outputs live here and never go to GitHub.

Muse implemented the code through reviewed pull requests (issue first, then fix, then push, then merge after my approval and a green CI run). Claude supported planning and review. All decisions and checks are mine: I chose the problem, the groups, the thresholds and the wording, and I verified the results before merging. See [docs/ai-usage-log.md](docs/ai-usage-log.md).

## 12. Data and privacy

Client data is not in this repository. The raw exports live in the git-ignored `data/raw/` folder, and all outputs live in the ignored `outputs/` folder. Committed configs hold only column mappings, campaign groupings and account-level UI totals (aggregates) — no raw files, no row-level data, no account IDs and no credentials. CI blocks data files: `.github/workflows/ci.yml` runs `scripts/check_no_data.py` over every tracked file and fails the run if a data file or a possible customer ID is found.
