"""Fetch Google Ads campaign data via the API (issue #74).

Usage:
    python src/fetch_ads.py --config config/restaurant.yaml
    bash run.sh --fetch        # fetch, then run the pipeline

Reads the client config for the export format (title lines,
encoding, delimiter, column headers), the date ranges
(analysis.daily_start / daily_end, analysis.monthly_end) and
the conversion breakdown file. Credentials come from
config/ads_api.yaml (git-ignored, never committed): developer
token, OAuth client ID/secret, refresh token, customer ID, and
optional login_customer_id. The google-ads library is imported
only when a real client is created, so this module imports
without it.

Queries (GAQL) and writes the three exports the loader reads,
in the exact format of the manual exports (2 title lines,
utf-8-sig, comma, headers from the config):
- campaign by day: one row per campaign per day, daily_start
  to today.
- campaign by month: one row per campaign per month, from
  fetch.monthly_start (default 2015-01) to monthly_end.
- conversion by campaign and month: one row per campaign,
  month and conversion action, from fetch.monthly_start to
  the current month.

After writing, it updates the client config in place (input
file paths, conversion file path, analysis.daily_end = today)
so the pipeline reads the fresh files. The old exports stay
in data/raw/; delete them by hand when they are no longer
needed.

Only a summary is printed per file: rows, date range,
campaigns, totals. Never campaign names, rows, or any
credential. A query that returns no rows is an error: the
fetch cannot produce a valid export from nothing.

This does not replace export validation (T0b): run.sh
--fetch skips the validation stage, because the data came
from the API itself, not from a UI export to check against.
The fetch prints its own summary so the totals can be
compared with the Ads UI by eye.
"""

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

import yaml

try:
    from src.paths import apply_output_root
except ImportError:  # running as `python src/<stage>.py`
    from paths import apply_output_root

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
DEFAULT_ADS_CONFIG = Path(__file__).resolve().parents[1] / "config" / "ads_api.yaml"
DEFAULT_MONTHLY_START = "2015-01"
REQUIRED_ADS_KEYS = (
    "developer_token",
    "client_id",
    "client_secret",
    "refresh_token",
    "customer_id",
)


def _as_date(value):
    """Return a date for a config value (a date or a string)."""
    if isinstance(value, date):
        return value
    text = str(value).strip()
    return date.fromisoformat(text)


def _month_of(value):
    """Return the YYYY-MM month for a date or a YYYY-MM string."""
    text = str(value).strip()
    return text[:7]


def load_ads_config(path):
    """Read the Ads API credentials file and return it as a dict.

    Fails naming the file when it is missing, and naming the
    key when a required credential is missing or empty.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Ads API credentials not found: {path}. Copy "
            f"config/ads_api.yaml.example to {path} and fill in "
            f"the values (see docs/daily-fetch.md). The file is "
            f"git-ignored: never commit it."
        )
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    missing = [
        key for key in REQUIRED_ADS_KEYS
        if not config.get(key) or not str(config.get(key)).strip()
    ]
    if missing:
        raise ValueError(
            f"Ads API credentials {path} are missing: "
            + ", ".join(missing)
            + ". Fill them in (see docs/daily-fetch.md)."
        )
    return config


def create_client(ads_config):
    """Build a GoogleAdsClient from the credentials dict.

    The google-ads library is imported here, not at the top,
    so this module imports without it. Fails with a clear
    message when the library is not installed.
    """
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        raise ImportError(
            "google-ads is not installed. Run: "
            ".venv/bin/pip install -r requirements-fetch.txt"
        )
    settings = {
        "developer_token": str(ads_config["developer_token"]).strip(),
        "client_id": str(ads_config["client_id"]).strip(),
        "client_secret": str(ads_config["client_secret"]).strip(),
        "refresh_token": str(ads_config["refresh_token"]).strip(),
        "use_proto_plus": True,
    }
    login_customer_id = str(ads_config.get("login_customer_id") or "").strip()
    if login_customer_id:
        settings["login_customer_id"] = login_customer_id
    return GoogleAdsClient.load_from_dict(settings)


def build_day_query(daily_start, end_date):
    """GAQL for campaign performance by day."""
    return (
        "SELECT campaign.name, segments.date, metrics.cost_micros, "
        "metrics.clicks, metrics.conversions, metrics.impressions "
        "FROM campaign "
        f"WHERE segments.date BETWEEN '{daily_start}' AND '{end_date}' "
        "ORDER BY segments.date ASC, campaign.name ASC"
    )


def build_month_query(monthly_start, monthly_end):
    """GAQL for campaign performance by month."""
    return (
        "SELECT campaign.name, segments.month, metrics.cost_micros, "
        "metrics.clicks, metrics.conversions, metrics.impressions "
        "FROM campaign "
        f"WHERE segments.month BETWEEN '{monthly_start}' AND '{monthly_end}' "
        "ORDER BY segments.month ASC, campaign.name ASC"
    )


def build_conversion_query(monthly_start, end_month):
    """GAQL for conversions by campaign, month and action."""
    return (
        "SELECT campaign.name, segments.month, "
        "segments.conversion_action_name, metrics.conversions, "
        "metrics.all_conversions "
        "FROM campaign "
        f"WHERE segments.month BETWEEN '{monthly_start}' AND '{end_month}' "
        "ORDER BY segments.month ASC, campaign.name ASC, "
        "segments.conversion_action_name ASC"
    )


def _row_to_dict(row, kind):
    """Extract the fields the exports need from one API row.

    Returns a dict keyed by logical name (date, campaign, cost
    in currency units, clicks, conversions, impressions, action,
    all_conversions). Cost is cost_micros / 1e6.
    """
    if kind == "day":
        return {
            "date": row.segments.date,
            "campaign": row.campaign.name,
            "cost": row.metrics.cost_micros / 1_000_000,
            "clicks": int(row.metrics.clicks),
            "conversions": float(row.metrics.conversions),
            "impressions": int(row.metrics.impressions),
        }
    if kind == "month":
        month = row.segments.month  # YYYY-MM
        return {
            "date": f"{month}-01",
            "campaign": row.campaign.name,
            "cost": row.metrics.cost_micros / 1_000_000,
            "clicks": int(row.metrics.clicks),
            "conversions": float(row.metrics.conversions),
            "impressions": int(row.metrics.impressions),
        }
    if kind == "conversion":
        month = row.segments.month  # YYYY-MM
        return {
            "date": f"{month}-01",
            "campaign": row.campaign.name,
            "action": row.segments.conversion_action_name,
            "conversions": float(row.metrics.conversions),
            "all_conversions": float(row.metrics.all_conversions),
        }
    raise ValueError(f"unknown kind {kind!r}")


def run_query(service, customer_id, query, kind):
    """Run one GAQL query and return its rows as a list of dicts."""
    customer_id = str(customer_id).replace("-", "").replace(" ", "").strip()
    rows = []
    for row in service.search(customer_id=customer_id, query=query):
        rows.append(_row_to_dict(row, kind))
    return rows


def _format_value(logical, value):
    """Format one value the way the manual exports write it."""
    if logical == "cost":
        return f"{float(value):,.2f}"
    if logical in ("clicks", "impressions"):
        return str(int(value))
    if logical in ("conversions", "all_conversions"):
        return f"{float(value):.2f}"
    return str(value)


def write_export(path, title_lines, headers, rows):
    """Write one export file: 2 title lines, header, rows.

    headers is a list of (logical, header) pairs, in the order
    the columns appear. Rows are dicts keyed by logical name.
    Encoding is utf-8-sig and the delimiter is a comma, the
    same as the manual exports. Fields containing a comma
    (cost with a thousands separator, campaign names) are
    quoted, so the loader reads them back as one column.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        for line in title_lines:
            writer.writerow([line])
        writer.writerow([header for _, header in headers])
        for row in rows:
            writer.writerow(
                [_format_value(logical, row[logical])
                 for logical, _ in headers]
            )


def print_summary(kind, rows, currency):
    """Print only a summary for one fetched file."""
    dates = sorted({row["date"] for row in rows})
    campaigns = {row["campaign"] for row in rows}
    cost = sum(row["cost"] for row in rows if "cost" in row)
    clicks = sum(row["clicks"] for row in rows if "clicks" in row)
    conversions = sum(row["conversions"] for row in rows)
    print(f"{kind}: rows: {len(rows)}")
    print(f"  date range: {dates[0]} to {dates[-1]}")
    print(f"  campaigns: {len(campaigns)}")
    if "cost" in rows[0]:
        print(f"  cost: {cost:,.2f} {currency}")
    if "clicks" in rows[0]:
        print(f"  clicks: {clicks:,}")
    print(f"  conversions: {conversions:,.2f}")


def _replace_value(line, new_value, quoted=False):
    """Replace the value part of a 'key: value' line, keeping the key."""
    key, _, _ = line.partition(":")
    value = f'"{new_value}"' if quoted else str(new_value)
    return f"{key}: {value}\n"


def update_config(config_path, day_path, month_path, conv_path, daily_end):
    """Update the client config in place with the fresh file paths.

    Replaces only the four lines that change (the day and month
    input paths, the conversion file path, and
    analysis.daily_end). Every other line, including comments,
    is kept byte-for-byte. The section is tracked by YAML
    indentation, so a 'path:' under input.files.day is not
    confused with one under conversion_breakdown.file.
    Returns the list of keys that were updated.
    """
    path = Path(config_path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    # Stack of (indent, key) for the mapping keys above this line.
    stack = []
    updated = []
    out = []
    # A file entry is identified by its parent section and key;
    # the value is the new path (None means leave it alone).
    flow_targets = {
        (("input", "files"), "day"): day_path,
        (("input", "files"), "month"): month_path,
        (("conversion_breakdown",), "file"): conv_path,
    }
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and ":" in stripped:
            indent = len(line) - len(line.lstrip())
            key = stripped.split(":", 1)[0].strip()
            value = stripped.split(":", 1)[1].strip()
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = tuple(k for _, k in stack)
            if not value:
                # Block mapping: opens a section.
                stack.append((indent, key))
                out.append(line)
                continue
            if value.startswith("{"):
                # Flow mapping on one line, e.g.
                # file: {path: data/raw/conv.csv, title_lines: 2}.
                # Replace the path inside the braces when this is
                # one of the file entries.
                target = flow_targets.get((parent, key))
                if target is not None and "path:" in value:
                    new_value = re.sub(
                        r"path:\s*[^,}\s]+", f"path: {target}",
                        value, count=1,
                    )
                    out.append(" " * indent + f"{key}: {new_value}\n")
                    updated.append(".".join(parent + (key,)) + ".path")
                else:
                    stack.append((indent, key))
                    out.append(line)
                continue
            section = parent
            if section == ("input", "files", "day") and key == "path":
                out.append(_replace_value(line, day_path))
                updated.append("input.files.day.path")
                continue
            if section == ("input", "files", "month") and key == "path":
                out.append(_replace_value(line, month_path))
                updated.append("input.files.month.path")
                continue
            if section == ("conversion_breakdown", "file") and key == "path":
                if conv_path is not None:
                    out.append(_replace_value(line, conv_path))
                    updated.append("conversion_breakdown.file.path")
                continue
            if section == ("analysis",) and key == "daily_end":
                out.append(_replace_value(line, daily_end, quoted=True))
                updated.append("analysis.daily_end")
                continue
        out.append(line)
    path.write_text("".join(out), encoding="utf-8")
    return updated


def main(argv=None):
    """Fetch the three exports from the Google Ads API."""
    parser = argparse.ArgumentParser(
        description="Fetch Google Ads campaign data via the API."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--ads-config", default=str(DEFAULT_ADS_CONFIG))
    parser.add_argument(
        "--today", default=None,
        help="Fetch date as YYYY-MM-DD (default: today). For tests.",
    )
    args = parser.parse_args(argv)
    try:
        from src.load import load_config
    except ImportError:
        from load import load_config
    try:
        config = load_config(args.config)
        config = apply_output_root(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        ads_config = load_ads_config(args.ads_config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    today = date.fromisoformat(args.today) if args.today else date.today()
    analysis = config.get("analysis") or {}
    daily_start = _as_date(analysis.get("daily_start"))
    monthly_end = _as_date(analysis.get("monthly_end"))
    fetch_section = config.get("fetch") or {}
    monthly_start = str(fetch_section.get("monthly_start")
                        or DEFAULT_MONTHLY_START).strip()
    currency = config.get("currency") or "SEK"
    settings = config.get("input") or {}
    columns = config.get("columns") or {}
    required = config.get("required_columns") or []

    # Resolve the repo root from the config file (config/ -> root)
    # so the written paths are relative to it, as the config is.
    repo_root = Path(args.config).resolve().parents[1]
    files = (settings.get("files") or {})
    if "day" not in files or "month" not in files:
        print("ERROR: config input.files must have day and month entries",
              file=sys.stderr)
        return 1

    def header_for(logical, kind):
        value = columns.get(logical)
        if isinstance(value, dict):
            return value.get(kind)
        return value

    # File names, following the existing naming pattern.
    day_name = (
        f"campaign_by_day_{daily_start.year}-{today.year}_"
        f"{today.isoformat()}.csv"
    )
    month_name = (
        f"campaign_by_month_{monthly_start[:4]}-{monthly_end.year}_"
        f"{today.isoformat()}.csv"
    )
    day_path = Path("data") / "raw" / day_name
    month_path = Path("data") / "raw" / month_name
    breakdown = config.get("conversion_breakdown") or {}
    conv_path = None
    conv_name = None
    if breakdown:
        conv_name = (
            f"conversion_by_campaign_month_{today.isoformat()}.csv"
        )
        conv_path = Path("data") / "raw" / conv_name

    try:
        client = create_client(ads_config)
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - report, never a token
        print(f"ERROR: could not create the Google Ads client: {exc}",
              file=sys.stderr)
        return 1
    service = client.get_service("GoogleAdsService")
    customer_id = ads_config["customer_id"]

    # Day export.
    day_rows = run_query(
        service, customer_id,
        build_day_query(daily_start.isoformat(), today.isoformat()),
        "day",
    )
    if not day_rows:
        print(
            f"ERROR: the Ads API returned no day rows for "
            f"{daily_start} to {today}",
            file=sys.stderr,
        )
        return 1
    day_headers = [
        ("date", header_for("date", "day")),
        ("campaign", header_for("campaign", "day")),
        ("cost", header_for("cost", "day")),
        ("clicks", header_for("clicks", "day")),
        ("conversions", header_for("conversions", "day")),
    ]
    if header_for("impressions", "day"):
        day_headers.append(
            ("impressions", header_for("impressions", "day"))
        )
    if any(header is None for _, header in day_headers):
        print("ERROR: config columns are missing a day header",
              file=sys.stderr)
        return 1
    write_export(
        repo_root / day_path,
        ["Google Ads API fetch",
         f"Fetched {today.isoformat()}: {daily_start} to {today}"],
        day_headers, day_rows,
    )
    print(f"  wrote: {day_path}")
    print_summary("day", day_rows, currency)

    # Month export.
    month_rows = run_query(
        service, customer_id,
        build_month_query(monthly_start, _month_of(monthly_end)),
        "month",
    )
    if not month_rows:
        print(
            f"ERROR: the Ads API returned no month rows for "
            f"{monthly_start} to {_month_of(monthly_end)}",
            file=sys.stderr,
        )
        return 1
    month_headers = [
        ("date", header_for("date", "month")),
        ("campaign", header_for("campaign", "month")),
        ("cost", header_for("cost", "month")),
        ("clicks", header_for("clicks", "month")),
        ("conversions", header_for("conversions", "month")),
    ]
    if header_for("impressions", "month"):
        month_headers.append(
            ("impressions", header_for("impressions", "month"))
        )
    if any(header is None for _, header in month_headers):
        print("ERROR: config columns are missing a month header",
              file=sys.stderr)
        return 1
    write_export(
        repo_root / month_path,
        ["Google Ads API fetch",
         f"Fetched {today.isoformat()}: {monthly_start} to "
         f"{_month_of(monthly_end)}"],
        month_headers, month_rows,
    )
    print(f"  wrote: {month_path}")
    print_summary("month", month_rows, currency)

    # Conversion breakdown export (only when the config has one).
    if breakdown:
        conv_columns = (breakdown.get("columns") or {})
        conv_rows = run_query(
            service, customer_id,
            build_conversion_query(monthly_start, _month_of(today)),
            "conversion",
        )
        if not conv_rows:
            print(
                f"ERROR: the Ads API returned no conversion rows for "
                f"{monthly_start} to {_month_of(today)}",
                file=sys.stderr,
            )
            return 1
        conv_headers = [
            ("campaign", conv_columns.get("campaign")),
            ("date", conv_columns.get("month")),
            ("action", conv_columns.get("action")),
            ("conversions", conv_columns.get("conversions")),
            ("all_conversions", conv_columns.get("all_conversions")),
        ]
        if any(header is None for _, header in conv_headers):
            print("ERROR: config conversion_breakdown.columns is "
                  "missing a header", file=sys.stderr)
            return 1
        write_export(
            repo_root / conv_path,
            ["Google Ads API fetch",
             f"Fetched {today.isoformat()}: {monthly_start} to "
             f"{_month_of(today)}"],
            conv_headers, conv_rows,
        )
        print(f"  wrote: {conv_path}")
        print_summary("conversion", conv_rows, currency)

    # Point the config at the fresh files and the new data end.
    updated = update_config(
        args.config,
        str(day_path), str(month_path),
        str(conv_path) if conv_path is not None else None,
        today.isoformat(),
    )
    print("Config updated: " + ", ".join(updated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
