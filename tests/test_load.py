"""Tests for src/load.py (T1).

All files are tiny and made up, in tmp_path. No real data, no real
campaign names, no real rows from the exports.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.load import load_config, load_export, main


def _write_csv(path, rows, header="Campaign,Day,Clicks,Cost,Conversions"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Made-up title line\n"
        "Made-up date range line\n"
        f"{header}\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )


def _config(tmp_path, day_rows=None, month_rows=None, **overrides):
    """Build a config dict pointing at made-up files in tmp_path."""
    day = tmp_path / "day.csv"
    month = tmp_path / "month.csv"
    _write_csv(day, day_rows if day_rows is not None else [
        "Alpha,2026-01-01,6,12.00,2.00",
        "Alpha,2026-01-02,4,8.00,2.00",
    ])
    _write_csv(month, month_rows if month_rows is not None else [
        "Alpha,January 2026,10,20.00,5.00",
    ], header="Campaign,Month,Clicks,Cost,Conversions")
    config = {
        "input": {
            "title_lines": 2,
            "encoding": "utf-8-sig",
            "delimiter": ",",
            "decimal": ".",
            "thousands": ",",
            "files": {
                "day": {
                    "path": str(day),
                    "output": str(tmp_path / "out" / "day.csv"),
                },
                "month": {
                    "path": str(month),
                    "output": str(tmp_path / "out" / "month.csv"),
                },
            },
        },
        "columns": {
            "date": {"day": "Day", "month": "Month"},
            "campaign": "Campaign",
            "cost": "Cost",
            "clicks": "Clicks",
            "conversions": "Conversions",
            "impressions": None,
        },
        "required_columns": ["date", "campaign", "cost", "clicks",
                             "conversions"],
    }
    config.update(overrides)
    return config


def test_valid_file_loads(tmp_path):
    df = load_export(_config(tmp_path), "day")
    assert list(df.columns) == ["date", "campaign", "clicks", "cost",
                                "conversions"]
    assert len(df) == 2
    assert df["date"].tolist() == [date(2026, 1, 1), date(2026, 1, 2)]
    assert df["clicks"].tolist() == [6, 4]
    assert df["cost"].tolist() == [12.0, 8.0]
    assert df["campaign"].nunique() == 1


def test_missing_required_column_stops_with_exact_error(tmp_path):
    config = _config(tmp_path)
    # Rewrite the day file without the Conversions header.
    day = Path(config["input"]["files"]["day"]["path"])
    _write_csv(day, ["Alpha,2026-01-01,6,12.00"],
               header="Campaign,Day,Clicks,Cost")
    with pytest.raises(ValueError) as excinfo:
        load_export(config, "day")
    assert str(excinfo.value) == "Missing required column(s): conversions"


def test_title_lines_skipped(tmp_path):
    # The two title lines are not data: 2 data rows load, not 4.
    df = load_export(_config(tmp_path), "day")
    assert len(df) == 2
    assert "Made-up title line" not in df["campaign"].tolist()


def test_totals_row_dropped_and_counted(tmp_path):
    config = _config(tmp_path, day_rows=[
        "Alpha,2026-01-01,6,12.00,2.00",
        "Total,0,0,0",
    ])
    df = load_export(config, "day")
    assert len(df) == 1
    assert df.attrs["totals_rows_dropped"] == 1


def test_decimal_and_thousands_parse(tmp_path):
    config = _config(tmp_path, day_rows=[
        'Alpha,2026-01-01,"1,234","1,234.56",2.00',
    ])
    df = load_export(config, "day")
    assert df["clicks"].tolist() == [1234]
    assert df["cost"].tolist() == [1234.56]


def test_missing_optional_column_skipped_with_message(tmp_path, capsys):
    df = load_export(_config(tmp_path), "day")
    assert "impressions" not in df.columns
    out = capsys.readouterr().out
    assert "skipped optional column" in out
    assert "impressions" in out


def test_month_dates_become_first_of_month(tmp_path):
    df = load_export(_config(tmp_path), "month")
    assert df["date"].tolist() == [date(2026, 1, 1)]


def test_main_writes_standardised_outputs(tmp_path):
    config = _config(tmp_path)
    config_path = tmp_path / "restaurant.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config))
    assert main(["--config", str(config_path)]) == 0
    day_out = Path(config["input"]["files"]["day"]["output"])
    month_out = Path(config["input"]["files"]["month"]["output"])
    assert day_out.is_file()
    assert month_out.is_file()
    assert "date,campaign,clicks,cost,conversions" in day_out.read_text()
    assert "Alpha" not in day_out.read_text().splitlines()[0]
