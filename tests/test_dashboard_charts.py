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
         "action_text": "a", "recent_trend": "not_active"},
        {"campaign": "Beta", "label": "test", "label_ratio": 0.45,
         "status_now": "active", "action_text": "b",
         "recent_trend": "worsening"},
        {"campaign": "Gamma", "label": "continue", "label_ratio": 0.95,
         "status_now": "ended", "action_text": "c",
         "recent_trend": "not_active"},
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
    # Only the ratio: "▶" on a bar past the axis, " · worsening" when
    # the trend is worsening; no label word on the bar.
    assert list(bar.text) == ["▶ 25.37x", "0.45x · worsening", "0.95x"]
    # The hover still names the label in words.
    assert "Final label: %{customdata[0]}" in bar.hovertemplate
    assert [row[0] for row in bar.customdata] == [
        "Pause or review", "Test", "Continue"]
    assert list(bar.marker.color) == ["#C8452D", "#D9961A", "#2E9E5B"]


def test_ratio_note_defaults_arrow_and_worsening():
    assert dd.ratio_note(_lines(), _bars()) == (
        "Dashed lines: 1.0x = the average, 2.0x = twice the average. "
        "▶ = the bar continues past the chart. Worsening = cost rising "
        "recently, so the label moved down.")


def test_ratio_note_other_values_and_no_extra_sentences():
    config = {"analysis": {"recommendation_rules": {
        "continue_max_ratio": 0.8, "test_max_ratio": 1.5}}}
    lines = dd.reference_lines(config, 4.88)
    rows = _bars().iloc[2:]
    assert dd.ratio_note(lines, rows) == (
        "Dashed lines: 0.8x = 0.8x the average, 1.5x = 1.5x the average.")
    assert dd.ratio_note(_lines(), _bars().iloc[1:]) == (
        "Dashed lines: 1.0x = the average, 2.0x = twice the average. "
        "Worsening = cost rising recently, so the label moved down.")


def test_ratio_bar_dashed_lines_at_config_ratios_with_costs():
    fig = charts.ratio_bar(_bars(), _lines(), "SEK")
    dashed = [shape for shape in fig.layout.shapes
              if shape.line.dash == "dash"]
    assert sorted(shape.x0 for shape in dashed) == [1.0, 2.0]
    texts = [note.text for note in fig.layout.annotations]
    assert any("4.88<br>SEK" in text for text in texts)
    assert any("9.76<br>SEK" in text for text in texts)


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


def test_weekday_bar_outlines_busiest_cheapest_and_dearest():
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
    # One neutral colour for every bar; Mon (cheapest), Tue (dearest)
    # and Fri (busiest) all have an outline.
    assert bar.marker.color == charts.NEUTRAL
    assert list(bar.marker.line.width) == [2.5, 2.5, 2.5]
    assert [note.text for note in fig.layout.annotations] == [
        "most pooled clicks"]
    # The note still sits above the busiest weekday, not the cheapest.
    assert fig.layout.annotations[0].x == "Fri"


def test_intent_stack_hides_labels_under_five_percent():
    long = pd.DataFrame({
        "campaign": ["A", "A", "A"],
        "intent": ["Directions", "Calls", "Store visits"],
        "share": [0.92, 0.05, 0.03]})
    fig = charts.intent_stack(long)
    texts = {trace.name: list(trace.text) for trace in fig.data}
    assert texts == {"Directions": ["92%"], "Calls": ["5%"],
                     "Store visits": [""]}


def _contrast(foreground, background):
    def luminance(colour):
        rgb = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
               for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    high, low = sorted([luminance(foreground), luminance(background)],
                       reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_intent_stack_brown_family_with_readable_labels():
    long = pd.DataFrame({
        "campaign": ["A", "A", "A"],
        "intent": ["Directions", "Calls", "Store visits"],
        "share": [0.5, 0.3, 0.2]})
    fig = charts.intent_stack(long)
    colours = {trace.name: trace.marker.color for trace in fig.data}
    assert colours == {"Directions": "#6B5240", "Calls": "#A68A6D",
                       "Store visits": "#D9C7B0"}
    for trace in fig.data:
        assert trace.insidetextfont.color == charts.INTENT_TEXT[trace.name]
        assert _contrast(trace.insidetextfont.color,
                         trace.marker.color) >= 4.5
    assert fig.data[0].insidetextfont.color == "#FFFFFF"  # dark bar


def test_chart_text_from_the_data_is_escaped():
    recs = pd.DataFrame([{
        "campaign": "<a href='x'>Evil</a>", "label": "test",
        "label_ratio": 1.2, "status_now": "ended", "action_text": "a",
        "trend_override": None}])
    fig = charts.ratio_bar(dd.ratio_bar_rows(dd.action_table(recs), recs),
                           _lines(), "SEK")
    # Escaped; a long name may be split over two lines with <br>.
    assert [name.replace("<br>", " ") for name in fig.data[0].y] == [
        "&lt;a href=&#x27;x&#x27;&gt;Evil&lt;/a&gt;"]
    long = pd.DataFrame({"campaign": ["<b>x</b>"], "intent": ["Calls"],
                         "share": [1.0]})
    assert list(charts.intent_stack(long).data[0].y) == [
        "&lt;b&gt;x&lt;/b&gt;"]


def test_trend_line_uses_a_date_axis_with_gaps():
    table = pd.DataFrame({
        "month": ["2026-01", "2026-02", "2026-05"],
        "cost_per_tracked_action": [1.0, 2.0, 3.0],
        "spend": [1.0, 1.0, 1.0], "tracked_actions": [1.0, 1.0, 1.0],
        "month_note": ["", "", "partial"]})
    fig = charts.trend_line(table, "month", "Month", "SEK")
    assert fig.layout.xaxis.type == "date"
    line = fig.data[0]
    assert line.connectgaps is False
    # Five months on the axis, two of them empty (a gap in the line).
    assert len(line.x) == 5
    assert sum(1 for value in line.y if value != value) == 2
    assert fig.data[1].marker.symbol == "circle-open"
