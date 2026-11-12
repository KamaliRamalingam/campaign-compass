"""Data preparation for the local Streamlit dashboard (T8).

All data preparation lives here, in pure functions that are
readable and testable. dashboard/app.py only displays.

Reads only outputs/results/ and outputs/reports/ — never
data/raw/. Table paths come from the config where they exist
(analysis.outputs); otherwise the one DEFAULT_PATHS constant
below is used. No campaign names, thresholds or other values
are hard-coded here.

If a result table is missing, load_tables raises
FileNotFoundError with "Run bash run.sh first".
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
}

REQUIRED_TABLES = list(DEFAULT_PATHS)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]


def load_config(config_path=None):
    """Load the restaurant config as a dict."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def caveat_text(config):
    """The caveat text, from analysis.caveat_text in the config."""
    return config["analysis"]["caveat_text"]


def table_paths(config, root=None):
    """Resolve every required table path, from config or default."""
    base = Path(root) if root else REPO_ROOT
    outputs = (config.get("analysis") or {}).get("outputs") or {}
    return {
        key: base / outputs.get(key, DEFAULT_PATHS[key])
        for key in REQUIRED_TABLES
    }


def load_tables(config=None, root=None):
    """Read all required result tables. Returns name -> DataFrame.

    Raises FileNotFoundError naming the missing file and telling
    the user to run bash run.sh first.
    """
    config = config if config is not None else load_config()
    paths = table_paths(config, root=root)
    tables = {}
    for key, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"Run bash run.sh first: {path} is missing")
        tables[key] = pd.read_csv(path)
    return tables


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
    grouped["share_pct"] = grouped["share"] * 100.0
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
    table["weekday_no"] = table["weekday"].apply(WEEKDAYS.index)
    table = table.sort_values("weekday_no").drop(
        columns=["weekday_no"])
    table["tracked_actions"] = table["conversions"]
    table["cost_per_tracked_action"] = table["cost_per_conversion"]
    return table.reset_index(drop=True)


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
