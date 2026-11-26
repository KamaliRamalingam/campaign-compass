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

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.groups import display_names, replace_group_keys  # noqa: E402

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
        journey["campaign"] != JOURNEY_POOL_ROW].copy()


# --- Group display names (display only) ---------------------------
# The result tables hold group keys (core, core_pmax, ...) and
# src/ texts that name them. These helpers swap in each group's
# config display_name when a value is shown; the tables, the
# filters and the downloads keep the keys.

# The journey's pooled row, as src/journey.py writes it.
JOURNEY_POOL_ROW = "core group"
# Columns holding one group key, or several joined with "+".
GROUP_COLUMNS = ("group", "groups")
# Columns holding src/ explanation text that may name a group.
GROUP_TEXT_COLUMNS = ("reason", "base_reason", "trend_reason")


def group_names(config):
    """{group key: readable name} from the config's campaign_groups."""
    analysis = (config or {}).get("analysis") or {}
    return display_names(analysis.get("campaign_groups") or {})


def group_text(value, names):
    """One group key, or "+"-joined keys, as readable names.

    "core+core_pmax" becomes "Core campaigns + Performance Max". A
    missing value is returned as is.
    """
    if isinstance(value, (list, tuple)):
        parts = [str(part) for part in value]
    elif isinstance(value, str):
        parts = [part for part in value.split("+") if part]
    else:
        return value
    return " + ".join(names.get(part, part) for part in parts)


def journey_pool_label(config, names):
    """Readable name of the journey's pooled row.

    src/journey.py pools the campaigns of analysis.time_groups
    (default core) into one row, so it is named after those groups.
    """
    analysis = (config or {}).get("analysis") or {}
    return group_text(list(analysis.get("time_groups") or ["core"]),
                      names)


def with_group_names(table, names, pool_label=None):
    """A copy of a table with group keys shown as readable names.

    group / groups columns become readable names; reason columns
    get each whole-word key replaced; the journey's pooled row is
    renamed to pool_label when given. The input table is unchanged.
    """
    if table is None:
        return table
    result = table.copy()
    for column in GROUP_COLUMNS:
        if column in result.columns:
            result[column] = [group_text(value, names)
                              for value in result[column]]
    for column in GROUP_TEXT_COLUMNS:
        if column in result.columns:
            result[column] = [replace_group_keys(value, names)
                              for value in result[column]]
    if pool_label and "campaign" in result.columns:
        result["campaign"] = result["campaign"].replace(
            {JOURNEY_POOL_ROW: pool_label})
    return result


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
        "judged_groups": str(judged["groups"]),
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


def too_little_data_count(recommendations, groups):
    """How many campaigns in the given groups are insufficient_data.

    groups is the "+"-joined text from benchmarks.csv (for example
    "core+sep_2026_group"). Uses all recommendations, never a
    filtered view, so it matches the KPI cards.
    """
    if isinstance(groups, str):
        names = [name for name in groups.split("+") if name]
    else:
        names = list(groups)
    part = recommendations.loc[recommendations["group"].isin(names)]
    return int((part["label"] == "insufficient_data").sum())


def totals_scope_text(campaigns, judged_groups, too_little,
                      benchmark_groups):
    """The "Totals and benchmark" sentence: both scopes.

    "has" when one campaign has too little data, "have" otherwise.
    """
    verb = "has" if too_little == 1 else "have"
    return (f"Totals cover {campaigns} campaigns in the groups "
            f"{', '.join(judged_groups)} ({too_little} of them {verb} "
            f"too little data for a label). The benchmark is built from "
            f"group(s) {', '.join(benchmark_groups)} only.")


def scope_groups(config, benchmarks=None):
    """(judged groups, benchmark groups), as lists, from the config.

    Judged groups: analysis.recommendation_rules.judged_groups; if
    unset, the groups of the judged_campaigns row of benchmarks.csv.
    Benchmark groups: recommendation_rules.benchmark.groups, default
    ["core"] as in src/recommend.py.
    """
    rules = ((config or {}).get("analysis") or {}).get(
        "recommendation_rules") or {}
    judged = rules.get("judged_groups")
    if not judged and benchmarks is not None:
        row = benchmarks.loc[benchmarks["variant"] == "judged_campaigns"]
        if not row.empty:
            judged = [name for name in str(row["groups"].iloc[0])
                      .split("+") if name]
    bench = (rules.get("benchmark") or {}).get("groups") or ["core"]
    return [str(name) for name in judged or []], [str(n) for n in bench]


def first_clause(text):
    """Text up to the first semicolon or sentence end, never reworded.

    "keep running, but test changes; cost ... risen" -> "keep running,
    but test changes". Missing text gives "".
    """
    if text is None or (not isinstance(text, str) and pd.isna(text)):
        return ""
    text = str(text).strip()
    cuts = [index for index in (text.find(";"), text.find(". "))
            if index >= 0]
    if cuts:
        text = text[:min(cuts)]
    return text.rstrip(" .")


TILE_LABELS = ("pause_or_review", "test", "continue")


def capitalise_first(text):
    """Text with only its first letter made upper case."""
    text = "" if text is None else str(text)
    return text[:1].upper() + text[1:]


def tile_title(text, count):
    """An Act tile's title with its count in brackets: "Test (3)"."""
    return f"{text} ({int(count)})"


def tile_detail(line, with_label=False):
    """Second line of a campaign in an Act tile.

    "Ended · Do not restart without changes", "Running · Keep
    running, but test changes", or in the Running now tile the label
    first: "Test · Keep running, but test changes". Only the first
    letter of each part is capitalised; the text is the same as in
    act_summary.
    """
    if with_label:
        first = label_text(line["label"]) or "—"
    elif line["running"]:
        first = "running"
    else:
        first = line["status"]
    parts = [capitalise_first(part) for part in (first, line["action"])
             if part]
    return " · ".join(parts)


def act_summary(recommendations, max_lines=3):
    """Per-tile data for the Act page's four decision tiles.

    Uses all recommendations (never a filtered view), so the counts
    match the labels in the data. Returns a dict:
    tiles: one dict per judged label (pause_or_review, test,
    continue) with label, count, lines (at most max_lines, in the
    order of the ranked action table) and more (how many are not
    listed). running: every campaign whose status_now is active (in
    ranked order, not_comparable last), with its label.
    Each line: campaign, label, status, running (True when active)
    and action (the action text up to its first semicolon or
    sentence end). A campaign with an empty label is in no tile.
    """
    ranked = action_table(recommendations)[
        ["campaign", "label", "status_now", "action"]]
    others = recommendations.loc[
        recommendations["label"] == NOT_COMPARABLE,
        ["campaign", "label", "status_now", "action_text"]].rename(
        columns={"action_text": "action"})
    ranked = pd.concat([ranked, others], ignore_index=True)

    def line(row):
        label = row["label"]
        status = row["status_now"]
        status = "" if status is None or pd.isna(status) else str(status)
        return {"campaign": str(row["campaign"]),
                "label": None if label is None or pd.isna(label)
                else label,
                "status": status.replace("_", " "),
                "running": status == "active",
                "action": first_clause(row["action"])}

    tiles = []
    for label in TILE_LABELS:
        part = ranked.loc[ranked["label"] == label]
        tiles.append({
            "label": label,
            "count": int(len(part)),
            "lines": [line(row) for _, row in
                      part.head(max_lines).iterrows()],
            "more": max(0, int(len(part)) - max_lines),
        })
    status = ranked["status_now"].astype(str)
    running = [line(row) for _, row in
               ranked.loc[status == "active"].iterrows()]
    return {"tiles": tiles, "running": running}


def ratio_bar_rows(table, recommendations, cap=2.5):
    """Bars for the Act page's ratio chart, in the table's order.

    table: action_table (already filtered). One row per judged
    campaign with a ratio to the benchmark. shown is the ratio cut
    at cap (the axis edge), over is True when the ratio is above
    it (the real value is written on the bar). worsening is True
    when the label comes from the trend override (trend_override
    is set in recommendations_by_campaign.csv).
    """
    columns = ["campaign", "label", "label_text", "colour", "ratio",
               "shown", "over", "worsening", "label_period",
               "cost_per_tracked_action", "benchmark"]
    part = table.loc[table["label"].isin(JUDGED_LABELS)].copy()
    part["ratio"] = pd.to_numeric(part["ratio_to_benchmark"],
                                  errors="coerce")
    part = part.dropna(subset=["ratio"])
    if part.empty:
        return pd.DataFrame(columns=columns)
    override = {}
    if "trend_override" in recommendations.columns:
        for name, value in zip(recommendations["campaign"],
                               recommendations["trend_override"]):
            override[name] = (value is not None and not pd.isna(value)
                              and str(value).strip() != "")
    part["label_text"] = part["label"].map(label_text)
    part["colour"] = part["label"].map(label_colour)
    part["shown"] = part["ratio"].clip(upper=cap)
    part["over"] = part["ratio"] > cap
    part["worsening"] = [override.get(name, False)
                         for name in part["campaign"]]
    return part[columns].reset_index(drop=True)


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


def rules_table(config, names=None):
    """Volume rule and thresholds as read from the config.

    With names ({group key: readable name}), a list of groups (a
    setting ending in "groups") is shown by its readable names.
    """
    analysis = config.get("analysis") or {}
    rows = []
    sections = (
        ("volume_rule", analysis.get("volume_rule") or {}),
        ("recommendation_rules",
         analysis.get("recommendation_rules") or {}),
        ("recent_trend", analysis.get("recent_trend") or {}),
    )

    def shown(setting, value):
        if names and setting.endswith("groups") \
                and isinstance(value, list):
            return ", ".join(names.get(str(g), str(g)) for g in value)
        return str(value)

    for section, values in sections:
        for key, value in values.items():
            if isinstance(value, dict):
                for inner, inner_value in value.items():
                    setting = f"{section}.{key}.{inner}"
                    rows.append({"setting": setting,
                                 "value": shown(setting, inner_value)})
            else:
                setting = f"{section}.{key}"
                rows.append({"setting": setting,
                             "value": shown(setting, value)})
    for key in ("weekday_min_conversions", "run_gap_days"):
        if key in analysis:
            rows.append({"setting": key, "value": str(analysis[key])})
    return pd.DataFrame(rows, columns=["setting", "value"])


MISSING = "—"
# Display-only rounding by column name (the CSV keeps raw values).
# Checked in order; the first rule whose words are in the name wins.
ROUNDING_RULES = (
    (("cost", "benchmark", "loo_min", "loo_max", "cpa"), 2),
    (("per click", "per_click"), 3),
    (("share", "ratio", "vs", "(%)", "rate", "pct"), 2),
    (("spend",), 0),
    (("action", "conversion", "click", "impression", "before", "after",
      "delta", "days", "campaigns", "changes", "lag", "count"), 0),
)


def _is_missing(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def format_number(value, pattern):
    """A number in a printf pattern from column_config ("%.2fx",
    "%d", "%.0f"), with thousands separators; MISSING if missing."""
    if _is_missing(value):
        return MISSING
    import re
    match = re.fullmatch(r"(.*)%(?:\.(\d+))?([df])(.*)", pattern)
    if not match:
        return pattern % value
    prefix, digits, kind, suffix = match.groups()
    if kind == "d":
        return f"{prefix}{int(round(float(value))):,}{suffix}"
    places = int(digits) if digits is not None else 6
    return f"{prefix}{float(value):,.{places}f}{suffix}"


def display_value(column, value, pattern=None):
    """Display text of one table value (never changes the data).

    MISSING for a missing value. A pattern (from column_config) wins;
    otherwise numbers are rounded by column name: actions, clicks
    and spend 0 dp, cost 2 dp, shares and ratios 2 dp, per-click
    rates 3 dp, other decimals 2 dp. Text is returned as is.
    """
    if _is_missing(value):
        return MISSING
    if isinstance(value, bool) or (hasattr(value, "dtype")
                                   and str(value.dtype) == "bool"):
        return str(value)
    if pattern:
        try:
            return format_number(value, pattern)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, str) or not pd.api.types.is_number(value):
        return str(value)
    name = str(column).lower()
    places = None
    for words, digits in ROUNDING_RULES:
        if any(word in name for word in words):
            places = digits
            break
    if places is None:
        if float(value).is_integer():
            return f"{int(value):,}" if abs(value) >= 10000 else str(
                int(value))
        places = 2
    return f"{float(value):,.{places}f}"


def csv_bytes(table):
    """A table as CSV bytes, for a download button."""
    return table.to_csv(index=False).encode("utf-8")


# --- PR 5: three-page report -------------------------------------

# Display text, symbol and colours per label (redesign palette).
# colour: the strong colour for bars, borders and markers. tint:
# the soft fill for tiles and pills, always with dark text (dark
# text on the strong green or grey is below 4.5:1). Every label
# also has its own text and symbol, so the meaning never depends
# on colour alone.
LABEL_STYLE = {
    "continue": {"text": "Continue", "symbol": "✓",
                 "colour": "#2E9E5B", "tint": "#DDF0E2",
                 "marker": "circle"},
    "test": {"text": "Test", "symbol": "◆",
             "colour": "#D9961A", "tint": "#FFF0CC",
             "marker": "diamond"},
    "pause_or_review": {"text": "Pause or review", "symbol": "✕",
                        "colour": "#C8452D", "tint": "#FBE3DD",
                        "marker": "x"},
    "not_comparable": {"text": "Not comparable", "symbol": "○",
                       "colour": "#8C8C8C", "tint": "#EFEAE3",
                       "marker": "circle-open"},
    "insufficient_data": {"text": "Insufficient data", "symbol": "–",
                          "colour": "#8C8C8C", "tint": "#EFEAE3",
                          "marker": "circle-open"},
    "not_judged": {"text": "Not judged", "symbol": "–",
                   "colour": "#8C8C8C", "tint": "#EFEAE3",
                   "marker": "circle-open"},
}
GREY_TINT = "#EFEAE3"
JUDGED_LABELS = ("continue", "test", "pause_or_review")
# Most urgent first in the ranked action table.
LABEL_RANK = {"pause_or_review": 0, "test": 1, "continue": 2,
              "not_comparable": 3, "insufficient_data": 4,
              "not_judged": 5}
ALL_STATUSES = "All"
DEFAULT_FOOTNOTE = "Labels are prompts for review, not proof of cause."
INTENT_COLUMNS = {"directions_share": "Directions",
                  "calls_share": "Calls",
                  "store_visits_share": "Store visits"}


def label_text(label):
    """"✓ Continue" style display text; unknown labels unchanged."""
    style = LABEL_STYLE.get(label)
    if style is None:
        return "" if label is None or pd.isna(label) else str(label)
    return f"{style['symbol']} {style['text']}"


def label_colour(label):
    """Colour of a label (grey for unknown labels)."""
    return LABEL_STYLE.get(label, {}).get("colour", "#8C8C8C")


def label_tint(label):
    """Soft fill of a label (light grey for unknown labels)."""
    return LABEL_STYLE.get(label, {}).get("tint", GREY_TINT)


def _day(value):
    """"1 Jul 2024" (no leading zero on the day)."""
    return f"{value.day} {value:%b %Y}"


def data_line(date_range, updated):
    """"Data 1 Jul 2024 – 12 Nov 2026 · Updated 24 Nov 2026 10:48"."""
    first, last = date_range
    return (f"Data {_day(first)} – {_day(last)} · Updated "
            f"{_day(updated)} {updated:%H:%M}")


def logo_path(config, repo_root=None):
    """The header logo from branding.logo_path, or None.

    None when the key is missing or the file does not exist, so
    the header falls back to the text wordmark without an error.
    A relative path is read from the repo root.
    """
    branding = (config or {}).get("branding") or {}
    configured = branding.get("logo_path")
    if not configured:
        return None
    path = Path(configured)
    if not path.is_absolute():
        path = (Path(repo_root) if repo_root else REPO_ROOT) / path
    return path if path.is_file() else None


def footnote_text(config):
    """analysis.footnote_text from the config, or the default."""
    analysis = config.get("analysis") or {}
    return analysis.get("footnote_text") or DEFAULT_FOOTNOTE


def judged_label_counts(recommendations):
    """(counts of the judged labels, counts of the other labels).

    The first table has one row per judged label (continue,
    test, pause_or_review, in that order, zero rows kept) with its
    display text and colour. The second is a dict label -> count
    for every other label, for a "not shown" caption.
    """
    counts = recommendations["label"].value_counts()
    judged = pd.DataFrame({
        "label": list(JUDGED_LABELS),
        "label_text": [label_text(label) for label in JUDGED_LABELS],
        "colour": [label_colour(label) for label in JUDGED_LABELS],
        "campaigns": [int(counts.get(label, 0))
                      for label in JUDGED_LABELS],
    })
    others = {label: int(count) for label, count in counts.items()
              if label not in JUDGED_LABELS}
    return judged, others


def status_options(recommendations):
    """Choices for the status filter: ALL_STATUSES, then each status."""
    return [ALL_STATUSES] + sorted(
        recommendations["status_now"].dropna().unique())


def filter_view(recommendations, group=None, status=None,
                min_tracked_actions=0):
    """Rows to show; a display filter only.

    Hides rows by group, status now and the tracked actions in
    the label period. It never changes a label or a KPI. A row
    without label-period figures is kept only when the minimum is
    0 (so insufficient_data rows are not hidden by accident).
    """
    recs = recommendations
    if group not in (None, ALL_GROUPS):
        recs = recs.loc[recs["group"] == group]
    if status not in (None, ALL_STATUSES):
        recs = recs.loc[recs["status_now"] == status]
    if min_tracked_actions and min_tracked_actions > 0:
        if "label_tracked_actions" in recs.columns:
            actions = recs["label_tracked_actions"]
            recs = recs.loc[actions.notna()
                            & (actions >= min_tracked_actions)]
        else:
            recs = recs.iloc[0:0]
    return recs.reset_index(drop=True)


def bubble_rows(recommendations):
    """Judged campaigns with label-period figures, for the bubble chart."""
    columns = ["label_spend", "label_tracked_actions",
               "label_cost_per_tracked_action", "label_benchmark"]
    if not set(columns) <= set(recommendations.columns):
        return pd.DataFrame(columns=["campaign", "label"] + columns)
    part = recommendations.loc[
        recommendations["label"].isin(JUDGED_LABELS)].dropna(
        subset=columns).copy()
    part["label_text"] = part["label"].map(label_text)
    part["colour"] = part["label"].map(label_colour)
    part["label_period"] = [
        _period(start, end) for start, end in zip(
            part["label_period_start"], part["label_period_end"])]
    keep = ["campaign", "group", "label", "label_text", "colour",
            "status_now", "label_basis", "label_period",
            "label_ratio"] + columns
    keep = [column for column in keep if column in part.columns]
    return part[keep].sort_values("campaign").reset_index(drop=True)


def reference_lines(config, benchmark):
    """[(name, ratio, cost)] for the benchmark and the two thresholds.

    Ratios from analysis.recommendation_rules (continue_max_ratio,
    test_max_ratio); cost = benchmark x ratio, a line to draw, not
    a recomputed result.
    """
    rules = (config.get("analysis") or {}).get(
        "recommendation_rules") or {}
    lines = [("Benchmark", 1.0, float(benchmark))]
    for key, name in (("continue_max_ratio", "Continue up to"),
                      ("test_max_ratio", "Test up to")):
        ratio = rules.get(key)
        if ratio is None:
            continue
        lines.append((f"{name} {float(ratio):.1f}x", float(ratio),
                      float(benchmark) * float(ratio)))
    return lines


def action_table(recommendations, recent_trend=None):
    """Ranked action table: most urgent first.

    pause_or_review, then test, then continue (then any other
    label), and within a label the highest ratio to the
    benchmark first. not_comparable rows are left out (they have
    their own box).
    """
    recs = recommendations.loc[
        recommendations["label"] != NOT_COMPARABLE].copy()
    windows = {}
    if recent_trend is not None and not recent_trend.empty:
        for _, row in recent_trend.iterrows():
            windows[row["campaign"]] = _period(
                row["recent_window_start"], row["recent_window_end"])
    recs["_rank"] = recs["label"].map(LABEL_RANK).fillna(9)
    ratio = recs["label_ratio"] if "label_ratio" in recs.columns \
        else pd.Series(float("nan"), index=recs.index)
    recs["_ratio"] = pd.to_numeric(ratio, errors="coerce").fillna(-1)
    recs = recs.sort_values(["_rank", "_ratio", "campaign"],
                            ascending=[True, False, True])

    def column(name):
        if name in recs.columns:
            return recs[name].tolist()
        return [None] * len(recs)

    table = pd.DataFrame({
        "campaign": column("campaign"),
        "group": column("group"),
        "label": column("label"),
        "final_label": [label_text(label) for label in recs["label"]],
        "status_now": column("status_now"),
        "ratio_to_benchmark": column("label_ratio"),
        "cost_per_tracked_action": column(
            "label_cost_per_tracked_action"),
        "benchmark": column("label_benchmark"),
        "tracked_actions": column("label_tracked_actions"),
        "spend": column("label_spend"),
        "recent_trend": column("recent_trend"),
        "action": column("action_text"),
        "label_from": column("label_basis"),
        "label_period": [_period(start, end) for start, end in zip(
            column("label_period_start"), column("label_period_end"))],
        "trend_window": [windows.get(name, "")
                         for name in column("campaign")],
    })
    table.insert(0, "rank", range(1, len(table) + 1))
    return table.reset_index(drop=True)


def trend_with_flags(timeline_df, campaign):
    """One campaign's monthly trend with partial / lagged flags.

    Adds month_note: "partial", "lagged", "partial, lagged" or "".
    Missing flag columns give an empty note.
    """
    table = trend_for_campaign(timeline_df, campaign)
    part = timeline_df.loc[timeline_df["campaign"] == campaign]
    flags = [column for column in ("is_partial", "is_lagged")
             if column in part.columns]
    if flags:
        table = table.merge(part[["month", "source"] + flags],
                            on=["month", "source"], how="left")
    notes = []
    for _, row in table.iterrows():
        note = [name for name, column in (("partial", "is_partial"),
                                          ("lagged", "is_lagged"))
                if column in table.columns
                and str(row[column]).strip().lower() == "true"]
        notes.append(", ".join(note))
    table["month_note"] = notes
    return table.drop(columns=flags)


def _plural(count, word):
    return f"{count} {word}" + ("" if count == 1 else "s")


def trend_takeaway(rows):
    """One sentence: how many active campaigns have each trend.

    rows: recent_trend_rows. Trends are named as in the data
    (underscores to spaces), most frequent first.
    """
    if rows is None or rows.empty:
        return "No active campaign has a recent trend."
    counts = rows["recent_trend"].fillna("unknown").astype(str) \
        .value_counts()
    parts = ", ".join(f"{count} {trend.replace('_', ' ')}"
                      for trend, count in counts.items())
    return (f"{_plural(len(rows), 'active campaign')} with a recent "
            f"trend: {parts}.")


def weekday_takeaway(pooled, currency, change=None, scenario=None):
    """One sentence: cheapest and dearest weekday, then the what-if.

    pooled: weekday_core_table. change and scenario: the what-if
    range text and scenario (what_if_parts), or None.
    """
    costs = pooled.dropna(subset=["cost_per_tracked_action"])
    if costs.empty:
        text = "No weekday has a cost per tracked action."
    else:
        low = costs.loc[costs["cost_per_tracked_action"].idxmin()]
        high = costs.loc[costs["cost_per_tracked_action"].idxmax()]
        text = (f"Cost per tracked action is lowest on {low['weekday']} "
                f"({low['cost_per_tracked_action']:,.2f} {currency}) and "
                f"highest on {high['weekday']} "
                f"({high['cost_per_tracked_action']:,.2f} {currency}).")
    if change:
        what = f"{scenario}: " if scenario else "Moving spend: "
        text += f" {what}{change}, a linear estimate."
    return text


def lag_takeaway(summary, configured):
    """One sentence: does another conversion lag change anything?"""
    changes = summary.drop(columns=["lag"]).fillna(0).to_numpy().sum()
    return (f"Configured lag: {configured} days. "
            + ("No trend or label changes with any other lag."
               if changes == 0 else
               "Some trends or labels change with another lag: treat "
               "the most recent weeks with care."))


def journey_takeaway(journey):
    """One sentence: pooled share of directions and calls.

    Campaign rows only: the "core group" aggregate row is left out,
    as in the chart, so it is neither counted as a campaign nor
    weighted twice. Shares are weighted by each campaign's tracked
    actions.
    """
    journey = journey_campaigns(journey)
    total = float(journey["tracked_actions"].sum()) \
        if "tracked_actions" in journey.columns else 0.0
    if not total:
        return "No tracked actions to split by type."

    def share(column):
        if column not in journey.columns:
            return 0.0
        return float((journey[column].fillna(0)
                      * journey["tracked_actions"]).sum()) / total

    return (f"Across {_plural(len(journey), 'campaign')}, "
            f"{share('directions_share'):.0%} of tracked actions are "
            f"directions requests and {share('calls_share'):.0%} are "
            f"calls.")


def recent_trend_rows(recent_trend, recommendations):
    """Active campaigns' recent trend: recent vs prior cost and windows."""
    if recent_trend is None or recent_trend.empty:
        return pd.DataFrame(columns=[
            "campaign", "final_label", "recent_trend", "recent_window",
            "recent_cost_per_tracked_action", "prior_window",
            "prior_cost_per_tracked_action", "recent_vs_prior_ratio",
            "recent_tracked_actions"])
    labels = recommendations.set_index("campaign")["label"]
    table = pd.DataFrame({
        "campaign": recent_trend["campaign"],
        "final_label": [label_text(labels.get(name))
                        for name in recent_trend["campaign"]],
        "recent_trend": recent_trend["recent_trend"],
        "recent_window": [_period(a, b) for a, b in zip(
            recent_trend["recent_window_start"],
            recent_trend["recent_window_end"])],
        "recent_cost_per_tracked_action":
            recent_trend["recent_cost_per_tracked_action"],
        "prior_window": [_period(a, b) for a, b in zip(
            recent_trend["prior_window_start"],
            recent_trend["prior_window_end"])],
        "prior_cost_per_tracked_action":
            recent_trend["prior_cost_per_tracked_action"],
        "recent_vs_prior_ratio": recent_trend["recent_vs_prior_ratio"],
        "recent_tracked_actions":
            recent_trend["recent_tracked_actions"],
    })
    return table.sort_values("campaign").reset_index(drop=True)


def with_period_gaps(table, x_field, freq):
    """The table with a real date column and empty rows for gaps.

    x_field holds months ("2026-01") when freq is "MS", or week
    starts ("2026-01-05") when freq is "W-MON". Adds period_date (a
    date) and inserts a row with no values for each missing month
    or week between the first and the last, so a line chart breaks
    there instead of joining across the gap. Display only: nothing
    is filled in or recomputed.
    """
    if table is None or table.empty:
        result = table.copy() if table is not None else pd.DataFrame()
        result["period_date"] = pd.Series(dtype="datetime64[ns]")
        return result
    result = table.copy()
    result["period_date"] = pd.to_datetime(result[x_field].astype(str))
    full = pd.date_range(result["period_date"].min(),
                         result["period_date"].max(), freq=freq)
    missing = full.difference(pd.DatetimeIndex(result["period_date"]))
    if len(missing):
        gaps = pd.DataFrame({"period_date": missing})
        gaps[x_field] = [
            value.strftime("%Y-%m" if freq == "MS" else "%Y-%m-%d")
            for value in missing]
        if "month_note" in result.columns:
            gaps["month_note"] = ""
        result = pd.concat([result, gaps], ignore_index=True)
    return result.sort_values("period_date").reset_index(drop=True)


def recent_rows_capped(rows, limit=5):
    """(first `limit` rows, how many more) of recent_trend_rows."""
    if rows is None or rows.empty:
        return rows, 0
    return rows.head(limit).reset_index(drop=True), max(
        0, len(rows) - limit)


def most_clicks_weekday(pooled):
    """The weekday with the most pooled clicks, or None.

    pooled: weekday_core_table. Picks a row, computes nothing.
    """
    if pooled is None or pooled.empty or "clicks" not in pooled.columns:
        return None
    clicks = pd.to_numeric(pooled["clicks"], errors="coerce")
    if clicks.notna().sum() == 0:
        return None
    return pooled.loc[clicks.idxmax(), "weekday"]


def journey_intent_long(journey):
    """(campaign, intent, share) rows for a stacked intent bar."""
    campaigns = journey_campaigns(journey)
    present = [column for column in INTENT_COLUMNS
               if column in campaigns.columns]
    long = campaigns.melt(id_vars=["campaign"], value_vars=present,
                          var_name="intent", value_name="share")
    long["intent"] = long["intent"].map(INTENT_COLUMNS)
    return long.reset_index(drop=True)
