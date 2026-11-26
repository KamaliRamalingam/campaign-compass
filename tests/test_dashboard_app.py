"""Smoke tests for the dashboard app (redesign).

The app starts and every page renders, on both clients, with and
without the optional branding.logo_path key (and with a key whose
file is missing). Uses Streamlit's AppTest; skipped when streamlit
or plotly is not installed (CI installs only requirements.txt) or
when a client's result tables are not there (outputs/ is never
committed). The logo is a made-up 1x1 PNG in a temp folder.
"""

import base64
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")

from streamlit.testing.v1 import AppTest  # noqa: E402

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
sys.path.insert(0, str(DASHBOARD))

import data as dd  # noqa: E402

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8Dw"
    "HwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
CLIENTS = ("restaurant", "synthetic_b")


def _has_outputs(client):
    try:
        config = dd.load_config(dd.client_config_path(client))
    except FileNotFoundError:
        return False
    root = dd.client_output_root(client, config)
    paths = dd.table_paths(config, output_root=root)
    return all(path.is_file() for path in paths.values())


# Runs one page of the app for one client, without st.navigation.
PAGE_SCRIPT = """
import sys
sys.path.insert(0, DASHBOARD_PATH)
import streamlit as st
import app
st.markdown(app.STYLE, unsafe_allow_html=True)
app._header([CLIENT])
ctx = app._load(CLIENT)
ctx["all_recommendations"] = ctx["tables"]["recommendations_by_campaign"]
ctx["campaigns"] = sorted(ctx["all_recommendations"]["campaign"])
app._CTX.clear()
app._CTX.update(ctx)
getattr(app, PAGE)()
"""


def _branding(monkeypatch, tmp_path, mode):
    """Patch load_config so the client config has the branding wanted."""
    original = dd.load_config

    def patched(path=None):
        config = dict(original(path))
        config.pop("branding", None)
        if mode == "missing_file":
            config["branding"] = {"logo_path": str(tmp_path / "none.png")}
        elif mode == "logo":
            logo = tmp_path / "logo.png"
            logo.write_bytes(PNG)
            config["branding"] = {"logo_path": str(logo)}
        return config

    monkeypatch.setattr(dd, "load_config", patched)


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("mode", ["no_key", "missing_file", "logo"])
@pytest.mark.parametrize("page",
                         ["act", "context", "campaign_detail", "method"])
def test_every_page_renders(client, mode, page, monkeypatch, tmp_path):
    if not _has_outputs(client):
        pytest.skip(f"no result tables for {client}: run bash run.sh")
    _branding(monkeypatch, tmp_path, mode)
    script = AppTest.from_string(
        f"DASHBOARD_PATH = {str(DASHBOARD)!r}\n"
        f"CLIENT = {client!r}\nPAGE = {page!r}\n" + PAGE_SCRIPT,
        default_timeout=60)
    script.run()
    assert not script.exception, script.exception
    page = " ".join(block.value for block in script.markdown)
    assert ("<img class='cc-logo'" in page) == (mode == "logo")
    # Wordmark in the header only without a logo. With a logo the
    # heading names the tool ("CampaignCompass · <page>:"); with the
    # wordmark it is only "<page>: <question>".
    assert ("cc-wordmark'>CampaignCompass" in page) == (mode != "logo")
    assert ("class='cc-tool'>CampaignCompass · " in page) == (mode == "logo")
    # The heading (data line under it) is at the left of the heading
    # row and the brand at its right edge, after the heading. (The
    # style block also names these classes, so match the divs.)
    assert page.index("class='cc-title'") < page.index("class='cc-data'")
    assert page.index("class='cc-data'") < page.index("class='cc-brand'")
    assert "class='cc-page'>" in page and "class='cc-q'>" in page


MOVED = ("Data completeness (lag check, monthly trend)", "Journey table",
         "Method and definitions")


@pytest.mark.parametrize("client", CLIENTS)
def test_method_page_holds_the_moved_sections(client):
    if not _has_outputs(client):
        pytest.skip(f"no result tables for {client}: run bash run.sh")
    labels = {}
    for page in ("context", "method"):
        script = AppTest.from_string(
            f"DASHBOARD_PATH = {str(DASHBOARD)!r}\n"
            f"CLIENT = {client!r}\nPAGE = {page!r}\n" + PAGE_SCRIPT,
            default_timeout=60)
        script.run()
        assert not script.exception, script.exception
        labels[page] = [block.label for block in script.expander]
    method = [label for label in labels["method"] if label in MOVED]
    assert method == list(MOVED)  # all three, in this order
    assert not set(MOVED) & set(labels["context"])
    assert any(label.startswith("Is one campaign distorting")
               for label in labels["context"])


def test_main_starts_with_top_navigation():
    if not _has_outputs("restaurant"):
        pytest.skip("no result tables: run bash run.sh")
    script = AppTest.from_file(str(DASHBOARD / "app.py"),
                               default_timeout=60)
    script.run()
    assert not script.exception, script.exception
    # Act is the default page: its heading block is there.
    text = " ".join(block.value for block in script.markdown)
    assert "Which campaigns should we continue, test or pause?" in text
    assert "Data " in text and "Updated " in text


def test_open_detail_drills_through_to_campaign_detail():
    if not _has_outputs("restaurant"):
        pytest.skip("no result tables: run bash run.sh")
    script = AppTest.from_file(str(DASHBOARD / "app.py"),
                               default_timeout=60)
    script.run()
    picked = script.selectbox(key="act_pick__restaurant")
    choice = picked.options[-1]
    picked.set_value(choice).run()
    script.button(key="act_open").click().run()
    assert not script.exception, script.exception
    text = " ".join(block.value for block in script.markdown)
    assert "How has this campaign performed?" in text
    assert script.selectbox(key="detail_campaign__restaurant").value == choice


def test_campaign_detail_table_expanders_sit_under_their_charts():
    """Campaign detail: the trend table is under the runs (left), the
    weekday table is an expander under the weekday chart, and the
    trend card holds only the chart."""
    if not _has_outputs("restaurant"):
        pytest.skip("no result tables: run bash run.sh")
    script = AppTest.from_string(
        f"DASHBOARD_PATH = {str(DASHBOARD)!r}\n"
        "CLIENT = 'restaurant'\nPAGE = 'campaign_detail'\n" + PAGE_SCRIPT,
        default_timeout=60)
    script.run()
    assert not script.exception, script.exception
    labels = [block.label for block in script.expander]
    wanted = ["Monthly table", "Weekday pattern", "Weekday table",
              "Acquisition journey"]
    assert [label for label in labels if label in wanted] == wanted
    # The weekday table is inside the weekday pattern expander.
    pattern = next(block for block in script.expander
                   if block.label == "Weekday pattern")
    assert [block.label for block in pattern.expander] == ["Weekday table"]


def test_act_tiles_title_with_count_and_two_line_campaigns():
    """Each tile: one card-title line with the count in brackets (no
    large number), then per campaign a bold name and a secondary
    status / advice line. No fixed tile height."""
    import app

    summary = {
        "tiles": [{"label": "test", "count": 3, "more": 0, "lines": [
            {"campaign": "Lunch", "label": "test", "status": "ended",
             "running": False, "action": "restart only with changes"}]}],
        "running": [{"campaign": "Dinner", "label": "test",
                     "status": "active", "running": True,
                     "action": "keep running, but test changes"}]}
    out = app._tiles_html(summary)
    assert "<div class='cc-card-title'>Test (3)</div>" in out
    assert "<div class='cc-card-title'>Running now (1)</div>" in out
    assert "<div class='cc-tile-name'>Lunch</div>" in out
    assert ("<div class='cc-tile-sub'>Ended · Restart only with changes"
            "</div>") in out
    assert ("<div class='cc-tile-sub'>Test · Keep running, but test "
            "changes</div>") in out
    # Text-only labels: no symbol anywhere in the tiles.
    assert not set(out) & set("✕◆✓●○")
    assert "cc-tile-count" not in out and "cc-tile-count" not in app.STYLE
    assert "min-height: var(--cc-tile-min)" not in app.STYLE


def _act_row(**changes):
    row = {"rank": 1, "campaign": "Lunch", "label": "test",
           "status_now": "active", "ratio_to_benchmark": 1.4,
           "tracked_actions": 120, "recent_trend": "worsening",
           "action": "keep running", "label_period":
           "2025-06-06 to 2025-10-04"}
    row.update(changes)
    return row


def test_act_table_shows_the_full_action_text():
    """A long action text is in the Act table in full: no clamp, no
    "…". The headline (up to the first "; ") is line 1 with a capital
    first letter; the rest is a smaller second line."""
    import pandas as pd

    import app

    action = ("keep running, but test changes; cost per tracked action "
              "has risen recently: check budget changes & conversion "
              "reporting")
    out = app._action_html(pd.DataFrame([_act_row(action=action)]))
    assert ("<td class='act'>Keep running, but test changes"
            "<div class='cc-act-detail'>Cost per tracked action has risen "
            "recently: check budget changes &amp; conversion reporting"
            "</div></td>") in out
    assert "…" not in out
    assert "cc-clamp" not in out and "line-clamp" not in app.STYLE
    assert ".cc-table .act {width: 32%; white-space: normal;" in app.STYLE


def test_act_table_formats_status_trend_and_period():
    """Status capitalised (Ended in grey), Trend "—" when not active
    and Worsening in bold, the period in day-month text, numbers
    right-aligned in header and cells."""
    import pandas as pd

    import app

    table = pd.DataFrame([
        _act_row(),
        _act_row(rank=2, campaign="Dinner", status_now="ended",
                 recent_trend="not_active",
                 action="restart only with changes; best run was run 2 "
                        "(2025-06-06 to 2025-10-04)",
                 label_period="2025-11-18 to 2026-07-14")])
    out = app._action_html(table)
    assert "<td>Active</td>" in out
    assert "<td class='cc-ended'>Ended</td>" in out
    assert "<td><b>Worsening</b></td>" in out
    assert "<td>—</td>" in out
    assert ("<td class='per'><span class='nw'>6 Jun –</span> "
            "<span class='nw'>4 Oct 2025</span></td>") in out
    assert ("<td class='per'><span class='nw'>18 Nov 2025 –</span> "
            "<span class='nw'>14 Jul 2026</span></td>") in out
    assert "Best run was run 2, 6 Jun – 4 Oct 2025</div>" in out
    assert "2025-06-06" not in out
    assert "<th class='n'>Ratio</th>" in out
    assert "<th class='n'>Tracked actions</th>" in out
    assert out.count("<td class='n'>") == 6


def test_act_table_label_pill_never_wraps():
    """The Final label pill stays on one line at every width: its
    cell is nowrap and no narrow-screen rule lets the pill wrap."""
    import pandas as pd

    import app

    out = app._action_html(pd.DataFrame([_act_row(
        label="pause_or_review")]))
    assert "<td class='lab'><span class='cc-pill'" in out
    assert ".stApp .cc-act .lab, .stApp .cc-act .lab .cc-pill " \
           "{white-space: nowrap;}" in app.STYLE
    narrow = app.STYLE[app.STYLE.index("@media (max-width: 1500px)"):]
    narrow = narrow[:narrow.index("}\n}") + 3]
    assert "white-space: normal" not in narrow


@pytest.mark.parametrize("client", CLIENTS)
def test_act_layout_totals_strip_and_not_comparable(client):
    """Act: tiles, then the totals strip; the old Totals box is gone;
    Not comparable sits in the right column under the chart (only
    when the client has such campaigns); How to read this is last."""
    if not _has_outputs(client):
        pytest.skip(f"no result tables for {client}: run bash run.sh")
    script = AppTest.from_string(
        f"DASHBOARD_PATH = {str(DASHBOARD)!r}\n"
        f"CLIENT = {client!r}\nPAGE = 'act'\n" + PAGE_SCRIPT,
        default_timeout=60)
    script.run()
    assert not script.exception, script.exception
    page = " ".join(block.value for block in script.markdown)
    assert "Totals and benchmark" not in page
    assert page.index("<div class='cc-tiles'>") < \
        page.index("<div class='cc-totals'>")
    assert "Total ad spend of the " in page
    captions = " ".join(block.value for block in script.caption)
    assert ("Sorted by decision: Pause or review, then Test, then "
            "Continue; the highest ratio first within each. \"—\" = no "
            "recent trend (the campaign is not active).") in captions
    labels = [block.label for block in script.expander]
    assert "Totals and benchmark" not in labels
    assert labels[-1] == "How to read this"
    config = dd.load_config(dd.client_config_path(client))
    root = dd.client_output_root(client, config)
    recs = dd.load_tables(config, output_root=root)[
        "recommendations_by_campaign"]
    count = int((recs["label"] == "not_comparable").sum())
    nc = [label for label in labels if label.startswith("Not comparable")]
    assert nc == ([f"Not comparable ({count})"] if count else [])
    if count:
        assert "Action:" not in page and "leave-one-out" not in page
        assert "Shown separately: not in the chart or the ranking." in page


def test_expander_titles_card_style_top_level_only():
    """Top-level expanders get the card-title style; expanders in a
    card or inside another expander keep the regular style."""
    import app

    assert (".stMain [data-testid=\"stExpander\"] summary p\n"
            "  {font-size: var(--cc-card-title); font-weight: 700; "
            "color: #3B2F2A;}") in app.STYLE
    assert ".stMain [data-testid=\"stExpanderDetails\"] " \
           "[data-testid=\"stExpander\"]\n  summary p," in app.STYLE
    assert ".stMain div[class*=\"st-key-card_\"] [data-testid=\"stExpander\"]" \
           " summary p\n  {font-size: var(--cc-text); font-weight: 400;}" \
        in app.STYLE
