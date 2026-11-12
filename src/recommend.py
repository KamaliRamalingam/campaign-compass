"""Recommendations per run and per campaign (T5).

Usage:
    python src/recommend.py --config config/restaurant.yaml

Reads outputs/results/runs.csv and
outputs/results/campaign_summary_day.csv (their paths come from
the config) and writes, all git-ignored:
- outputs/results/recommendations_by_run.csv: per run, ratio
  (run cost per conversion / benchmark), label, reason, caveat.
- outputs/results/recommendations_by_campaign.csv: per campaign,
  the label of its latest run with enough volume, number of runs
  with enough volume, repeat_eligible, last active date and
  status (active or ended), best run, action_text, reason, caveat.
- outputs/results/recommendation_sensitivity.csv: one row per
  campaign and per combination of the sensitivity threshold
  lists, with the resulting label and label_stable.
- outputs/reports/recommend-report.md: counts only (labels,
  status, stable and unstable campaigns).

The benchmark is calculated, not typed in: core group overall
cost per conversion = sum of core spend / sum of core
conversions, from the daily campaign summary.

Labels, from analysis.recommendation_rules:
- insufficient_data if the run's volume_flag is
  insufficient_data (this always wins);
- continue if ratio <= continue_max_ratio;
- test if ratio <= test_max_ratio;
- pause_or_review otherwise (ratio > pause_above_ratio).

repeat_eligible is true only when the campaign has at least
repeat_min_runs runs with enough volume.

Every row gets a plain-language reason built from the numbers
and a caveat column holding the caveat text from
analysis.caveat_text in the config. No claim of extra customers
is made anywhere; the wording is always "tracked conversions".

Only counts per label are printed, never campaign names or rows.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

try:
    from src.clean import load_config
except ImportError:  # running as `python src/recommend.py`
    from clean import load_config

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
LABEL_INSUFFICIENT = "insufficient_data"
LABEL_CONTINUE = "continue"
LABEL_TEST = "test"
LABEL_PAUSE = "pause_or_review"


def compute_benchmark(day_summary):
    """Core group overall cost per conversion, calculated."""
    core = day_summary.loc[day_summary["group"] == "core"]
    if core.empty:
        raise ValueError("no core campaigns in the daily summary")
    conversions = float(core["conversions"].sum())
    if conversions == 0:
        raise ValueError("core conversions total is 0, no benchmark")
    return float(core["spend"].sum()) / conversions


def label_run(ratio, volume_flag, rules):
    """Label one run. insufficient_data always wins."""
    if volume_flag == LABEL_INSUFFICIENT or ratio is None \
            or pd.isna(ratio):
        return LABEL_INSUFFICIENT
    if ratio <= rules["continue_max_ratio"]:
        return LABEL_CONTINUE
    if ratio <= rules["test_max_ratio"]:
        return LABEL_TEST
    return LABEL_PAUSE


def recommend_runs(runs_df, benchmark, rules, volume_rule,
                    caveat):
    """Recommend per run, with ratio, label, reason and caveat."""
    runs = runs_df.copy()
    rows = []
    for campaign, part in runs.groupby("campaign"):
        total_runs = len(part)
        for _, run in part.iterrows():
            cost_per_conversion = run.get("cost_per_conversion")
            ratio = (
                cost_per_conversion / benchmark
                if cost_per_conversion is not None
                and not pd.isna(cost_per_conversion)
                else None
            )
            label = label_run(ratio, run["volume_flag"], rules)
            if label == LABEL_INSUFFICIENT:
                reason = (
                    f"not enough volume to judge: "
                    f"{run['conversions']:.0f} tracked conversions "
                    f"over {int(run['active_days'])} active days; "
                    f"run {int(run['run_number'])} of {total_runs} "
                    f"for this campaign"
                )
            else:
                reason = (
                    f"cost per conversion is {ratio:.2f} times the "
                    f"core benchmark; run {int(run['run_number'])} "
                    f"of {total_runs} for this campaign"
                )
            rows.append({
                "campaign": campaign,
                "group": run["group"],
                "run_number": int(run["run_number"]),
                "start": run["start"],
                "end": run["end"],
                "active_days": int(run["active_days"]),
                "spend": float(run["spend"]),
                "clicks": int(run["clicks"]),
                "conversions": float(run["conversions"]),
                "cost_per_conversion": cost_per_conversion,
                "ratio_to_benchmark": ratio,
                "label": label,
                "reason": reason,
                "caveat": caveat,
            })
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values(["campaign", "run_number"]).reset_index(
        drop=True)


ACTION_TEXT = {
    (LABEL_CONTINUE, "active"): "keep running",
    (LABEL_CONTINUE, "ended"): (
        "worked well when it ran; candidate to restart"),
    (LABEL_TEST, "active"): "keep running, but test changes",
    (LABEL_TEST, "ended"): "restart only with changes",
    (LABEL_PAUSE, "active"): "pause or review",
    (LABEL_PAUSE, "ended"): "do not restart without changes",
    (LABEL_INSUFFICIENT, "active"): "not enough data to judge",
    (LABEL_INSUFFICIENT, "ended"): "not enough data to judge",
}


def action_text(label, status_now, repeat_eligible, best_run,
                latest_run_number):
    """Plain-language action from label and status_now.

    When repeat_eligible is true and the best run is not the
    latest run with enough volume, the best run is named.
    """
    text = ACTION_TEXT[(label, status_now)]
    if (repeat_eligible and best_run is not None
            and best_run["run_number"] != latest_run_number):
        text += (
            f"; best run was run {int(best_run['run_number'])} "
            f"({best_run['start']} to {best_run['end']})"
        )
    return text


def recommend_campaigns(run_recs, day_summary, rules, caveat):
    """Recommend per campaign from its runs.

    The label is the label of its latest run with enough volume,
    or insufficient_data if it has none. repeat_eligible is true
    only when it has at least repeat_min_runs runs with enough
    volume. Campaigns with no runs at all are included as
    insufficient_data.

    Adds last_active_date and status_now (active if the last
    active date is within active_window_days of the latest date
    in the daily data, otherwise ended), the best run with enough
    volume (lowest cost per conversion) and action_text.
    """
    repeat_min = rules.get("repeat_min_runs", 2)
    window = rules.get("active_window_days", 14)
    latest_date = pd.to_datetime(
        day_summary["last_active_date"]).max()
    rows = []
    for _, campaign_row in day_summary.iterrows():
        campaign = campaign_row["campaign"]
        last_active = pd.to_datetime(campaign_row["last_active_date"])
        status_now = ("active" if (latest_date - last_active).days
                      <= window else "ended")
        part = run_recs.loc[run_recs["campaign"] == campaign]
        total_runs = len(part)
        with_volume = part.loc[
            part["label"] != LABEL_INSUFFICIENT
        ]
        runs_with_volume = len(with_volume)
        repeat_eligible = runs_with_volume >= repeat_min
        if with_volume.empty:
            label = LABEL_INSUFFICIENT
            latest_run_number = None
            best_run = None
            reason = (
                f"no run had enough volume to judge: "
                f"{total_runs} runs, 0 with enough volume"
            )
        else:
            latest = with_volume.sort_values("run_number").iloc[-1]
            label = latest["label"]
            latest_run_number = int(latest["run_number"])
            best = with_volume.sort_values(
                "cost_per_conversion").iloc[0]
            best_run = {
                "run_number": int(best["run_number"]),
                "start": best["start"],
                "end": best["end"],
                "cost_per_conversion": float(
                    best["cost_per_conversion"]),
            }
            ratio = latest["ratio_to_benchmark"]
            reason = (
                f"latest run with enough volume is labelled "
                f"{label}; cost per conversion is {ratio:.2f} "
                f"times the core benchmark; {runs_with_volume} "
                f"of {total_runs} runs had enough volume"
            )
        rows.append({
            "campaign": campaign,
            "group": campaign_row["group"],
            "last_active_date": campaign_row["last_active_date"],
            "status_now": status_now,
            "label": label,
            "latest_run_number": latest_run_number,
            "runs_with_volume": runs_with_volume,
            "repeat_eligible": repeat_eligible,
            "best_run_number": (
                best_run["run_number"] if best_run else None),
            "best_run_cost_per_conversion": (
                best_run["cost_per_conversion"]
                if best_run else None),
            "best_run_start": best_run["start"] if best_run else None,
            "best_run_end": best_run["end"] if best_run else None,
            "action_text": action_text(
                label, status_now, repeat_eligible, best_run,
                latest_run_number),
            "reason": reason,
            "caveat": caveat,
        })
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values("campaign").reset_index(drop=True)


def sensitivity_table(run_recs, day_summary, rules):
    """One row per campaign and per sensitivity combination.

    Only combinations where continue_max_ratio <= test_max_ratio
    are used. The label is the label of the campaign's latest run
    with enough volume under those thresholds, or
    insufficient_data if it has none. label_stable is true when
    the campaign's label is the same in every combination.
    """
    continue_list = rules.get("sensitivity_continue_max_ratio") or []
    test_list = rules.get("sensitivity_test_max_ratio") or []
    base = {key: rules[key] for key in
            ("continue_max_ratio", "test_max_ratio",
             "pause_above_ratio")
            if key in rules}
    rows = []
    for _, campaign_row in day_summary.iterrows():
        campaign = campaign_row["campaign"]
        part = run_recs.loc[run_recs["campaign"] == campaign]
        with_volume = part.loc[
            part["label"] != LABEL_INSUFFICIENT
        ]
        ratio = None
        if not with_volume.empty:
            latest = with_volume.sort_values("run_number").iloc[-1]
            ratio = latest["ratio_to_benchmark"]
        labels = []
        for continue_max in continue_list:
            for test_max in test_list:
                if continue_max > test_max:
                    continue
                trial = dict(base)
                trial["continue_max_ratio"] = continue_max
                trial["test_max_ratio"] = test_max
                label = label_run(
                    ratio, "ok" if ratio is not None else
                    LABEL_INSUFFICIENT, trial)
                labels.append(label)
                rows.append({
                    "campaign": campaign,
                    "group": campaign_row["group"],
                    "continue_max_ratio": continue_max,
                    "test_max_ratio": test_max,
                    "label": label,
                })
        stable = len(set(labels)) <= 1
        for row in rows:
            if row["campaign"] == campaign:
                row["label_stable"] = stable
    return pd.DataFrame(rows)


def write_recommend_report(report_path, run_recs, campaign_recs,
                           sensitivity, benchmark):
    """Write the recommend report: counts only, no names."""
    lines = ["# Recommend report", ""]
    lines.append(
        f"- Core benchmark cost per conversion: {benchmark:.2f}"
    )
    lines.append(f"- Runs: {len(run_recs)}")
    lines.append(f"- Campaigns: {len(campaign_recs)}")
    lines.append("")
    lines.append("## Runs per label")
    lines.append("")
    for label, count in run_recs["label"].value_counts().items():
        lines.append(f"- {label}: {int(count)}")
    lines.append("")
    lines.append("## Campaigns per label")
    lines.append("")
    for label, count in campaign_recs["label"].value_counts().items():
        lines.append(f"- {label}: {int(count)}")
    lines.append("")
    lines.append(
        "- Campaigns repeat eligible: "
        f"{int(campaign_recs['repeat_eligible'].sum())}"
    )
    lines.append("")
    lines.append("## Campaigns per status")
    lines.append("")
    for status, count in campaign_recs["status_now"].value_counts().items():
        lines.append(f"- {status}: {int(count)}")
    lines.append("")
    if not sensitivity.empty:
        stable = sensitivity.drop_duplicates("campaign")[
            "label_stable"]
        lines.append("## Sensitivity")
        lines.append("")
        lines.append(
            f"- Campaigns with a stable label: "
            f"{int(stable.sum())}")
        lines.append(
            f"- Campaigns with an unstable label: "
            f"{int((~stable).sum())}")
        lines.append("")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Compute the recommendations and write them and the report."""
    parser = argparse.ArgumentParser(
        description="Compute recommendations per run and campaign."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    analysis = config["analysis"]
    outputs = analysis.get("outputs") or {}
    rules = analysis.get("recommendation_rules") or {}
    volume_rule = analysis.get("volume_rule") or {}
    try:
        runs_df = pd.read_csv(outputs["runs"])
        day_summary = pd.read_csv(outputs["campaign_summary_day"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    try:
        benchmark = compute_benchmark(day_summary)
        caveat = analysis["caveat_text"]
        run_recs = recommend_runs(runs_df, benchmark, rules,
                                  volume_rule, caveat)
        campaign_recs = recommend_campaigns(
            run_recs, day_summary, rules, caveat)
        sensitivity = sensitivity_table(run_recs, day_summary, rules)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    run_out = Path(outputs.get(
        "recommendations_by_run",
        "outputs/results/recommendations_by_run.csv"))
    campaign_out = Path(outputs.get(
        "recommendations_by_campaign",
        "outputs/results/recommendations_by_campaign.csv"))
    sensitivity_out = Path(outputs.get(
        "recommendation_sensitivity",
        "outputs/results/recommendation_sensitivity.csv"))
    report_out = Path(outputs.get(
        "recommend_report", "outputs/reports/recommend-report.md"))
    for path in (run_out, campaign_out, sensitivity_out, report_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    run_recs.to_csv(run_out, index=False)
    campaign_recs.to_csv(campaign_out, index=False)
    sensitivity.to_csv(sensitivity_out, index=False)
    write_recommend_report(report_out, run_recs, campaign_recs,
                           sensitivity, benchmark)

    print("Runs per label:")
    for label, count in run_recs["label"].value_counts().items():
        print(f"  {label}: {int(count)}")
    print("Campaigns per label:")
    for label, count in campaign_recs["label"].value_counts().items():
        print(f"  {label}: {int(count)}")
    print("Campaigns per status:")
    for status, count in campaign_recs["status_now"].value_counts().items():
        print(f"  {status}: {int(count)}")
    if not sensitivity.empty:
        stable = sensitivity.drop_duplicates("campaign")[
            "label_stable"]
        print(f"Campaigns with a stable label: {int(stable.sum())}")
        print(f"Campaigns with an unstable label: "
              f"{int((~stable).sum())}")
    print(f"wrote: {run_out}")
    print(f"wrote: {campaign_out}")
    print(f"wrote: {sensitivity_out}")
    print(f"report: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
