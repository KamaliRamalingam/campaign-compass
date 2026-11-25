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
@pytest.mark.parametrize("page", ["act", "context", "campaign_detail"])
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
    # Wordmark in the header only without a logo. The heading always
    # names the tool now: the brand is at the top-right, not beside
    # the heading, so the heading cannot rely on it.
    assert ("cc-wordmark'>CampaignCompass" in page) == (mode != "logo")
    assert "CampaignCompass · " in page
    # The brand sits at the far right, spanning both header rows, and
    # comes after the data line in the page: the picker is above the
    # tabs and the logo is centred on the header. (The style block
    # also names these classes, so match the divs.)
    assert page.index("class='cc-brand'") > page.index("class='cc-data'")
    assert "class='cc-page'>" in page and "class='cc-q'>" in page


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
