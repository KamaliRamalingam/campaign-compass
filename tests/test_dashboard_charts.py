"""Tests for the redesigned chart builders (dashboard/charts.py).

Made-up rows only. Skipped when plotly is not installed (CI installs
only requirements.txt).
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("plotly")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import charts  # noqa: E402
import data as dd  # noqa: E402


def _bars():
    recs = pd.DataFrame([
        {"campaign": "Alpha", "label": "pause_or_review",
         "label_ratio": 25.37, "status_now": "ended",
         "action_text": "a", "trend_override": None},
        {"campaign": "Beta", "label": "test", "label_ratio": 0.45,
         "status_now": "active", "action_text": "b",
         "trend_override": "continue -> test"},
        {"campaign": "Gamma", "label": "continue", "label_ratio": 0.95,
         "status_now": "ended", "action_text": "c",
         "trend_override": None},
    ])
    return dd.ratio_bar_rows(dd.action_table(recs), recs)


def _lines():
    config = {"analysis": {"recommendation_rules": {
        "continue_max_ratio": 1.0, "test_max_ratio": 2.0}}}
    return dd.reference_lines(config, 4.88)


def test_ratio_bar_is_linear_capped_with_real_value_written():
    fig = charts.ratio_bar(_bars(), _lines(), "SEK")
    assert fig.layout.xaxis.type == "linear"
    assert tuple(fig.layout.xaxis.range) == (0, 2.5)
    bar = fig.data[0]
    assert max(bar.x) == 2.5
    assert bar.text[0].startswith("▶ 25.37x")
    assert "worsening" in bar.text[1]
    assert "worsening" not in bar.text[2]
    # Label text is written, so colour is not the only cue.
    assert "Pause or review" in bar.text[0]
    assert list(bar.marker.color) == ["#C8452D", "#D9961A", "#2E9E5B"]


def test_ratio_bar_dashed_lines_at_config_ratios_with_costs():
    fig = charts.ratio_bar(_bars(), _lines(), "SEK")
    dashed = [shape for shape in fig.layout.shapes
              if shape.line.dash == "dash"]
    assert sorted(shape.x0 for shape in dashed) == [1.0, 2.0]
    texts = [note.text for note in fig.layout.annotations]
    assert any("4.88 SEK" in text for text in texts)
    assert any("9.76 SEK" in text for text in texts)


def test_trend_line_flagged_months_are_hollow():
    table = pd.DataFrame({
        "month": ["2026-07", "2026-08", "2026-09"],
        "cost_per_tracked_action": [4.5, 2.0, 5.8],
        "spend": [1.0, 1.0, 1.0], "tracked_actions": [1.0, 1.0, 1.0],
        "month_note": ["partial", "", "partial, lagged"]})
    fig = charts.trend_line(table, "month", "Month", "SEK")
    base, rings = fig.data
    assert list(base.marker.color) == [
        "rgba(0,0,0,0)", charts.NEUTRAL, "rgba(0,0,0,0)"]
    assert rings.marker.symbol == "circle-open"
    assert list(rings.text) == ["partial", "partial, lagged"]
    assert fig.layout.yaxis.type != "log"


def test_weekday_bar_outlines_only_the_busiest_weekday():
    table = pd.DataFrame({
        "weekday": ["Mon", "Tue", "Fri"],
        "cost_per_tracked_action": [5.0, 6.0, 5.8],
        "tracked_actions": [1.0, 1.0, 1.0],
        "clicks": [10.0, 12.0, 30.0]})
    busiest = dd.most_clicks_weekday(table)
    assert busiest == "Fri"
    fig = charts.weekday_bar(table, "SEK", highlight=busiest,
                             note="most pooled clicks")
    bar = fig.data[0]
    # One neutral colour for every bar; only Fri has an outline.
    assert bar.marker.color == charts.NEUTRAL
    assert list(bar.marker.line.width) == [0, 0, 2.5]
    assert [note.text for note in fig.layout.annotations] == [
        "most pooled clicks"]


def test_intent_stack_hides_labels_under_five_percent():
    long = pd.DataFrame({
        "campaign": ["A", "A", "A"],
        "intent": ["Directions", "Calls", "Store visits"],
        "share": [0.92, 0.05, 0.03]})
    fig = charts.intent_stack(long)
    texts = {trace.name: list(trace.text) for trace in fig.data}
    assert texts == {"Directions": ["92%"], "Calls": ["5%"],
                     "Store visits": [""]}


def test_chart_text_from_the_data_is_escaped():
    recs = pd.DataFrame([{
        "campaign": "<a href='x'>Evil</a>", "label": "test",
        "label_ratio": 1.2, "status_now": "ended", "action_text": "a",
        "trend_override": None}])
    fig = charts.ratio_bar(dd.ratio_bar_rows(dd.action_table(recs), recs),
                           _lines(), "SEK")
    assert list(fig.data[0].y) == ["&lt;a href=&#x27;x&#x27;&gt;Evil&lt;/a&gt;"]
    long = pd.DataFrame({"campaign": ["<b>x</b>"], "intent": ["Calls"],
                         "share": [1.0]})
    assert list(charts.intent_stack(long).data[0].y) == [
        "&lt;b&gt;x&lt;/b&gt;"]
