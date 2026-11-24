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
