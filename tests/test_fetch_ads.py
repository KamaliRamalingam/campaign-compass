"""Tests for src/fetch_ads.py (Google Ads API fetch, issue #74).

All data is tiny and made up, in tmp_path. The Google Ads API
is never called: the tests use a fake client whose service
returns fixed rows with the same attribute shape as the real
google-ads rows (row.campaign.name, row.segments.date/month,
row.metrics.cost_micros/clicks/conversions/impressions/
all_conversions). No credentials and no network.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import fetch_ads  # noqa: E402
from src.load import load_export, load_config  # noqa: E402


def _fake_row(kind, **values):
    """A fake google-ads row with the real attribute shape."""
    metrics = SimpleNamespace(
        cost_micros=values.get("cost_micros", 0),
        clicks=values.get("clicks", 0),
        conversions=values.get("conversions", 0.0),
        impressions=values.get("impressions", 0),
        all_conversions=values.get("all_conversions", 0.0),
    )
    segments = SimpleNamespace(
        date=values.get("date", ""),
        month=values.get("month", ""),
        conversion_action_name=values.get("action", ""),
    )
    campaign = SimpleNamespace(name=values.get("campaign", ""))
    return SimpleNamespace(
        campaign=campaign, segments=segments, metrics=metrics,
    )


class _FakeService:
    """Returns fixed rows per query kind; records the queries."""

    def __init__(self, rows_by_kind):
        self.rows_by_kind = rows_by_kind
        self.queries = []
        self.customer_ids = []

    def search(self, customer_id, query):
        self.customer_ids.append(customer_id)
        self.queries.append(query)
        if "segments.date" in query:
            return list(self.rows_by_kind.get("day", []))
        if "conversion_action_name" in query:
            return list(self.rows_by_kind.get("conversion", []))
        return list(self.rows_by_kind.get("month", []))


class _FakeClient:
    def __init__(self, service):
        self._service = service

    def get_service(self, name):
        assert name == "GoogleAdsService"
        return self._service


def _tiny_config(tmp_path):
    """A minimal client config (made-up campaign Alpha)."""
    config = tmp_path / "config" / "restaurant.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "# A comment that must survive the config update.\n"
        "client: restaurant_chain\n"
        "currency: SEK\n"
        "input:\n"
        "  title_lines: 2\n"
        "  encoding: utf-8-sig\n"
        "  delimiter: ','\n"
        "  decimal: '.'\n"
        "  thousands: ','\n"
        "  files:\n"
        "    day:\n"
        "      path: data/raw/day.csv\n"
        "      output: outputs/interim/campaign_by_day.csv\n"
        "    month:\n"
        "      path: data/raw/month.csv\n"
        "      output: outputs/interim/campaign_by_month.csv\n"
        "columns:\n"
        "  date: {day: Day, month: Month}\n"
        "  campaign: Campaign\n"
        "  cost: Cost\n"
        "  clicks: Clicks\n"
        "  conversions: Conversions\n"
        "  impressions: 'Impr.'\n"
        "required_columns: [date, campaign, cost, clicks, conversions]\n"
        "analysis:\n"
        "  daily_start: '2026-01-01'\n"
        "  daily_end: '2026-01-07'\n"
        "  monthly_end: '2025-12-31'\n"
        "conversion_breakdown:\n"
        "  file: {path: data/raw/conv.csv, title_lines: 2}\n"
        "  columns: {campaign: Campaign, month: Month, action: Conversion action, conversions: Conversions, all_conversions: 'All conv.'}\n"
        "  ui_expected: {conversions: 4.0, all_conversions: 40.0, tolerance: 0.05}\n"
    )
    return config


def _tiny_ads_config(tmp_path):
    """A credentials file with made-up values (never real)."""
    path = tmp_path / "config" / "ads_api.yaml"
    path.write_text(
        "developer_token: 'MADE_UP_TOKEN'\n"
        "client_id: 'MADE_UP_CLIENT'\n"
        "client_secret: 'MADE_UP_SECRET'\n"
        "refresh_token: 'MADE_UP_REFRESH'\n"
        "customer_id: '1234-567890'\n"
        # Made-up: the dash is there so the test proves dashes are
        # stripped, but the shape is not a real customer ID (the
        # check_no_data guard rejects \d{3}-\d{3}-\d{4}).
    )
    return path


def _rows():
    """Made-up API rows for the three queries."""
    day = [
        _fake_row("day", date="2026-01-01", campaign="Alpha",
                  cost_micros=12_000_000, clicks=6, conversions=2.0,
                  impressions=100),
        _fake_row("day", date="2026-01-02", campaign="Alpha",
                  cost_micros=8_000_000, clicks=4, conversions=2.0,
                  impressions=80),
        _fake_row("day", date="2026-01-01", campaign="Beta, Inc",
                  cost_micros=1_234_560, clicks=3, conversions=1.5,
                  impressions=50),
    ]
    month = [
        _fake_row("month", month="2025-12", campaign="Alpha",
                  cost_micros=20_000_000, clicks=10, conversions=5.0,
                  impressions=200),
    ]
    conversion = [
        _fake_row("conversion", month="2026-01", campaign="Alpha",
                  action="Store visits", conversions=2.0,
                  all_conversions=20.0),
        _fake_row("conversion", month="2026-01", campaign="Alpha",
                  action="Local actions - Menu views",
                  conversions=2.0, all_conversions=20.0),
    ]
    return {"day": day, "month": month, "conversion": conversion}


def test_queries_contain_fields_and_dates():
    day = fetch_ads.build_day_query("2026-01-01", "2026-11-27")
    assert "campaign.name" in day
    assert "segments.date" in day
    assert "metrics.cost_micros" in day
    assert "metrics.clicks" in day
    assert "metrics.conversions" in day
    assert "metrics.impressions" in day
    assert "BETWEEN '2026-01-01' AND '2026-11-27'" in day
    month = fetch_ads.build_month_query("2015-01", "2025-12")
    assert "segments.month" in month
    assert "BETWEEN '2015-01' AND '2025-12'" in month
    conv = fetch_ads.build_conversion_query("2015-01", "2026-11")
    assert "segments.conversion_action_name" in conv
    assert "metrics.all_conversions" in conv
    assert "BETWEEN '2015-01' AND '2026-11'" in conv


def test_row_to_dict_converts_cost_micros():
    row = _fake_row("day", date="2026-01-01", campaign="Alpha",
                    cost_micros=12_345_678, clicks=6,
                    conversions=2.5, impressions=100)
    out = fetch_ads._row_to_dict(row, "day")
    assert out["date"] == "2026-01-01"
    assert out["campaign"] == "Alpha"
    assert out["cost"] == pytest.approx(12.345678)
    assert out["clicks"] == 6
    assert out["conversions"] == pytest.approx(2.5)
    month = fetch_ads._row_to_dict(
        _fake_row("month", month="2025-12", campaign="Alpha",
                  cost_micros=20_000_000, clicks=10,
                  conversions=5.0, impressions=200),
        "month",
    )
    assert month["date"] == "2025-12-01"
    conv = fetch_ads._row_to_dict(
        _fake_row("conversion", month="2026-01", campaign="Alpha",
                  action="Store visits", conversions=2.0,
                  all_conversions=20.0),
        "conversion",
    )
    assert conv["date"] == "2026-01-01"
    assert conv["action"] == "Store visits"
    assert conv["all_conversions"] == pytest.approx(20.0)


def test_load_ads_config_missing_file_and_keys(tmp_path):
    with pytest.raises(FileNotFoundError, match="ads_api.yaml"):
        fetch_ads.load_ads_config(tmp_path / "config" / "ads_api.yaml")
    path = tmp_path / "ads.yaml"
    path.write_text("developer_token: 'x'\n")
    with pytest.raises(ValueError, match="client_id"):
        fetch_ads.load_ads_config(path)
    good = tmp_path / "good.yaml"
    good.write_text(
        "developer_token: 't'\nclient_id: 'c'\n"
        "client_secret: 's'\nrefresh_token: 'r'\n"
        "customer_id: '1'\n"
    )
    assert fetch_ads.load_ads_config(good)["customer_id"] == "1"


def test_update_config_keeps_comments_and_only_changes_four_lines(tmp_path):
    config = _tiny_config(tmp_path)
    before = config.read_text()
    updated = fetch_ads.update_config(
        config,
        "data/raw/campaign_by_day_2026-2026_2026-11-27.csv",
        "data/raw/campaign_by_month_2015-2025_2026-11-27.csv",
        "data/raw/conversion_by_campaign_month_2026-11-27.csv",
        "2026-11-27",
    )
    after = config.read_text()
    assert "# A comment that must survive the config update." in after
    assert "currency: SEK" in after
    assert "campaign_by_day_2026-2026_2026-11-27.csv" in after
    assert "campaign_by_month_2015-2025_2026-11-27.csv" in after
    assert "conversion_by_campaign_month_2026-11-27.csv" in after
    assert 'daily_end: "2026-11-27"' in after
    # Only the four lines changed.
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    assert len(before_lines) == len(after_lines)
    changed = [i for i, (a, b) in enumerate(zip(before_lines, after_lines))
               if a != b]
    assert len(changed) == 4
    assert sorted(updated) == sorted([
        "input.files.day.path", "input.files.month.path",
        "conversion_breakdown.file.path", "analysis.daily_end",
    ])
    # The output paths and the other dates are untouched.
    assert "outputs/interim/campaign_by_day.csv" in after
    assert "daily_start: '2026-01-01'" in after
    assert "monthly_end: '2025-12-31'" in after


def test_main_writes_loader_compatible_files(tmp_path, monkeypatch):
    config = _tiny_config(tmp_path)
    ads = _tiny_ads_config(tmp_path)
    service = _FakeService(_rows())
    monkeypatch.setattr(
        fetch_ads, "create_client",
        lambda ads_config: _FakeClient(service),
    )
    monkeypatch.chdir(tmp_path)
    rc = fetch_ads.main([
        "--config", str(config),
        "--ads-config", str(ads),
        "--today", "2026-11-27",
    ])
    assert rc == 0
    # The customer ID is sent without dashes.
    assert service.customer_ids == ["1234567890"] * 3
    # The config now points at the fresh files.
    new_config = load_config(config)
    day_path = new_config["input"]["files"]["day"]["path"]
    month_path = new_config["input"]["files"]["month"]["path"]
    conv_path = new_config["conversion_breakdown"]["file"]["path"]
    assert day_path == "data/raw/campaign_by_day_2026-2026_2026-11-27.csv"
    assert month_path == "data/raw/campaign_by_month_2015-2025_2026-11-27.csv"
    assert conv_path == "data/raw/conversion_by_campaign_month_2026-11-27.csv"
    assert str(new_config["analysis"]["daily_end"]) == "2026-11-27"
    # The day file loads through the real loader, including the
    # campaign name with a comma (quoted, so it stays one column).
    day_df = load_export(new_config, "day")
    assert len(day_df) == 3
    assert set(day_df["campaign"]) == {"Alpha", "Beta, Inc"}
    assert day_df["cost"].sum() == pytest.approx(12.00 + 8.00 + 1.23)
    assert day_df["clicks"].sum() == 13
    assert day_df["conversions"].sum() == pytest.approx(5.5)
    assert day_df["impressions"].sum() == 230
    # The month file loads too, with the month as its first day.
    month_df = load_export(new_config, "month")
    assert len(month_df) == 1
    assert str(month_df["date"].iloc[0]) == "2025-12-01"
    assert month_df["cost"].iloc[0] == pytest.approx(20.00)
    # The conversion file parses: headers and values as written.
    conv_df = pd.read_csv(
        tmp_path / conv_path, skiprows=2, encoding="utf-8-sig",
    )
    assert list(conv_df.columns) == [
        "Campaign", "Month", "Conversion action",
        "Conversions", "All conv.",
    ]
    assert len(conv_df) == 2
    assert conv_df["Conversions"].sum() == pytest.approx(4.0)
    assert conv_df["All conv."].sum() == pytest.approx(40.0)
    # The title lines are present and the loader skipped them.
    first_lines = (tmp_path / day_path).read_text(
        encoding="utf-8-sig").splitlines()
    assert first_lines[0] == "Google Ads API fetch"
    assert "2026-11-27" in first_lines[1]
    assert first_lines[2].startswith("Day,Campaign,Cost")


def test_main_fails_when_credentials_missing(tmp_path, monkeypatch):
    config = _tiny_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = fetch_ads.main([
        "--config", str(config),
        "--ads-config", str(tmp_path / "config" / "ads_api.yaml"),
        "--today", "2026-11-27",
    ])
    assert rc == 1
    # Nothing was written and the config is untouched.
    assert not (tmp_path / "data" / "raw").exists()
    assert "2026-01-07" in config.read_text()


def test_main_fails_when_api_returns_no_rows(tmp_path, monkeypatch):
    config = _tiny_config(tmp_path)
    ads = _tiny_ads_config(tmp_path)
    service = _FakeService({"day": [], "month": [], "conversion": []})
    monkeypatch.setattr(
        fetch_ads, "create_client",
        lambda ads_config: _FakeClient(service),
    )
    monkeypatch.chdir(tmp_path)
    rc = fetch_ads.main([
        "--config", str(config),
        "--ads-config", str(ads),
        "--today", "2026-11-27",
    ])
    assert rc == 1
    assert not (tmp_path / "data" / "raw" / "campaign_by_day_2026-2026_2026-11-27.csv").exists()
    assert "2026-01-07" in config.read_text()


def test_main_skips_conversion_when_section_absent(tmp_path, monkeypatch):
    config = _tiny_config(tmp_path)
    text = config.read_text()
    # Drop the conversion_breakdown section entirely.
    text = text.split("conversion_breakdown:")[0]
    config.write_text(text)
    ads = _tiny_ads_config(tmp_path)
    service = _FakeService(_rows())
    monkeypatch.setattr(
        fetch_ads, "create_client",
        lambda ads_config: _FakeClient(service),
    )
    monkeypatch.chdir(tmp_path)
    rc = fetch_ads.main([
        "--config", str(config),
        "--ads-config", str(ads),
        "--today", "2026-11-27",
    ])
    assert rc == 0
    # Only the day and month queries ran.
    assert len(service.queries) == 2
    assert not list((tmp_path / "data" / "raw").glob("conversion_*"))
