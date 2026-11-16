"""Data preparation for the local Streamlit dashboard (T8).

All data preparation lives here, in pure functions that are
readable and testable. dashboard/app.py only displays.

Reads only outputs/results/ and outputs/reports/ — never
data/raw/. Table paths come from the config where they exist
(analysis.outputs); otherwise the one DEFAULT_PATHS constant
below is used. No campaign names, thresholds or other values
are hard-coded here.

If a result table is missing, load_tables raises
FileNotFoundError with "Run bash run.sh first". Optional tables
(written only when the client's config turns a stage on) load
as None and the page says so.

The dashboard only reads: labels are the FINAL labels in
recommendations_by_campaign.csv (after the trend override), and
no metric, ratio or label is recomputed here. Functions only
filter, sort, join on campaign or run number, and rename for
display.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "restaurant.yaml"

# Fallback paths, used only when the config has no path for a
# table. Keys match analysis.outputs in config/restaurant.yaml.
DEFAULT_PATHS = {
    "recommendations_by_campaign":
        "outputs/results/recommendations_by_campaign.csv",
    "runs": "outputs/results/runs.csv",
    "weekday_core": "outputs/results/weekday_core.csv",
    "weekday_by_campaign": "outputs/results/weekday_by_campaign.csv",
    "monthly_by_campaign": "outputs/results/monthly_by_campaign.csv",
    "timeline_by_campaign": "outputs/results/timeline_by_campaign.csv",
    "campaign_summary_day": "outputs/results/campaign_summary_day.csv",
    "campaign_summary_intent":
        "outputs/results/campaign_summary_intent.csv",
    "group_summary": "outputs/results/group_summary.csv",
    "conversion_mix_by_campaign":
        "outputs/results/conversion_mix_by_campaign.csv",
    "conversion_mix_by_run":
        "outputs/results/conversion_mix_by_run.csv",
    "recent_trend": "outputs/results/recent_trend.csv",
    "weekly_by_campaign": "outputs/results/weekly_by_campaign.csv",
    "journey_by_campaign": "outputs/results/journey_by_campaign.csv",
    "what_if_weekday_shift":
        "outputs/results/what_if_weekday_shift.csv",
    "recommendations_by_run":
        "outputs/results/recommendations_by_run.csv",
    "recommendation_sensitivity":
        "outputs/results/recommendation_sensitivity.csv",
    "benchmarks": "outputs/results/benchmarks.csv",
}

REQUIRED_TABLES = list(DEFAULT_PATHS)

# Written only when a stage is turned on in the client's config;
# None when missing.
OPTIONAL_PATHS = {
    "lag_check": "outputs/results/lag_check.csv",
    "weekday_mix_by_campaign":
        "outputs/results/weekday_mix_by_campaign.csv",
    "weekday_leave_one_out":
        "outputs/results/weekday_leave_one_out.csv",
    "weekday_top_days": "outputs/results/weekday_top_days.csv",
}

# Labels hidden on the Summary page unless asked for.
HIDDEN_LABELS = ("not_judged", "insufficient_data")
NOT_COMPARABLE = "not_comparable"
ALL_GROUPS = "All groups"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
# Short names map to the same weekday numbers (Monday = 0).
WEEKDAY_ALIASES = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def weekday_number(value):
    """Weekday number (Monday = 0) for a weekday value.

    Accepts full names, short names and any capitalisation
    ("Monday", "mon", "MON"), and numbers 0-6 (Monday = 0, as in
    pandas day_of_week) or 7 for Sunday (the 1-7 scheme).
    Raises ValueError for anything else.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = int(value)
        if 0 <= number <= 6:
            return number
        if number == 7:
            return 6
        raise ValueError(f"unknown weekday value: {value!r}")
    text = str(value).strip().lower()
    if text.isdigit():
        return weekday_number(int(text))
    if text in WEEKDAY_ALIASES:
        return WEEKDAY_ALIASES[text]
    raise ValueError(f"unknown weekday value: {value!r}")


def weekday_numbers(values):
    """Weekday numbers for a column of weekday values.

    Raises ValueError listing only the unknown values, never
    crashing with a bare list.index error.
    """
    numbers = []
    unknown = []
    for value in values:
        try:
            numbers.append(weekday_number(value))
        except ValueError:
            unknown.append(str(value))
    if unknown:
        seen = sorted(set(unknown))
        raise ValueError(
            "Unknown weekday value(s): " + ", ".join(seen)
            + ". Expected a weekday name or a number 0-6."
        )
    return numbers


def load_config(config_path=None):
    """Load the restaurant config as a dict."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def caveat_text(config):
    """The caveat text, from analysis.caveat_text in the config."""
    return config["analysis"]["caveat_text"]


def client_config_path(client, config_dir=None):
    """Config file of a client: config/<client>.yaml.

    "restaurant" is config/restaurant.yaml. A client without its
    own config is an error: falling back to another client's
    config would show the wrong caveat and groups.
    """
    base = Path(config_dir) if config_dir else REPO_ROOT / "config"
    path = base / f"{client}.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"No config for client {client!r}: {path} is missing")
    return path


def client_output_root(client, config, repo_root=None):
    """Output folder of a client, or None for outputs/ itself.

    analysis.output_root from the client's config when set (for
    example outputs/synthetic_b), otherwise outputs/<client> for
    any client other than "restaurant".
    """
    root = Path(repo_root) if repo_root else REPO_ROOT
    configured = (config.get("analysis") or {}).get("output_root")
    if configured and configured != "outputs":
        return root / configured
    if client == "restaurant":
        return None
    return root / "outputs" / client


def list_clients(outputs_dir=None):
    """Client names with result tables to show in the dashboard.

    "restaurant" first (the default, from outputs/ itself), then
    any folder directly under outputs/ that has a results table
    (for example synthetic_b, from outputs/synthetic_b/results/).
    """
    base = Path(outputs_dir) if outputs_dir else REPO_ROOT / "outputs"
    clients = ["restaurant"]
    if base.is_dir():
        for folder in sorted(base.iterdir()):
            if folder.is_dir() and (
                folder / "results"
                / "recommendations_by_campaign.csv"
            ).is_file():
                clients.append(folder.name)
    return clients


def _resolve(configured, root=None, output_root=None):
    """A configured output path under root or a client folder."""
    if output_root is not None:
        relative = Path(configured)
        if relative.parts and relative.parts[0] == "outputs":
            relative = Path(*relative.parts[1:])
        return Path(output_root) / relative
    base = Path(root) if root else REPO_ROOT
    return base / configured


def table_paths(config, root=None, output_root=None, defaults=None):
    """Resolve every table path, from config or default.

    root is the project root (as in the tests). output_root is
    a client output folder such as outputs/synthetic_b: each
    configured path has its leading "outputs/" part replaced
    by it, so the same config paths work for every client.
    defaults is DEFAULT_PATHS (required tables) unless given.
    """
    outputs = (config.get("analysis") or {}).get("outputs") or {}
    defaults = DEFAULT_PATHS if defaults is None else defaults
    return {key: _resolve(outputs.get(key, default), root, output_root)
            for key, default in defaults.items()}


def load_tables(config=None, root=None, output_root=None):
    """Read all required result tables. Returns name -> DataFrame.

    Raises FileNotFoundError naming the missing file and telling
    the user to run bash run.sh first.
    """
    config = config if config is not None else load_config()
    paths = table_paths(config, root=root, output_root=output_root)
    tables = {}
    for key, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"Run bash run.sh first: {path} is missing")
        tables[key] = pd.read_csv(path)
    return tables


def load_optional_tables(config, root=None, output_root=None):
    """Read the optional tables; a missing one is None."""
    paths = table_paths(config, root=root, output_root=output_root,
                        defaults=OPTIONAL_PATHS)
    return {key: (pd.read_csv(path) if path.is_file() else None)
            for key, path in paths.items()}


def break_even_path(config, root=None, output_root=None):
    """Path of the optional break-even table.

    The break-even table exists only when the config sets
    avg_revenue_per_visit, so it is not a required table.
    """
    outputs = (config.get("analysis") or {}).get("outputs") or {}
    configured = outputs.get(
        "break_even", "outputs/results/break_even.csv")
    return _resolve(configured, root, output_root)


def load_break_even(config=None, root=None, output_root=None):
    """Read the break-even table, or None when it does not exist."""
    config = config if config is not None else load_config()
    path = break_even_path(
        config, root=root, output_root=output_root)
    if not path.is_file():
        return None
    return pd.read_csv(path)


def journey_display(journey):
    """Journey table for display: intent shares as percentages.

    The CSV stores the shares as fractions; the dashboard
    shows them as percentages with two decimals. The input
    table is unchanged.
    """
    table = journey.copy()
    for column in ("directions_share", "calls_share",
                   "store_visits_share"):
        if column in table.columns:
            table[column] = (table[column] * 100.0).round(2)
    return table


def journey_campaigns(journey):
    """Journey rows for campaigns only, without the core group row."""
    return journey.loc[
        journey["campaign"] != "core group"].copy()


def data_date_range(summary_day):
    """(first active date, last active date) in the daily data."""
    first = pd.to_datetime(
        summary_day["first_active_date"]).min().date()
    last = pd.to_datetime(
        summary_day["last_active_date"]).max().date()
    return first, last


def last_updated(paths):
    """Latest file modification time of the given files."""
    times = [datetime.fromtimestamp(Path(path).stat().st_mtime)
             for path in paths]
    return max(times)


def conversion_shares(mix_by_campaign):
    """Share of tracked actions by action, with its action group.

    The Conversions column is the tracked actions; the column is
    renamed so the dashboard says "tracked actions" everywhere.
    """
    grouped = mix_by_campaign.groupby(
        ["action", "action_group"], as_index=False).agg(
        tracked_actions=("conversions", "sum"),
        all_conversions=("all_conversions", "sum"),
    )
    total = float(grouped["tracked_actions"].sum())
    grouped["share"] = grouped["tracked_actions"] / total if total else 0.0
    grouped["share_pct"] = (grouped["share"] * 100.0).round(2)
    return grouped.sort_values(
        "tracked_actions", ascending=False).reset_index(drop=True)


def engagement_share(mix_by_campaign):
    """Share of tracked actions from the engagement action group."""
    total = float(mix_by_campaign["conversions"].sum())
    if not total:
        return 0.0
    engagement = float(mix_by_campaign.loc[
        mix_by_campaign["action_group"] == "engagement",
        "conversions"].sum())
    return engagement / total


def engagement_share_all(mix_by_campaign):
    """Share of All conv. from the engagement action group.

    Calculated from the data, not typed in.
    """
    total = float(mix_by_campaign["all_conversions"].sum())
    if not total:
        return 0.0
    engagement = float(mix_by_campaign.loc[
        mix_by_campaign["action_group"] == "engagement",
        "all_conversions"].sum())
    return engagement / total


def overview_groups(group_summary):
    """Spend and conversions by group, biggest spend first."""
    return group_summary.sort_values(
        "spend", ascending=False).reset_index(drop=True)


def core_campaigns(summary_day, recommendations):
    """Core campaigns: spend, tracked actions, cost, label, action.

    Tracked actions are the conversions column, renamed so the
    dashboard says "tracked actions" everywhere.
    """
    merged = summary_day.loc[summary_day["group"] == "core"].merge(
        recommendations[["campaign", "label", "status_now",
                         "action_text"]],
        on="campaign", how="left")
    table = pd.DataFrame({
        "campaign": merged["campaign"],
        "spend": merged["spend"],
        "tracked_actions": merged["conversions"],
        "cost_per_tracked_action": merged["cost_per_conversion"],
        "label": merged["label"],
        "status_now": merged["status_now"],
        "action_text": merged["action_text"],
    })
    return table.sort_values(
        "spend", ascending=False).reset_index(drop=True)


def comparison_data(summary_day, recommendations):
    """Core campaigns for the cost-per-tracked-action chart.

    Sorted cheapest first. Campaigns with insufficient_data are
    marked and not ranked (rank is empty for them).
    """
    core = core_campaigns(summary_day, recommendations)
    volume = summary_day.set_index("campaign")["volume_flag"]
    core["volume_flag"] = core["campaign"].map(volume)
    ranked = core.loc[
        core["volume_flag"] != "insufficient_data"].copy()
    ranked = ranked.sort_values("cost_per_tracked_action")
    ranked["rank"] = range(1, len(ranked) + 1)
    unranked = core.loc[
        core["volume_flag"] == "insufficient_data"].copy()
    unranked["rank"] = None
    table = pd.concat([ranked, unranked], ignore_index=True)
    return table.sort_values(
        "cost_per_tracked_action").reset_index(drop=True)


def runs_for_campaign(runs_df, campaign):
    """One campaign's runs, in run order."""
    part = runs_df.loc[runs_df["campaign"] == campaign].copy()
    table = pd.DataFrame({
        "run_number": part["run_number"],
        "start": part["start"],
        "end": part["end"],
        "active_days": part["active_days"],
        "spend": part["spend"],
        "tracked_actions": part["conversions"],
        "cost_per_tracked_action": part["cost_per_conversion"],
        "volume_flag": part["volume_flag"],
    })
    return table.sort_values("run_number").reset_index(drop=True)


def weekday_core_table(weekday_core):
    """Pooled core weekday table, Monday to Sunday."""
    table = weekday_core.copy()
    table["weekday_no"] = weekday_numbers(table["weekday"])
    table = table.sort_values("weekday_no").drop(
        columns=["weekday_no"])
    table["tracked_actions"] = table["conversions"]
    table["cost_per_tracked_action"] = table["cost_per_conversion"]
    table = table.drop(
        columns=["conversions", "cost_per_conversion"])
    # Tracked actions and cost per tracked action first, so
    # they are visible even in a narrow table.
    first = ["weekday", "tracked_actions",
             "cost_per_tracked_action"]
    rest = [column for column in table.columns
            if column not in first]
    return table[first + rest].reset_index(drop=True)


def weekday_campaign_table(weekday_by_campaign, campaign):
    """One campaign's weekday table, Monday to Sunday."""
    part = weekday_by_campaign.loc[
        weekday_by_campaign["campaign"] == campaign].copy()
    return weekday_core_table(part)


def trend_for_campaign(timeline_df, campaign):
    """One campaign's monthly trend, from the timeline table."""
    part = timeline_df.loc[
        timeline_df["campaign"] == campaign].copy()
    table = pd.DataFrame({
        "month": part["month"],
        "source": part["source"],
        "active_days": part["active_days"],
        "spend": part["spend"],
        "tracked_actions": part["conversions"],
        "cost_per_tracked_action": part["cost_per_conversion"],
    })
    return table.sort_values("month").reset_index(drop=True)


def recommendations_view(recommendations):
    """Recommendations table for display, one row per campaign."""
    columns = ["campaign", "group", "label", "status_now",
               "action_text", "best_run_number", "best_run_start",
               "best_run_end", "reason"]
    return recommendations[columns].sort_values(
        "campaign").reset_index(drop=True)


def recommendations_display(recommendations):
    """Recommendations for the Recommendations page.

    Campaign, label, status_now, recent_trend, ratio against
    the run average, ratio against the prior window, trend
    reason, action_text and reason. The group and run columns
    are hidden. Older result files without recent_trend or the
    ratios get an empty value.
    """
    table = recommendations.copy()
    if "recent_trend" not in table.columns:
        table["recent_trend"] = ""
    if "ratio_vs_run_average" not in table.columns:
        table["ratio_vs_run_average"] = None
    if "recent_vs_prior_ratio" not in table.columns:
        table["recent_vs_prior_ratio"] = None
    if "trend_reason" not in table.columns:
        table["trend_reason"] = ""
    columns = ["campaign", "label", "status_now", "recent_trend",
               "ratio_vs_run_average", "recent_vs_prior_ratio",
               "trend_reason", "action_text", "reason"]
    return table[columns].sort_values(
        "campaign").reset_index(drop=True)


def format_ratio(ratio):
    """Ratio vs run average with two decimals, or a dash."""
    if ratio is None or pd.isna(ratio):
        return "—"
    return f"{float(ratio):.2f}"


def weekly_for_campaign(weekly_df, campaign):
    """One campaign's weekly table, earliest week first."""
    part = weekly_df.loc[
        weekly_df["campaign"] == campaign].copy()
    table = pd.DataFrame({
        "week_start": part["week_start"],
        "active_days": part["active_days"],
        "spend": part["spend"],
        "tracked_actions": part["tracked_actions"],
        "cost_per_tracked_action":
            part["cost_per_tracked_action"],
    })
    return table.sort_values("week_start").reset_index(drop=True)


def display_table(table):
    """A copy of a table with display wording, for the dashboard.

    "conversions" becomes "tracked actions" and
    "cost_per_conversion" becomes "cost per tracked action".
    Rates are shown as percentages with two decimals:
    conversion_rate (a fraction) becomes "tracked actions per
    click (%)", and shares that are already percentages
    (share_of_campaign_conversions, share_of_spend,
    share_of_conversions) become "... (%)", rounded to two
    decimals. This renames and converts at display time only:
    the returned copy is changed, the input table and the CSV
    files are unchanged.

    If a table has both "conversions" and "tracked_actions"
    they hold the same numbers and would both rename to
    "tracked actions", so the "conversions" column is dropped
    instead of producing two columns with the same name.
    """
    result = table.copy()
    if ("conversions" in result.columns
            and "tracked_actions" in result.columns):
        result = result.drop(columns=["conversions"])
    if "conversion_rate" in result.columns:
        result["conversion_rate"] = (
            result["conversion_rate"] * 100.0).round(2)
    for column in ("share_of_campaign_conversions",
                   "share_of_spend", "share_of_conversions"):
        if column in result.columns:
            result[column] = result[column].round(2)
    renamed = {}
    for column in result.columns:
        if column == "conversion_rate":
            renamed[column] = "tracked actions per click (%)"
            continue
        if column in ("share_of_campaign_conversions",
                      "share_of_spend", "share_of_conversions"):
            name = column.replace("conversions", "tracked actions")
            renamed[column] = name.replace("_", " ") + " (%)"
            continue
        name = column
        name = name.replace("cost_per_conversion",
                            "cost per tracked action")
        name = name.replace("conversions", "tracked actions")
        name = name.replace("_", " ")
        renamed[column] = name
    return result.rename(columns=renamed)


# --- PR 4: pages built on final labels ---------------------------

def campaigns_in_group(recommendations, group):
    """Campaign names in a group, or all for ALL_GROUPS / None."""
    if group in (None, ALL_GROUPS):
        return sorted(recommendations["campaign"])
    return sorted(recommendations.loc[
        recommendations["group"] == group, "campaign"])


def group_options(recommendations):
    """Sidebar choices: ALL_GROUPS, then each group."""
    return [ALL_GROUPS] + sorted(recommendations["group"].unique())


def final_label_counts(recommendations):
    """Count of campaigns per FINAL label, largest first."""
    counts = recommendations["label"].value_counts()
    return pd.DataFrame({"label": counts.index,
                         "campaigns": counts.values})


def _period(start, end):
    """"start to end", or "" when either is missing."""
    if start is None or end is None or pd.isna(start) or pd.isna(end):
        return ""
    return f"{start} to {end}"


def summary_rows(recommendations, recent_trend, show_hidden=False,
                 group=None):
    """One row per judged campaign for the Summary page.

    Final label, status now, recent trend, action text, and the
    period each signal covers: the label's (recent window or
    run, from label_period_start/end) and the trend's recent
    window (from recent_trend.csv). not_comparable campaigns are
    left out (they get their own box); not_judged and
    insufficient_data only when show_hidden is true.
    """
    recs = recommendations.copy()
    if group not in (None, ALL_GROUPS):
        recs = recs.loc[recs["group"] == group]
    recs = recs.loc[recs["label"] != NOT_COMPARABLE]
    if not show_hidden:
        recs = recs.loc[~recs["label"].isin(HIDDEN_LABELS)]
    windows = {}
    if recent_trend is not None and not recent_trend.empty:
        for _, row in recent_trend.iterrows():
            windows[row["campaign"]] = _period(
                row["recent_window_start"], row["recent_window_end"])
    rows = []
    for _, row in recs.iterrows():
        rows.append({
            "campaign": row["campaign"],
            "group": row["group"],
            "label": row["label"],
            "status_now": row["status_now"],
            "recent_trend": row.get("recent_trend", ""),
            "action": row["action_text"],
            "label_from": row.get("label_basis", ""),
            "label_period": _period(row.get("label_period_start"),
                                    row.get("label_period_end")),
            "trend_period": windows.get(row["campaign"], ""),
        })
    columns = ["campaign", "group", "label", "status_now",
               "recent_trend", "action", "label_from",
               "label_period", "trend_period"]
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["status_now", "campaign"]).reset_index(drop=True)


def not_comparable_rows(recommendations):
    """Campaigns labelled not_comparable, with reason and action."""
    part = recommendations.loc[
        recommendations["label"] == NOT_COMPARABLE]
    return part[["campaign", "group", "status_now", "reason",
                 "action_text"]].sort_values(
        "campaign").reset_index(drop=True)


def kpi_values(benchmarks):
    """KPI tile values, read from benchmarks.csv.

    spend, tracked actions and cost per tracked action of the
    judged campaigns, and the benchmark (pooled, its groups, and
    the leave-one-out range when it is used).
    """
    table = benchmarks.set_index("variant")
    judged = table.loc["judged_campaigns"]
    bench = table.loc["benchmark"]
    loo = bench.get("leave_one_out")
    loo = bool(loo) if loo is not None and not pd.isna(loo) else False
    return {
        "judged_campaigns": int(judged["campaigns"]),
        "spend": float(judged["spend"]),
        "tracked_actions": float(judged["tracked_actions"]),
        "cost_per_tracked_action": float(
            judged["cost_per_tracked_action"]),
        "benchmark": float(bench["cost_per_tracked_action"]),
        "benchmark_groups": bench["groups"],
        "leave_one_out": loo,
        "loo_min": (float(bench["loo_min"]) if loo else None),
        "loo_max": (float(bench["loo_max"]) if loo else None),
    }


def campaign_detail(recommendations, recent_trend, campaign):
    """One campaign's final label, reasons and periods (a dict)."""
    row = recommendations.set_index("campaign").loc[campaign]
    trend_window = prior_window = ""
    if recent_trend is not None and not recent_trend.empty and \
            campaign in set(recent_trend["campaign"]):
        trend = recent_trend.set_index("campaign").loc[campaign]
        trend_window = _period(trend["recent_window_start"],
                               trend["recent_window_end"])
        prior_window = _period(trend["prior_window_start"],
                               trend["prior_window_end"])
    def text(key):
        value = row.get(key, "")
        return "" if value is None or pd.isna(value) else str(value)
    return {
        "campaign": campaign,
        "group": text("group"),
        "label": text("label"),
        "status_now": text("status_now"),
        "label_from": text("label_basis"),
        "label_period": _period(row.get("label_period_start"),
                                row.get("label_period_end")),
        "reason": text("reason"),
        "action": text("action_text"),
        "recent_trend": text("recent_trend"),
        "trend_window": trend_window,
        "prior_window": prior_window,
        "trend_reason": text("trend_reason"),
    }


def run_recommendations_for_campaign(run_recs, campaign):
    """One campaign's runs with their run labels, in run order."""
    part = run_recs.loc[run_recs["campaign"] == campaign]
    columns = [column for column in (
        "run_number", "start", "end", "active_days", "spend",
        "conversions", "cost_per_conversion", "ratio_to_benchmark",
        "benchmark_basis", "label") if column in part.columns]
    return part[columns].sort_values("run_number").reset_index(
        drop=True).rename(columns={"label": "run_label"})


def filter_period(table, column, start=None, end=None):
    """Rows whose period column is within start..end (inclusive).

    Works for months ("2026-01") and dates ("2026-01-12"):
    values are compared as text, which orders ISO dates
    correctly. start or end None means no limit.
    """
    values = table[column].astype(str)
    keep = pd.Series(True, index=table.index)
    if start is not None:
        keep &= values >= str(start)
    if end is not None:
        keep &= values <= str(end)
    return table.loc[keep].reset_index(drop=True)


def journey_row(journey, campaign):
    """One campaign's journey row (empty table if it has none)."""
    return journey.loc[journey["campaign"] == campaign].reset_index(
        drop=True)


def weekday_focus_table(mix, weekday):
    """Per campaign on one weekday: click shares, actions per click.

    From weekday_mix_by_campaign.csv; sorted by the campaign's
    share of that weekday's pooled clicks, largest first.
    """
    part = mix.loc[mix["weekday"] == weekday]
    columns = ["campaign", "clicks", "share_of_weekday_clicks",
               "share_of_campaign_clicks", "share_vs_even",
               "actions_per_click", "baseline_actions_per_click",
               "actions_per_click_vs_baseline"]
    return part[columns].sort_values(
        "share_of_weekday_clicks", ascending=False).reset_index(
        drop=True)


def leave_one_out_for_weekday(loo, weekday):
    """The pooled weekday with each campaign left out, one weekday.

    The full pool ("(none)") first, then the left-out campaigns,
    closest to the baseline weekdays first, so the campaign that
    explains the weekday is on top.
    """
    part = loo.loc[loo["weekday"] == weekday].copy()
    part["distance_from_baseline"] = (
        part["actions_per_click_vs_baseline"] - 1).abs()
    part["_full"] = part["left_out"] != "(none)"
    part = part.sort_values(["_full", "distance_from_baseline"])
    return part.drop(columns=["_full"]).reset_index(drop=True)


def what_if_parts(what_if):
    """(variant rows, range row or None) of the what-if table."""
    if "variant" not in what_if.columns:
        return what_if.reset_index(drop=True), None
    variants = what_if.loc[what_if["variant"] != "range"]
    span = what_if.loc[what_if["variant"] == "range"]
    return (variants.reset_index(drop=True),
            span.iloc[0].to_dict() if not span.empty else None)


def lag_check_summary(lag_check):
    """Per lag: trend and label changes against the configured lag."""
    totals = lag_check.loc[lag_check["measure"].isin(
        ["recent_trend_changes_total", "label_changes_total"])]
    table = totals.pivot_table(index="lag", columns="measure",
                               values="campaigns", aggfunc="sum")
    table = table.rename(columns={
        "recent_trend_changes_total": "trend_changes",
        "label_changes_total": "label_changes"}).reset_index()
    table.columns.name = None
    return table


def rules_table(config):
    """Volume rule and thresholds as read from the config."""
    analysis = config.get("analysis") or {}
    rows = []
    sections = (
        ("volume_rule", analysis.get("volume_rule") or {}),
        ("recommendation_rules",
         analysis.get("recommendation_rules") or {}),
        ("recent_trend", analysis.get("recent_trend") or {}),
    )
    for section, values in sections:
        for key, value in values.items():
            if isinstance(value, dict):
                for inner, inner_value in value.items():
                    rows.append({"setting": f"{section}.{key}.{inner}",
                                 "value": str(inner_value)})
            else:
                rows.append({"setting": f"{section}.{key}",
                             "value": str(value)})
    for key in ("weekday_min_conversions", "run_gap_days"):
        if key in analysis:
            rows.append({"setting": key, "value": str(analysis[key])})
    return pd.DataFrame(rows, columns=["setting", "value"])


def csv_bytes(table):
    """A table as CSV bytes, for a download button."""
    return table.to_csv(index=False).encode("utf-8")
