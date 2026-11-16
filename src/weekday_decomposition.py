"""Weekday decomposition: is a weekday pattern one campaign? (PR 3, M5)

Usage:
    python src/weekday_decomposition.py --config config/restaurant.yaml

The pooled weekday table (outputs/results/weekday_core.csv) sums
all campaigns in analysis.time_groups. A weekday can look
different only because one campaign gets more of its clicks on
that day. This stage splits the pooled weekday cells up, from
the cleaned daily table, and writes aggregates only:

- outputs/results/weekday_mix_by_campaign.csv: per campaign and
  weekday: active_days, clicks, conversions, spend,
  share_of_campaign_clicks (and share_vs_even = that share
  divided by 1/7), share_of_weekday_clicks (the campaign's part
  of the pooled clicks that weekday), actions_per_click,
  baseline_actions_per_click (the campaign's own actions per
  click on the baseline weekdays, default Mon-Thu) and
  actions_per_click_vs_baseline.
- outputs/results/weekday_leave_one_out.csv: the pooled weekday
  table with each campaign left out in turn (left_out "(none)"
  is the full pool): clicks, conversions, spend,
  actions_per_click, cost_per_action and
  actions_per_click_vs_baseline (against the same pool's
  baseline weekdays).
- outputs/results/weekday_top_days.csv: for the focus weekday
  (the weekday with the most pooled clicks, or
  weekday_decomposition.focus_weekday), the top_days dates by
  pooled clicks: clicks, share_of_weekday_clicks, conversions,
  actions_per_click.
- outputs/reports/weekday-decomposition-report.md: a summary
  with counts, shares and ratios, no campaign names.

Settings, analysis.weekday_decomposition (when the key is not
set the stage is skipped with a message):
- baseline_weekdays: default [Mon, Tue, Wed, Thu]
- top_days: default 5
- focus_weekday: default the weekday with the most clicks

No weekday, run or journey number changes. The console shows
counts only, never rows.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from src.paths import apply_output_root
    from src.clean import load_config
    from src.groups import assign_group
    from src.metrics import _safe_divide
except ImportError:  # running as `python src/weekday_decomposition.py`
    from clean import load_config
    from paths import apply_output_root
    from groups import assign_group
    from metrics import _safe_divide

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_BASELINE = ["Mon", "Tue", "Wed", "Thu"]
NONE_LEFT_OUT = "(none)"
DEFAULT_OUTPUTS = {
    "weekday_mix_by_campaign":
        "outputs/results/weekday_mix_by_campaign.csv",
    "weekday_leave_one_out":
        "outputs/results/weekday_leave_one_out.csv",
    "weekday_top_days": "outputs/results/weekday_top_days.csv",
    "weekday_decomposition_report":
        "outputs/reports/weekday-decomposition-report.md",
}


def prepare(day_df, groups, time_groups):
    """Daily rows of the time_groups campaigns, with weekday."""
    df = day_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["group"] = df["campaign"].apply(
        lambda name: assign_group(name, groups))
    df = df.loc[df["group"].isin(time_groups)].copy()
    df["weekday"] = df["date"].dt.day_of_week.map(
        dict(enumerate(WEEKDAYS)))
    return df


def _ratio(numerator, denominator):
    value = _safe_divide(numerator, denominator)
    return None if value is None else float(value)


def _order(table, by):
    table = table.copy()
    table["_weekday_no"] = table["weekday"].map(WEEKDAYS.index)
    table = table.sort_values(by + ["_weekday_no"])
    return table.drop(columns="_weekday_no").reset_index(drop=True)


def mix_by_campaign(df, baseline):
    """Per campaign and weekday: click shares and actions per click."""
    pooled_clicks = df.groupby("weekday")["clicks"].sum()
    rows = []
    for campaign, part in df.groupby("campaign"):
        total_clicks = float(part["clicks"].sum())
        base = part.loc[part["weekday"].isin(baseline)]
        base_apc = _ratio(float(base["conversions"].sum()),
                          float(base["clicks"].sum()))
        for weekday, cell in part.groupby("weekday"):
            clicks = float(cell["clicks"].sum())
            conversions = float(cell["conversions"].sum())
            share = _ratio(clicks, total_clicks)
            apc = _ratio(conversions, clicks)
            rows.append({
                "campaign": campaign,
                "weekday": weekday,
                "active_days": int(cell["date"].nunique()),
                "clicks": clicks,
                "conversions": conversions,
                "spend": float(cell["cost"].sum()),
                "share_of_campaign_clicks": share,
                "share_vs_even": (None if share is None
                                  else share * len(WEEKDAYS)),
                "share_of_weekday_clicks": _ratio(
                    clicks, float(pooled_clicks[weekday])),
                "actions_per_click": apc,
                "baseline_actions_per_click": base_apc,
                "actions_per_click_vs_baseline": (
                    None if apc is None else _ratio(apc, base_apc)),
            })
    return _order(pd.DataFrame(rows), ["campaign"])


def _pooled(part, baseline):
    """Pooled weekday rows for one set of campaigns."""
    base = part.loc[part["weekday"].isin(baseline)]
    base_apc = _ratio(float(base["conversions"].sum()),
                      float(base["clicks"].sum()))
    rows = []
    for weekday, cell in part.groupby("weekday"):
        clicks = float(cell["clicks"].sum())
        conversions = float(cell["conversions"].sum())
        apc = _ratio(conversions, clicks)
        rows.append({
            "weekday": weekday,
            "clicks": clicks,
            "conversions": conversions,
            "spend": float(cell["cost"].sum()),
            "actions_per_click": apc,
            "cost_per_action": _ratio(float(cell["cost"].sum()),
                                      conversions),
            "actions_per_click_vs_baseline": (
                None if apc is None else _ratio(apc, base_apc)),
        })
    return rows


def leave_one_out(df, baseline):
    """Pooled weekday table with each campaign left out in turn."""
    rows = [{"left_out": NONE_LEFT_OUT, **row}
            for row in _pooled(df, baseline)]
    for campaign in sorted(df["campaign"].unique()):
        rest = df.loc[df["campaign"] != campaign]
        rows += [{"left_out": campaign, **row}
                 for row in _pooled(rest, baseline)]
    table = pd.DataFrame(rows)
    table["_none_first"] = table["left_out"] != NONE_LEFT_OUT
    table = _order(table, ["_none_first", "left_out"])
    return table.drop(columns="_none_first")


def focus_weekday(df, settings):
    """The configured focus weekday, or the one with most clicks."""
    configured = (settings or {}).get("focus_weekday")
    if configured:
        if configured not in WEEKDAYS:
            raise ValueError(
                f"weekday_decomposition.focus_weekday: unknown "
                f"weekday {configured!r}")
        return configured
    clicks = df.groupby("weekday")["clicks"].sum()
    return str(clicks.idxmax())


def top_days(df, weekday, count):
    """Top dates by pooled clicks on one weekday."""
    part = df.loc[df["weekday"] == weekday]
    total = float(part["clicks"].sum())
    by_date = part.groupby(part["date"].dt.date).agg(
        clicks=("clicks", "sum"), conversions=("conversions", "sum"))
    # Most clicks first; ties by the earlier date, so the order
    # is stable.
    by_date = by_date.reset_index(names="day").sort_values(
        ["clicks", "day"], ascending=[False, True]).set_index(
        "day").head(count)
    rows = []
    for rank, (day, row) in enumerate(by_date.iterrows(), start=1):
        rows.append({
            "weekday": weekday, "rank": rank, "date": day,
            "clicks": float(row["clicks"]),
            "share_of_weekday_clicks": _ratio(
                float(row["clicks"]), total),
            "conversions": float(row["conversions"]),
            "actions_per_click": _ratio(
                float(row["conversions"]), float(row["clicks"])),
        })
    return pd.DataFrame(rows, columns=[
        "weekday", "rank", "date", "clicks",
        "share_of_weekday_clicks", "conversions",
        "actions_per_click"])


def _pct(value):
    return "-" if value is None or pd.isna(value) else \
        f"{100 * value:.1f}%"


def _num(value, digits=2):
    return "-" if value is None or pd.isna(value) else \
        f"{value:.{digits}f}"


def write_report(path, mix, loo, top, weekday, baseline,
                 days_on_weekday):
    """Write the report: shares and ratios only, no names."""
    pooled = loo.loc[loo["left_out"] == NONE_LEFT_OUT].set_index(
        "weekday")
    total_clicks = float(pooled["clicks"].sum())
    focus = pooled.loc[weekday]
    lines = ["# Weekday decomposition report", ""]
    lines.append(
        f"- Campaigns pooled: {mix['campaign'].nunique()}; "
        f"baseline weekdays: {', '.join(baseline)}")
    lines.append(
        f"- Focus weekday (most pooled clicks): {weekday}, "
        f"{_pct(focus['clicks'] / total_clicks)} of pooled clicks "
        f"(even share {_pct(1 / len(WEEKDAYS))})")
    lines.append(
        f"- {weekday} actions per click: "
        f"{_num(focus['actions_per_click'], 3)}, "
        f"{_num(focus['actions_per_click_vs_baseline'])} times the "
        f"baseline weekdays")
    lines.append("")
    lines.append("## Pooled weekdays")
    lines.append("")
    lines.append("| Weekday | Share of clicks | Actions per click | "
                 "vs baseline |")
    lines.append("|---|---|---|---|")
    for name in WEEKDAYS:
        if name not in pooled.index:
            continue
        row = pooled.loc[name]
        lines.append(
            f"| {name} | {_pct(row['clicks'] / total_clicks)} | "
            f"{_num(row['actions_per_click'], 3)} | "
            f"{_num(row['actions_per_click_vs_baseline'])} |")
    lines.append("")
    on_focus = mix.loc[mix["weekday"] == weekday]
    # A small tolerance, so an exactly even share is not counted
    # as above even through float rounding.
    above_even = int((on_focus["share_vs_even"] > 1 + 1e-9).sum())
    largest = on_focus["share_of_weekday_clicks"].max()
    lower = int((on_focus["actions_per_click_vs_baseline"] < 1).sum())
    lines.append(f"## Campaigns on {weekday}")
    lines.append("")
    lines.append(
        f"- Campaigns with more than an even share (1/7) of their "
        f"own clicks on {weekday}: {above_even} of {len(on_focus)}")
    lines.append(
        f"- Largest single-campaign share of {weekday} clicks: "
        f"{_pct(largest)}")
    lines.append(
        f"- Campaigns with lower actions per click on {weekday} "
        f"than on their own baseline weekdays: {lower} of "
        f"{len(on_focus)}")
    lines.append("")
    lines.append(f"## Leave-one-out ({weekday})")
    lines.append("")
    others = loo.loc[(loo["left_out"] != NONE_LEFT_OUT)
                     & (loo["weekday"] == weekday)].copy()
    full = focus["actions_per_click_vs_baseline"]
    if not others.empty and full is not None and not pd.isna(full):
        others["move"] = (others["actions_per_click_vs_baseline"]
                          - full).abs()
        biggest = others.sort_values("move").iloc[-1]
        lines.append(
            f"- {weekday} actions per click vs baseline, all "
            f"campaigns: {_num(full)}")
        lines.append(
            f"- With one campaign left out: "
            f"{_num(others['actions_per_click_vs_baseline'].min())}"
            f" to "
            f"{_num(others['actions_per_click_vs_baseline'].max())}")
        lines.append(
            f"- Leaving out the campaign with the largest effect "
            f"(its share of {weekday} clicks: "
            f"{_pct(on_focus.set_index('campaign').loc[biggest['left_out'], 'share_of_weekday_clicks'])}"
            f") moves it from {_num(full)} to "
            f"{_num(biggest['actions_per_click_vs_baseline'])}")
    else:
        lines.append("- Not enough data for leave-one-out.")
    lines.append("")
    lines.append(f"## Top {len(top)} {weekday}s by pooled clicks")
    lines.append("")
    lines.append(
        f"- {weekday}s in the data: {days_on_weekday}; the top "
        f"{len(top)} hold {_pct(top['share_of_weekday_clicks'].sum())}"
        f" of {weekday} clicks")
    lines.append("")
    lines.append("| Rank | Date | Share of weekday clicks | "
                 "Actions per click |")
    lines.append("|---|---|---|---|")
    for row in top.itertuples():
        lines.append(
            f"| {row.rank} | {row.date} | "
            f"{_pct(row.share_of_weekday_clicks)} | "
            f"{_num(row.actions_per_click, 3)} |")
    lines.append("")
    lines.append(
        "Campaign-level figures are in "
        "weekday_mix_by_campaign.csv and "
        "weekday_leave_one_out.csv.")
    lines.append("")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    """Decompose the pooled weekday cells and write aggregates."""
    parser = argparse.ArgumentParser(
        description="Split the pooled weekday cells by campaign.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        config = apply_output_root(load_config(args.config))
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    analysis = config["analysis"]
    settings = analysis.get("weekday_decomposition")
    if settings is None:
        print("Weekday decomposition skipped: "
              "analysis.weekday_decomposition is not set in the "
              "config.")
        return 0
    settings = settings or {}
    baseline = list(settings.get("baseline_weekdays")
                    or DEFAULT_BASELINE)
    count = int(settings.get("top_days", 5))
    outputs = analysis.get("outputs") or {}
    try:
        day_df = pd.read_csv(outputs["day"])
    except (KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc} (run the earlier stages first)",
              file=sys.stderr)
        return 1
    try:
        unknown = [name for name in baseline if name not in WEEKDAYS]
        if unknown:
            raise ValueError(
                "weekday_decomposition.baseline_weekdays: unknown "
                + ", ".join(unknown))
        df = prepare(day_df, analysis.get("campaign_groups") or {},
                     analysis.get("time_groups") or [])
        if df.empty:
            raise ValueError("no campaigns in analysis.time_groups")
        mix = mix_by_campaign(df, baseline)
        loo = leave_one_out(df, baseline)
        weekday = focus_weekday(df, settings)
        top = top_days(df, weekday, count)
        days_on_weekday = int(
            df.loc[df["weekday"] == weekday, "date"].nunique())
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    paths = {key: Path(outputs.get(key, default))
             for key, default in DEFAULT_OUTPUTS.items()}
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    mix.to_csv(paths["weekday_mix_by_campaign"], index=False)
    loo.to_csv(paths["weekday_leave_one_out"], index=False)
    top.to_csv(paths["weekday_top_days"], index=False)
    write_report(paths["weekday_decomposition_report"], mix, loo,
                 top, weekday, baseline, days_on_weekday)
    print(f"Weekday decomposition: {mix['campaign'].nunique()} "
          f"campaigns, focus weekday {weekday}, top {len(top)} days")
    for key in ("weekday_mix_by_campaign", "weekday_leave_one_out",
                "weekday_top_days"):
        print(f"wrote: {paths[key]}")
    print(f"report: {paths['weekday_decomposition_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
