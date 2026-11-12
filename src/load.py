"""Load the Google Ads exports into standardised tables (T1).

Usage:
    python src/load.py --config config/restaurant.yaml

Loads the campaign-by-day and campaign-by-month exports listed in
the config, using only the config: file paths, title lines,
encoding, delimiter, decimal/thousands separators, and the
columns mapping (logical name -> header in the file).

Steps per file: skip the title lines, drop any row starting with
"Total" (and report how many), rename headers to logical names,
parse dates (a month value becomes the first day of that month)
and numbers, and check the required columns. If a required column
is missing, stop with a clear error naming the missing column(s)
and exit code 1. An optional column whose header is not known or
not in the file is skipped with a printed message, not an error.

Output: standardised tables at the paths in the config, under
outputs/interim/ (git-ignored). Only a summary is printed per
file: column names, date range, row count, campaign count and
totals rows dropped. Never rows or title lines.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

try:
    from src.paths import apply_output_root
except ImportError:  # running as `python src/<stage>.py`
    from paths import apply_output_root

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "restaurant.yaml"
# Logical columns, in the order they appear in the output tables.
# Impressions is last because it is optional and may be absent.
OUTPUT_COLUMNS = ["date", "campaign", "clicks", "cost", "conversions",
                  "impressions"]


def load_config(config_path):
    """Read the YAML config file and return it as a dictionary."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {config_path}")
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or not config.get("input"):
        raise ValueError(
            f"config file {config_path} must contain an 'input' section"
        )
    return config


def _header_for(columns, logical, kind):
    """Return the header for a logical column, or None if unknown."""
    value = columns.get(logical)
    if isinstance(value, dict):
        return value.get(kind)
    return value


def _parse_number(series, decimal=".", thousands=","):
    """Parse a column of numbers given as text.

    Removes thousands separators and currency symbols, then
    converts to numbers. An empty cell counts as 0.
    """
    text = series.astype(str).str.strip()
    # Currency symbols are stripped, not assumed: the restaurant
    # exports use SEK and the synthetic Company B export uses EUR.
    for symbol in ("SEK", "EUR", "€", "$", "£"):
        text = text.str.replace(symbol, "", regex=False).str.strip()
    if thousands:
        text = text.str.replace(thousands, "", regex=False)
    if decimal and decimal != ".":
        text = text.str.replace(decimal, ".", regex=False)
    text = text.replace({"": "0", "nan": "0", "None": "0"})
    return pd.to_numeric(text, errors="raise")


def _parse_date(series, kind):
    """Parse a date column. A month value becomes its first day."""
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        # Month values such as "November 2026" -> 2026-11-01.
        parsed_month = pd.to_datetime(
            text[missing], format="%B %Y", errors="coerce"
        )
        parsed = parsed.fillna(parsed_month)
    missing = parsed.isna()
    if missing.any():
        parsed = parsed.fillna(
            pd.to_datetime(text[missing], errors="coerce")
        )
    if parsed.isna().any():
        bad = sorted(set(text[parsed.isna()].tolist()))
        raise ValueError(f"could not parse date value(s): {bad}")
    return parsed.dt.date


def load_export(config, kind):
    """Load one export (kind "day" or "month") into a DataFrame.

    Returns the standardised DataFrame. Its .attrs holds
    "totals_rows_dropped" (how many "Total" rows were dropped)
    and "skipped_optional" (optional columns skipped).
    """
    if kind not in ("day", "month"):
        raise ValueError(f"unknown kind {kind!r}: expected 'day' or 'month'")
    settings = config.get("input") or {}
    files = settings.get("files") or {}
    if kind not in files:
        raise ValueError(f"config input.files has no entry for kind {kind!r}")
    entry = files[kind]
    path = entry["path"] if isinstance(entry, dict) else entry
    columns = config.get("columns") or {}
    required = config.get("required_columns") or []

    # Resolve the header for every logical column.
    headers = {}
    for logical in OUTPUT_COLUMNS:
        headers[logical] = _header_for(columns, logical, kind)

    df = pd.read_csv(
        path,
        skiprows=settings.get("title_lines", 2),
        encoding=settings.get("encoding") or "utf-8-sig",
        delimiter=settings.get("delimiter") or ",",
        dtype=str,
        keep_default_na=False,
    )

    # Required columns: fail naming the missing logical names.
    missing = [
        logical for logical in required
        if not headers.get(logical) or headers[logical] not in df.columns
    ]
    if missing:
        raise ValueError(
            "Missing required column(s): " + ", ".join(missing)
        )

    # Optional columns: skip with a printed message, do not fail.
    skipped_optional = []
    for logical in OUTPUT_COLUMNS:
        if logical in required:
            continue
        header = headers.get(logical)
        if not header or header not in df.columns:
            skipped_optional.append(logical)
    if skipped_optional:
        print(f"INFO: skipped optional column(s): "
              f"{', '.join(skipped_optional)}")

    # Drop totals rows: any row whose first cell starts with "Total".
    first = df.iloc[:, 0].astype(str).str.strip()
    is_total = first.str.lower().str.startswith("total")
    totals_dropped = int(is_total.sum())
    df = df.loc[~is_total].copy()

    # Drop fully empty rows (only days/months with activity are present,
    # so any empty row is padding, not data).
    df = df.loc[df.astype(str).apply(
        lambda row: row.str.strip().any(), axis=1
    )].copy()

    # Rename headers to logical names, keeping only mapped columns.
    rename = {
        headers[logical]: logical
        for logical in OUTPUT_COLUMNS
        if headers.get(logical) and headers[logical] in df.columns
    }
    df = df.rename(columns=rename)
    keep = [logical for logical in OUTPUT_COLUMNS if logical in df.columns]
    df = df[keep]

    # Parse dates and numbers.
    df["date"] = _parse_date(df["date"], kind)
    decimal = settings.get("decimal") or "."
    thousands = settings.get("thousands")
    if thousands is None:
        thousands = ","
    for logical in ("clicks", "cost", "conversions", "impressions"):
        if logical in df.columns:
            df[logical] = _parse_number(df[logical], decimal, thousands)
    if "clicks" in df.columns:
        df["clicks"] = df["clicks"].astype("int64")
    if "impressions" in df.columns:
        df["impressions"] = df["impressions"].astype("int64")

    df.attrs["totals_rows_dropped"] = totals_dropped
    df.attrs["skipped_optional"] = skipped_optional
    return df


def print_summary(kind, df):
    """Print only a summary for one loaded file."""
    print(f"{kind}: columns: {list(df.columns)}")
    print(f"  date range: {df['date'].min()} to {df['date'].max()}")
    print(f"  rows: {len(df)}")
    print(f"  campaigns: {df['campaign'].nunique()}")
    print(f"  totals rows dropped: {df.attrs.get('totals_rows_dropped', 0)}")


def main(argv=None):
    """Load both exports and write the standardised tables."""
    parser = argparse.ArgumentParser(
        description="Load Google Ads exports into standardised tables."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--kind", choices=["day", "month", "all"], default="all",
        help="Load one export, or both (default).",
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        config = apply_output_root(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    kinds = ["day", "month"] if args.kind == "all" else [args.kind]
    for kind in kinds:
        try:
            df = load_export(config, kind)
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        entry = config["input"]["files"][kind]
        out_path = Path(entry["output"]) if isinstance(entry, dict) else None
        if out_path is None:
            print(f"ERROR: no output path in config for kind {kind!r}",
                  file=sys.stderr)
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        print_summary(kind, df)
        print(f"  wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
