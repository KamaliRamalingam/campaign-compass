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
  status (active or ended), best run, action_text, reason, caveat,
  and base_label / base_action_text / base_reason (copies that
  src/recent_trend.py rebuilds from, so it is idempotent).
- outputs/results/recommendation_sensitivity.csv: one row per
  campaign and per combination of the sensitivity threshold
  lists, with the resulting label and label_stable.
- outputs/reports/recommend-report.md: counts only (labels,
  status, stable and unstable campaigns).

The benchmark is calculated, not typed in: sum of spend / sum
of conversions over the campaigns in
recommendation_rules.benchmark.groups (default ["core"]), from
the daily campaign summary. With benchmark.leave_one_out
(default false) each campaign in those groups is compared with
the benchmark of the other campaigns in them. Each run row
carries the benchmark it used and its basis. The report lists
the pooled and leave-one-out benchmarks with and without the
not_comparable groups.

Fixed labels, which win over every other label:
- not_comparable for a campaign whose group is in
  recommendation_rules.not_comparable_groups (default none),
  e.g. Performance Max: never compared with the benchmark;
- not_judged, reason "group X not evaluated", for a campaign
  whose group is outside recommendation_rules.judged_groups,
  when that key is set (default: every group is judged).

Labels, from analysis.recommendation_rules:
- insufficient_data if the run's volume_flag is
  insufficient_data (this always wins);
- continue if ratio <= continue_max_ratio;
- test if ratio <= test_max_ratio;
- pause_or_review otherwise (ratio > test_max_ratio).

test_max_ratio is the only pause boundary. A config that
still sets pause_above_ratio gets a warning that it is not
used.

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
    from src.paths import apply_output_root
    from src.clean import load_config
except ImportError:  # running as `python src/recommend.py`
    from clean import load_config
    from paths import apply_output_root

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
LABEL_INSUFFICIENT = "insufficient_data"
LABEL_CONTINUE = "continue"
LABEL_TEST = "test"
LABEL_PAUSE = "pause_or_review"
LABEL_NOT_COMPARABLE = "not_comparable"
LABEL_NOT_JUDGED = "not_judged"
DEFAULT_BENCHMARK_GROUPS = ("core",)
BASE_COLUMNS = ("label", "action_text", "reason")
BASIS_POOLED = "pooled"
BASIS_LOO = "leave_one_out"
BASIS_LOO_FALLBACK = "pooled (leave-one-out not possible)"


def compute_benchmark(day_summary, groups=DEFAULT_BENCHMARK_GROUPS,
                      exclude=None):
    """Pooled cost per conversion of the campaigns in groups.

    Sum of spend / sum of conversions over the campaigns whose
    group is in groups, leaving out the campaign named in
    exclude (for a leave-one-out benchmark).
    """
    groups = list(groups)
    part = day_summary.loc[day_summary["group"].isin(groups)]
    if exclude is not None:
        part = part.loc[part["campaign"] != exclude]
    names = "+".join(groups)
    if part.empty:
        raise ValueError(
            f"no campaigns in benchmark groups {names} in the daily "
            f"summary")
    conversions = float(part["conversions"].sum())
    if conversions == 0:
        raise ValueError(
            f"{names} conversions total is 0, no benchmark")
    return float(part["spend"].sum()) / conversions


def benchmark_settings(rules):
    """(groups, leave_one_out) from rules["benchmark"].

    Defaults: groups ["core"], leave_one_out false, which is the
    benchmark used before these keys existed.
    """
    settings = rules.get("benchmark") or {}
    groups = list(settings.get("groups") or DEFAULT_BENCHMARK_GROUPS)
    return groups, bool(settings.get("leave_one_out", False))


def benchmark_name(groups, leave_one_out):
    """Name used in reasons, e.g. "core benchmark (leave-one-out)"."""
    name = f"{'+'.join(groups)} benchmark"
    if leave_one_out:
        name += " (leave-one-out)"
    return name


def benchmarks_by_campaign(day_summary, groups, leave_one_out):
    """{campaign: (benchmark, basis)} for every campaign.

    With leave_one_out, a campaign in the benchmark groups is
    compared with the pooled benchmark of the other campaigns in
    those groups (basis "leave_one_out"). If that leaves no
    conversions, the pooled benchmark is used with basis
    "pooled (leave-one-out not possible)". Every other campaign
    gets the pooled benchmark (basis "pooled").
    """
    pooled = compute_benchmark(day_summary, groups)
    result = {}
    for _, row in day_summary.iterrows():
        campaign = row["campaign"]
        if leave_one_out and row["group"] in groups:
            try:
                value = compute_benchmark(day_summary, groups,
                                          exclude=campaign)
                result[campaign] = (value, BASIS_LOO)
            except ValueError:
                result[campaign] = (pooled, BASIS_LOO_FALLBACK)
        else:
            result[campaign] = (pooled, BASIS_POOLED)
    return result


def fixed_label(group, rules):
    """not_comparable, not_judged, or None for a campaign group.

    not_comparable_groups are never compared with the benchmark.
    When judged_groups is set, any group outside it (and outside
    not_comparable_groups) is not judged. Without these keys
    every group is judged, as before.
    """
    if group in (rules.get("not_comparable_groups") or []):
        return LABEL_NOT_COMPARABLE
    judged = rules.get("judged_groups")
    if judged is not None and group not in judged:
        return LABEL_NOT_JUDGED
    return None


def _fixed_reason(label, group, cost_per_conversion, name):
    """Reason text for a not_comparable or not_judged row."""
    if label == LABEL_NOT_JUDGED:
        return f"group {group} not evaluated"
    cost = (f"cost per conversion is {cost_per_conversion:.2f}; "
            if cost_per_conversion is not None
            and not pd.isna(cost_per_conversion) else "")
    return (f"group {group} is not comparable with the {name}; "
            f"{cost}judge against its own history")


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


def recommend_runs(runs_df, benchmark, rules, caveat,
                   per_campaign=None):
    """Recommend per run, with ratio, label, reason and caveat.

    benchmark is the pooled benchmark. per_campaign, from
    benchmarks_by_campaign, gives each campaign its own
    (benchmark, basis); without it every run uses benchmark with
    basis "pooled", as before. Runs of not_comparable and
    not_judged groups get that label and no ratio.
    """
    groups, leave_one_out = benchmark_settings(rules)
    name = benchmark_name(groups, leave_one_out)
    runs = runs_df.copy()
    rows = []
    for campaign, part in runs.groupby("campaign"):
        total_runs = len(part)
        run_benchmark, basis = (per_campaign or {}).get(
            campaign, (benchmark, BASIS_POOLED))
        for _, run in part.iterrows():
            cost_per_conversion = run.get("cost_per_conversion")
            fixed = fixed_label(run["group"], rules)
            ratio = (
                cost_per_conversion / run_benchmark
                if fixed is None
                and cost_per_conversion is not None
                and not pd.isna(cost_per_conversion)
                else None
            )
            label = fixed or label_run(ratio, run["volume_flag"], rules)
            if fixed is not None:
                fixed_text = _fixed_reason(
                    fixed, run["group"], cost_per_conversion, name)
                reason = (
                    f"{fixed_text}; run {int(run['run_number'])} "
                    f"of {total_runs} for this campaign"
                )
            elif label == LABEL_INSUFFICIENT:
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
                    f"{name}; run {int(run['run_number'])} "
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
                "volume_flag": run["volume_flag"],
                "cost_per_conversion": cost_per_conversion,
                "benchmark": None if fixed else run_benchmark,
                "benchmark_basis": None if fixed else basis,
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
    (LABEL_NOT_COMPARABLE, "active"): (
        "judge against its own history, not the benchmark"),
    (LABEL_NOT_COMPARABLE, "ended"): (
        "judge against its own history, not the benchmark"),
    (LABEL_NOT_JUDGED, "active"): "not evaluated: group not judged",
    (LABEL_NOT_JUDGED, "ended"): "not evaluated: group not judged",
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
        fixed = fixed_label(campaign_row["group"], rules)
        if fixed is not None:
            # not_comparable / not_judged: no benchmark, no best
            # run, never repeat eligible.
            label = fixed
            latest_run_number = (
                int(part["run_number"].max()) if total_runs else None)
            best_run = None
            repeat_eligible = False
            runs_with_volume = int(
                (part["volume_flag"] == "ok").sum()
            ) if "volume_flag" in part.columns else 0
            latest_cost = (
                part.sort_values("run_number").iloc[-1][
                    "cost_per_conversion"] if total_runs else None)
            groups, leave_one_out = benchmark_settings(rules)
            reason = _fixed_reason(
                fixed, campaign_row["group"], latest_cost,
                benchmark_name(groups, leave_one_out))
        elif with_volume.empty:
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
    # Base copies: later stages (recent_trend) rebuild label,
    # action_text and reason from these, so rerunning them never
    # stacks changes on top of earlier ones.
    for column in BASE_COLUMNS:
        table[f"base_{column}"] = table[column]
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
            ("continue_max_ratio", "test_max_ratio")
            if key in rules}
    rows = []
    for _, campaign_row in day_summary.iterrows():
        campaign = campaign_row["campaign"]
        part = run_recs.loc[run_recs["campaign"] == campaign]
        with_volume = part.loc[
            part["label"] != LABEL_INSUFFICIENT
        ]
        fixed = fixed_label(campaign_row["group"], rules)
        ratio = None
        if fixed is None and not with_volume.empty:
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
                # not_comparable / not_judged do not depend on
                # the thresholds, so they are stable.
                label = fixed or label_run(
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


def benchmark_summary(day_summary, rules):
    """Benchmark variants for the report: numbers only, no names.

    Pooled and leave-one-out (min to max over the campaigns in
    the groups) for benchmark.groups, and for benchmark.groups
    plus not_comparable_groups (when there are any), so the
    effect of leaving those groups out is visible.
    """
    groups, leave_one_out = benchmark_settings(rules)
    variants = [groups]
    extra = [group for group in
             (rules.get("not_comparable_groups") or [])
             if group not in groups]
    if extra:
        variants.append(groups + extra)
    rows = []
    for variant in variants:
        try:
            pooled = compute_benchmark(day_summary, variant)
        except ValueError:
            continue
        # Only campaigns inside the variant's groups get the
        # leave_one_out basis.
        loo_values = [value for value, basis in benchmarks_by_campaign(
                          day_summary, variant, True).values()
                      if basis == BASIS_LOO]
        rows.append({
            "groups": variant,
            "pooled": pooled,
            "loo_min": min(loo_values) if loo_values else None,
            "loo_max": max(loo_values) if loo_values else None,
        })
    return {"groups": groups, "leave_one_out": leave_one_out,
            "variants": rows}


def write_recommend_report(report_path, run_recs, campaign_recs,
                           sensitivity, benchmark, benchmarks=None):
    """Write the recommend report: counts only, no names.

    benchmarks, from benchmark_summary, adds a Benchmarks
    section with group names and numbers only.
    """
    lines = ["# Recommend report", ""]
    lines.append(
        f"- Core benchmark cost per conversion: {benchmark:.2f}"
    )
    lines.append(f"- Runs: {len(run_recs)}")
    lines.append(f"- Campaigns: {len(campaign_recs)}")
    lines.append("")
    if benchmarks:
        lines.append("## Benchmarks")
        lines.append("")
        lines.append(
            f"- Benchmark groups: {'+'.join(benchmarks['groups'])}; "
            f"leave-one-out: "
            f"{'on' if benchmarks['leave_one_out'] else 'off'}")
        for row in benchmarks["variants"]:
            names = "+".join(row["groups"])
            lines.append(
                f"- Pooled ({names}): {row['pooled']:.2f}")
            if row["loo_min"] is not None:
                lines.append(
                    f"- Leave-one-out ({names}): "
                    f"{row['loo_min']:.2f} to {row['loo_max']:.2f}")
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
        config = apply_output_root(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    analysis = config["analysis"]
    outputs = analysis.get("outputs") or {}
    rules = analysis.get("recommendation_rules") or {}
    if "pause_above_ratio" in rules:
        print("WARNING: recommendation_rules.pause_above_ratio is "
              "not used (test_max_ratio is the pause boundary); "
              "remove it from the config")
    try:
        runs_df = pd.read_csv(outputs["runs"])
        day_summary = pd.read_csv(outputs["campaign_summary_day"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    try:
        groups, leave_one_out = benchmark_settings(rules)
        benchmark = compute_benchmark(day_summary, groups)
        per_campaign = benchmarks_by_campaign(
            day_summary, groups, leave_one_out)
        benchmarks = benchmark_summary(day_summary, rules)
        caveat = analysis["caveat_text"]
        run_recs = recommend_runs(runs_df, benchmark, rules, caveat,
                                  per_campaign)
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
                           sensitivity, benchmark, benchmarks)

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
