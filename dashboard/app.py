"""Local Streamlit dashboard (T8, reworked in PR 4, restyled in PR 5).

Run it with: bash dashboard.sh (after bash run.sh). It listens
on localhost only.

Four pages: Act (which campaigns to continue, test or pause),
Context (can we trust this?), Campaign detail (opened from the Act
ranking or picked directly) and Method (how the labels were built:
data completeness, journey table, method and definitions). Charts are Plotly,
built in dashboard/charts.py.

Reads only the client's results and reports folders, never
data/raw/ or outputs/interim/. All data preparation lives in
dashboard/data.py; this file only displays. Labels are the FINAL
labels (after the trend override) from
recommendations_by_campaign.csv; nothing is recomputed here. No
hosting, login, uploads or network access.

Every page shows the caveat (data.CAVEAT_TEXT), the data date
range and the last-updated date. The wording is "tracked actions"
everywhere.
"""

import base64
import html
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import data as dashboard_data  # noqa: E402

WIDE = st.column_config.TextColumn  # shorthand below
NUM = st.column_config.NumberColumn
DETAIL_KEY = "detail_campaign"
# Widgets whose options depend on the client: reset on a switch.
CLIENT_WIDGETS = ("act_group", "act_status", "act_pick", DETAIL_KEY,
                  "ctx_trend_campaign", "ctx_weekday",
                  "method_trend_campaign")

# Warm spice theme (redesign). Colours: text #3B2F2A, secondary
# #7A6B5F (#6B5E54 inside tinted tiles, for 4.5:1), card border
# #EADFCF, brand green #254C31 for the heading, KPI values, the
# active tab and buttons. Open Sans from Google Fonts; Helvetica / Arial
# when offline.
GREEN = "#254C31"
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap');
/* Scale: every size below comes from these variables, so the whole
   dashboard can be tuned here. --cc-s is the overall scale (0.88 =
   about 12% smaller than the original design). Streamlit sizes its
   own widgets (selects, inputs, buttons, card padding) in rem, so
   the root font size follows the same scale.
   Type scale: five text styles, all Open Sans (sizes at --cc-s
   0.88): card title 16px 700 charcoal; label 13px 600 secondary;
   value (KPI numbers) 24px 600 deep green; body 13px 400 charcoal;
   caption 12.5px 400 secondary, line-height 1.35. The older size
   names below point at these five. */
:root {
  --cc-s: 0.88;
  --cc-pad-k: calc(var(--cc-s) - 0.08);          /* padding: ~20% less */
  --cc-root: calc(16px * var(--cc-s));
  --cc-t-title: calc(18.18px * var(--cc-s));          /* 16px */
  --cc-t-label: calc(14.77px * var(--cc-s));          /* 13px */
  --cc-t-value: calc(27.27px * var(--cc-s));          /* 24px */
  --cc-t-body: calc(14.77px * var(--cc-s));           /* 13px */
  --cc-t-cap: calc(14.2px * var(--cc-s));             /* 12.5px */
  --cc-text: var(--cc-t-body);
  --cc-small: var(--cc-t-cap);
  --cc-foot: var(--cc-t-cap);
  --cc-th: var(--cc-t-label);
  --cc-num: var(--cc-t-value);
  --cc-kpi: var(--cc-t-value);
  --cc-badge: calc(20px * var(--cc-s));
  --cc-card-title: var(--cc-t-title);
  --cc-label: var(--cc-t-label);
  --cc-tot-pad: calc(15.91px * var(--cc-s));          /* 14px */
  --cc-tot-gap: calc(4.55px * var(--cc-s));           /* 4px */
  --cc-wordmark: calc(22px * var(--cc-s));
  --cc-gap: calc(13.64px * var(--cc-s));             /* 12px */
  --cc-pad-y: calc(14px * var(--cc-pad-k));
  --cc-pad-x: calc(16px * var(--cc-pad-k));
  --cc-page-max: 1500px;                              /* content width */
  --cc-side: 24px;                                    /* side padding */
  --cc-logo-h: 64px;
  --cc-picker-w: 160px;
}
html {font-size: var(--cc-root);}
html, body, .stApp, .stApp p, .stApp div, .stApp label, .stApp input,
.stApp button, .stApp td, .stApp th, .stApp li, .stApp a {
  font-family: 'Open Sans', Helvetica, Arial, sans-serif;}
[data-testid="stIconMaterial"], .material-symbols-rounded {
  font-family: 'Material Symbols Rounded' !important;}
.stApp {background: #FBF6EE; color: #3B2F2A;}
/* Page width: at most 1500px of content, centred, 24px side
   padding; the header uses the same box so both share one edge. */
.block-container {padding: 4px var(--cc-side) 3rem;
  max-width: calc(var(--cc-page-max) + 2 * var(--cc-side));}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"]
  {display: none;}
[data-testid="stVerticalBlock"] {gap: var(--cc-gap);}
[data-testid="stHorizontalBlock"] {gap: var(--cc-gap);}
h1, h2, h3, h4 {color: #3B2F2A !important;}
p, li, td, th {font-size: var(--cc-text);}
/* Streamlit sets markdown paragraphs in rem; they are body text. */
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li
  {font-size: var(--cc-t-body);}
/* Streamlit text in the type scale: widget labels are labels, the
   checkbox and radio options are body (weight 500 for the checkbox),
   captions are captions, buttons, inputs and the caveat are body. */
.stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stWidgetLabel"] span
  {font-size: var(--cc-t-label); font-weight: 600; color: #7A6B5F;}
.stApp [data-testid="stCheckbox"] label p,
.stApp [data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p
  {font-size: var(--cc-t-body); font-weight: 500; color: #3B2F2A;}
.stApp [role="radiogroup"] label p {font-size: var(--cc-t-body);
  font-weight: 400; color: #3B2F2A;}
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] p
  {font-size: var(--cc-t-cap); font-weight: 400; color: #7A6B5F;
   line-height: 1.35;}
.stApp .stButton button p, .stApp .stDownloadButton button p,
.stApp input, .stApp [data-testid="stAlert"] p
  {font-size: var(--cc-t-body);}

/* No header bar: Streamlit's header is transparent and empty except
   for its menu (⋮). The header is two rows at every width: the
   heading (one line, data line under it) at the left and the logo
   (or the wordmark) at the right edge; then the page tabs at the
   left, under the heading text, and the client picker at the right,
   with room after it for the menu. The menu is centred in the
   header overlay, and the tabs row's middle is about 112px from the
   top (16px above the 64px heading row, a 12px gap, then the tabs
   row), so the overlay is 225px high. */
[data-testid="stHeader"], [data-testid="stAppHeader"]
  {background: transparent; border: 0; height: 225px;
   pointer-events: none;}
[data-testid="stDecoration"] {display: none;}
[data-testid="stToolbar"] {height: 225px; align-items: center;
  max-width: calc(var(--cc-page-max) + 2 * var(--cc-side));
  margin: 0 auto; padding: 0 8px 0 var(--cc-side);
  box-sizing: border-box; left: 0; right: 0;}
/* The empty header must not catch clicks meant for the top row;
   only its menu (⋮) stays clickable. */
[data-testid="stHeader"] * {pointer-events: none;}
[data-testid="stHeader"] [data-testid="stMainMenu"],
[data-testid="stHeader"] [data-testid="stMainMenu"] *
  {pointer-events: auto;}
[data-testid="stMainMenu"] {background: #FBF6EE; border-radius: 50%;}
.st-key-cc_header {padding: 0; margin: 0;}
.st-key-cc_header [data-testid="stMarkdownContainer"],
.st-key-cc_header [data-testid="stElementContainer"] {margin: 0;}
/* Tabs row: tabs at the left, picker at the right; the 40px right
   margin leaves room for the menu (⋮). */
.st-key-cc_controls {justify-content: space-between; align-items: center;
  gap: var(--cc-gap); flex-wrap: nowrap; padding-right: 40px;
  box-sizing: border-box;}
/* Heading row: heading at the left, brand at the right edge. */
.cc-head {display: flex; align-items: center; gap: 24px;
  min-height: var(--cc-logo-h); min-width: 0;}
.cc-headtext {flex: 1 1 auto; min-width: 0;}
.cc-brand {display: flex; align-items: center; justify-content: flex-end;
  min-height: var(--cc-logo-h); flex: 0 0 auto; margin-left: auto;}
.cc-logo {height: var(--cc-logo-h); width: auto; display: block;
  flex: 0 0 auto;}
.cc-wordmark {font-size: var(--cc-wordmark); font-weight: 600;
  letter-spacing: 0.2em; text-transform: uppercase; color: #7A6B5F;
  flex: 0 0 auto; white-space: nowrap;}
/* Page tabs: plain text; the active one has a 3px green underline.
   The first tab's text starts at the heading's left edge. */
.st-key-cc_nav {justify-content: flex-start; gap: 4px; flex-wrap: nowrap;
  width: auto; margin-left: -12px;}
.st-key-cc_nav [data-testid="stPageLink"] a {background: transparent;
  border-radius: 0; padding: 6px 12px 5px; border-bottom: 3px solid
  transparent;}
.st-key-cc_nav [data-testid="stPageLink"] a:hover
  {background: transparent; border-bottom-color: #D9CFC0;}
.st-key-cc_nav [data-testid="stPageLink"] p {font-size: var(--cc-small);
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;
  color: #3B2F2A; white-space: nowrap;}
.st-key-cc_nav_on [data-testid="stPageLink"] a
  {border-bottom-color: #254C31;}
.st-key-cc_nav_on [data-testid="stPageLink"] a:hover
  {border-bottom-color: #254C31;}
.st-key-cc_nav_on [data-testid="stPageLink"] p {color: #254C31;}

/* Heading: always one deep green line, tool and page name in 600
   weight, the question in 400; never wraps. The size follows the
   window (18px up to about 28px at the 1500px content cap) so the
   longest heading (Context) fits beside the brand. Below 1150px the
   "CampaignCompass · " part is hidden (the logo already names the
   tool) and the wordmark is smaller. Data line grey under it. */
.stApp .cc-title {font-size:
    clamp(18px, calc((min(100vw, 1548px) - 260px) / 46), 32px);
  line-height: 1.2; color: #254C31; margin: 0; white-space: nowrap;}
@media (max-width: 1149px) {
  .stApp .cc-tool {display: none;}
  .cc-wordmark {font-size: var(--cc-t-title);}
}
.stApp .cc-page {font-weight: 600; color: #254C31;}
.stApp .cc-q {font-weight: 400; color: #254C31;}
.stApp .cc-data {font-size: var(--cc-text); font-weight: 400;
  color: #7A6B5F; margin: 4px 0 0; white-space: nowrap;}

/* Caveat banner: white, warm border, charcoal text. */
[data-testid="stAlert"] > div {background: #FFFFFF; color: #3B2F2A;
  border: 1px solid #EADFCF;}
[data-testid="stAlert"] p {color: #3B2F2A;}

/* Cards: white on the beige page, warm border. */
div[class*="st-key-card_"] {background: #FFFFFF;
  border: 1px solid #EADFCF !important; border-radius: 8px;}
/* Expanders: white card, white header row with a thin line under it
   when open. */
[data-testid="stExpander"] details {background: #FFFFFF;
  border: 1px solid #EADFCF; border-radius: 8px;}
[data-testid="stExpander"] summary {background: #FFFFFF;
  border-radius: 8px;}
[data-testid="stExpander"] summary:hover {background: #FFFFFF;}
[data-testid="stExpander"] details[open] > summary
  {border-bottom: 1px solid #EADFCF; border-radius: 8px 8px 0 0;}
[data-testid="stExpanderDetails"] {border: 0 !important;
  background: #FFFFFF;}
/* Expander titles: a top-level expander is a card, so its title has
   the card-title style. An expander inside a card or inside another
   expander only hides a table: it keeps the regular, lighter text. */
.stMain [data-testid="stExpander"] summary p
  {font-size: var(--cc-card-title); font-weight: 700; color: #3B2F2A;}
.stMain [data-testid="stExpanderDetails"] [data-testid="stExpander"]
  summary p,
.stMain div[class*="st-key-card_"] [data-testid="stExpander"] summary p
  {font-size: var(--cc-text); font-weight: 400;}
/* Space after HTML blocks (Streamlit gives markdown a negative bottom
   margin, so rows of HTML cards would touch the next row). */
.cc-tiles, .cc-stat {margin-bottom: var(--cc-gap);}
.cc-stat {background: #FFFFFF; border: 1px solid #EADFCF;
  border-radius: 8px; padding: var(--cc-pad-y) var(--cc-pad-x);
  box-sizing: border-box;}
.cc-stat-title {font-size: var(--cc-card-title); font-weight: 700;
  color: #3B2F2A;}
.cc-stat-v {font-size: var(--cc-num); font-weight: 600; line-height: 1.2;
  margin-top: 4px; color: #254C31;}
/* Act totals strip: one white bar, four items with thin dividers,
   2 x 2 below about 1100px. */
.cc-totals {display: grid; grid-template-columns: repeat(4, 1fr);
  background: #FFFFFF; border: 1px solid #EADFCF; border-radius: 8px;
  margin-bottom: var(--cc-gap); box-sizing: border-box;}
.cc-tot {padding: var(--cc-tot-pad); border-left: 1px solid #EADFCF;
  min-width: 0; line-height: 1.3;}
.cc-tot:first-child {border-left: 0;}
.cc-tot-l {font-size: var(--cc-t-label); font-weight: 600; color: #7A6B5F;
  line-height: 1.3;}
.cc-tot-v {font-size: var(--cc-t-value); font-weight: 600; line-height: 1.3;
  color: #254C31; margin: var(--cc-tot-gap) 0;}
.cc-tot-c {font-size: var(--cc-t-cap); color: #7A6B5F; line-height: 1.35;}
@media (max-width: 1100px) {
  .cc-totals {grid-template-columns: 1fr 1fr;}
  .cc-tot:nth-child(3) {border-left: 0;}
  .cc-tot:nth-child(n+3) {border-top: 1px solid #EADFCF;}
}
/* Not comparable card: bold name, then two small grey lines. */
.cc-nc {margin-top: 8px;}
.cc-nc-sub {font-size: var(--cc-small); color: #7A6B5F; line-height: 1.35;
  margin-top: 1px;}
/* How to read this: bullets in two columns where the width allows. */
.cc-foot-2 ul {columns: 2; column-gap: 32px;}
.cc-foot-2 li {break-inside: avoid;}
@media (max-width: 900px) {.cc-foot-2 ul {columns: 1;}}
.cc-card-title, .stApp .stMarkdown p.cc-card-title,
.stApp [data-testid="stMarkdownContainer"] p.cc-card-title
  {font-size: var(--cc-card-title); font-weight: 700; line-height: 1.35;
  margin: 0 0 4px; color: #3B2F2A;}

/* Equal-height rows (Campaign detail cc_detail_*, Context cc_eq_*):
   the columns of a row are one height, and the card, tile or
   expander in each column fills it, so the shorter side has no blank
   area under it. Content stays at the top, except the acquisition
   journey, which is centred when it is the shorter side. The space
   between rows is the one --cc-gap. */
:is(div[class*="st-key-cc_detail_"], div[class*="st-key-cc_eq_"])
  > [data-testid="stLayoutWrapper"]
  > [data-testid="stHorizontalBlock"] {align-items: stretch;}
:is(div[class*="st-key-cc_detail_"], div[class*="st-key-cc_eq_"])
  > [data-testid="stLayoutWrapper"]
  > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
  {display: flex; flex-direction: column;}
:is(div[class*="st-key-cc_detail_"], div[class*="st-key-cc_eq_"])
  > [data-testid="stLayoutWrapper"]
  > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
  > [data-testid="stVerticalBlock"] {flex: 1 1 auto;}
:is(div[class*="st-key-cc_detail_"], div[class*="st-key-cc_eq_"])
  > [data-testid="stLayoutWrapper"]
  > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
  > [data-testid="stVerticalBlock"] > *:only-child {flex: 1 1 auto;}
:is(div[class*="st-key-cc_detail_"], div[class*="st-key-cc_eq_"])
  > [data-testid="stLayoutWrapper"]
  > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
  > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]
  > div[class*="st-key-card_"] {height: 100%;}
.st-key-cc_detail_tiles [data-testid="stElementContainer"],
.st-key-cc_detail_tiles .stMarkdown, .st-key-cc_detail_tiles
  [data-testid="stMarkdownContainer"] {height: 100%; margin-bottom: 0;}
.st-key-cc_detail_tiles .stMarkdown > div {height: 100%;}
.st-key-cc_detail_tiles .cc-stat {height: 100%; margin-bottom: 0;}
.st-key-cc_detail_more [data-testid="stExpander"],
.st-key-cc_detail_more [data-testid="stExpander"] > details[open]
  {height: 100%;}
.st-key-cc_detail_more [data-testid="stExpander"] > details[open]
  {display: flex; flex-direction: column;}
.st-key-cc_detail_more [data-testid="stColumn"]:nth-child(2)
  [data-testid="stExpander"] > details[open] > [data-testid="stExpanderDetails"]
  {flex: 1 1 auto; display: flex; flex-direction: column;
   justify-content: center;}

/* Buttons. */
.stButton button[kind="primary"], .stDownloadButton button,
.stButton button {background: #254C31; color: #FFFFFF;
  border-color: #254C31;}
.stButton button:hover, .stDownloadButton button:hover
  {background: #1C3A25; color: #FFFFFF; border-color: #1C3A25;}

/* Labels: soft tint, coloured left border and dark text. */
.cc-pill {display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-weight: 600; font-size: var(--cc-small); color: #3B2F2A;
  white-space: nowrap; border-left: 3px solid;}
.cc-badge {display: inline-block; padding: 5px 12px; border-radius: 6px;
  font-weight: 600; font-size: var(--cc-badge); color: #3B2F2A;
  border-left: 5px solid;}
.cc-foot {color: #7A6B5F; font-size: var(--cc-foot); line-height: 1.35;}
.cc-take {font-size: var(--cc-text); color: #3B2F2A; margin: 0 0 8px;}
.cc-muted {color: #7A6B5F; font-size: var(--cc-small); line-height: 1.35;}

/* Tables. */
.cc-table {width: 100%; border-collapse: collapse;
  font-size: var(--cc-text); margin: 0 0 8px;}
.cc-table th {text-align: left; color: #7A6B5F; font-size: var(--cc-th);
  font-weight: 600;
  border-bottom: 1px solid #EADFCF; padding: 6px; background: #F3EADB;}
.cc-table td {border-bottom: 1px solid #EADFCF; padding: 6px;
  vertical-align: top; background: #FFFFFF; line-height: 1.35;}
.cc-table th {line-height: 1.35;}
.cc-table, .cc-table tr, .cc-table tr:nth-child(even) td
  {background: #FFFFFF;}
.cc-table {border: 1px solid #EADFCF;}
.stApp .cc-table th, .stApp .cc-table td {border-left: 0; border-right: 0;}
.cc-table .n {text-align: right; white-space: nowrap;}
.cc-scroll {overflow-x: auto; max-width: 100%;}
.stApp .cc-tight th, .stApp .cc-tight td {padding: 4px;}
.stApp .cc-table.cc-tight th {white-space: normal !important;
  vertical-align: bottom; text-transform: none; letter-spacing: 0;}
.cc-table .nw {white-space: nowrap;}
/* A small table (few columns, few rows) is as wide as its content. */
.stApp .cc-table.cc-narrow {width: auto; min-width: 360px;}
.cc-table .cc-key {font-size: var(--cc-t-cap); color: #7A6B5F;}
.cc-table .cmp {min-width: 7.5em;}
/* Narrower windows: the ranked table gets compact so it fits its
   card (the 2-column layout stays). */
@media (max-width: 1500px) {
  .stApp .cc-act th, .stApp .cc-act td {padding: 5px 4px;}
  .stApp .cc-act .cc-pill {padding: 2px 5px;}
}
/* Ranked table: the Action column gets about a third of the width
   and wraps; headers may wrap so the other columns can be narrower.
   Header text follows its column (numbers right, text left); every
   cell sits at the top of its row. The Final label pill never wraps
   ("Pause or review" stays on one line), so its column takes the
   width it needs. */
.stApp .cc-act th {white-space: normal; vertical-align: bottom;}
.stApp .cc-act td {vertical-align: top;}
.stApp .cc-act .lab, .stApp .cc-act .lab .cc-pill {white-space: nowrap;}
.cc-table .act {width: 32%; white-space: normal; overflow-wrap: anywhere;}
.cc-act-detail {font-size: var(--cc-small); color: #7A6B5F;
  margin-top: 2px; line-height: 1.35;}
.cc-table .cc-ended {color: #7A6B5F;}
/* Act row 1: both columns are one height, whether Not comparable is
   open or closed. The left card fills its column; in the right
   column the last block (Not comparable, or the chart card when
   there is none) grows. Inside the left card the picker row sits at
   the bottom, so any extra height falls between the hint and the
   picker, not under the buttons. */
.st-key-cc_act_row1 > [data-testid="stLayoutWrapper"]
  > [data-testid="stHorizontalBlock"] {align-items: stretch;}
.st-key-cc_act_row1 [data-testid="stHorizontalBlock"]
  > [data-testid="stColumn"] {display: flex; flex-direction: column;}
.st-key-cc_act_row1 [data-testid="stHorizontalBlock"]
  > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
  {flex: 1 0 auto;}
.st-key-cc_act_row1 [data-testid="stHorizontalBlock"]
  > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
  > :last-child {flex: 1 0 auto; display: flex; flex-direction: column;}
.st-key-cc_act_row1 [data-testid="stHorizontalBlock"]
  > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
  > :last-child > div[class*="st-key-card_"],
.st-key-cc_act_row1 [data-testid="stHorizontalBlock"]
  > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
  > :last-child > [data-testid="stExpander"]
  {flex: 1 0 auto; display: flex; flex-direction: column;}
.st-key-cc_act_row1 [data-testid="stExpander"] > details {flex: 1 0 auto;}
/* Room under the last Not comparable campaign (the markdown block's
   negative bottom margin would put the text on the border). */
.st-key-cc_act_row1 .cc-nc:last-child {padding-bottom: var(--cc-gap);}
.st-key-cc_act_row1 div[class*="st-key-card_"]
  > [data-testid="stLayoutWrapper"]:has(> .st-key-cc_act_picks)
  {margin-top: auto;}


/* Decision tiles. */
.cc-tiles {display: grid; grid-template-columns: repeat(4, 1fr);
  gap: var(--cc-gap); align-items: stretch;}
/* Equal height in the row comes from the grid (align-items:
   stretch), with no fixed minimum, so short tiles stay compact. */
.cc-tile {border-radius: 8px; padding: var(--cc-pad-y) var(--cc-pad-x);
  border-left: 5px solid; color: #3B2F2A;}
/* One campaign: bold name, then status and advice in the secondary
   colour (#6B5E54, 4.5:1 or more on the tints), a gap between. */
.cc-tile-camp {margin-top: 8px;}
.cc-tile-name {font-size: var(--cc-text); font-weight: 600;
  line-height: 1.35; color: #3B2F2A;}
.cc-tile-sub {font-size: var(--cc-small); font-weight: 400;
  line-height: 1.35; color: #6B5E54; margin-top: 1px;}
.cc-tile-more {font-size: var(--cc-small); color: #6B5E54; margin-top: 8px;}
@media (max-width: 900px) {.cc-tiles {grid-template-columns: 1fr 1fr;}}
/* Method: the four "How a label is decided" steps, white tiles like
   Running now on Act. */
.cc-step {background: #FFFFFF; border: 1px solid #D9CFC0;
  border-left: 5px solid #D9CFC0;}
.cc-step-text {font-size: var(--cc-t-body); line-height: 1.35;
  color: #3B2F2A; margin-top: 4px;}
/* The last step has the longest text: a little more width, so every
   step stays within two lines. */
.cc-steps {grid-template-columns: 1fr 1fr 1fr 1.3fr;}
@media (max-width: 900px) {.cc-steps {grid-template-columns: 1fr 1fr;}}

/* Context: recent-window rows, what-if tile, tags. */
.cc-tag {display: inline-block; border: 1px solid #3B2F2A;
  border-radius: 4px; padding: 0 6px; font-size: var(--cc-th);
  font-weight: 600; color: #3B2F2A; background: #FFFFFF;
  white-space: nowrap;}
.cc-big {background: #FBF6EE; border-radius: 8px;
  padding: calc(20px * var(--cc-pad-k)); text-align: center;}
.cc-big-n {font-size: var(--cc-num); font-weight: 600; line-height: 1.3;
  color: #254C31;}
.cc-rt {width: 100%; border-collapse: collapse; font-size: var(--cc-small);}
.cc-rt td {padding: 4px 6px; vertical-align: middle;
  border-bottom: 1px solid #EADFCF;}
.cc-bar {display: inline-block; height: 12px; vertical-align: middle;
  border-radius: 2px;}
</style>
"""


def _ckey(name):
    """A widget key per client.

    Streamlit keeps a keyed widget's value in the browser even when
    its options change, so after a client switch a picker could
    still show the other client's campaign. A key per client gives
    each client its own widget.
    """
    return f"{name}__{st.session_state.get('_client', '')}"


# The header's heading slot and brand (logo, or the wordmark), set
# by _header on every run; the slot is filled by the page's _heading.
_TOP = {"slot": None, "brand": ""}
WORDMARK = "<span class='cc-wordmark'>CampaignCompass</span>"


def _heading(page, question, ctx):
    """The heading row: one heading line ("CampaignCompass · <page>:"
    in 600 weight, then the question in 400 weight) with the data
    line under it at the left, and the brand (logo or wordmark) at
    the right edge. Without a logo the wordmark names the tool, so
    the heading is only "<page>: <question>". When the page runs
    alone (a page run without the header), the heading is shown
    where the page is, without a brand.
    """
    first, last = ctx["date_range"]
    line = dashboard_data.data_line((first, last), ctx["updated"])
    brand = _TOP["brand"]
    tool = ("" if brand == WORDMARK else
            "<span class='cc-tool'>CampaignCompass · </span>")
    title = (f"<div class='cc-title'>"
             f"<span class='cc-page'>{tool}{html.escape(page)}:</span> "
             f"<span class='cc-q'>{html.escape(question)}</span></div>")
    data = f"<div class='cc-data'>{html.escape(line)}</div>"
    if _TOP["slot"] is not None:
        _TOP["slot"].markdown(
            f"<div class='cc-head'>"
            f"<div class='cc-headtext'>{title}{data}</div>"
            f"<div class='cc-brand'>{brand}</div></div>",
            unsafe_allow_html=True)
    else:
        st.markdown(title + data, unsafe_allow_html=True)


def _caveat(ctx):
    """The caveat banner (on every page)."""
    st.info(dashboard_data.CAVEAT_TEXT, icon="ℹ️")


def _card_title(text):
    """A card's question title."""
    st.markdown(f"<p class='cc-card-title'>{html.escape(text)}</p>",
                unsafe_allow_html=True)


def _pill(label):
    """A label pill: tint, strong left border and text."""
    text = html.escape(dashboard_data.label_text(label) or "—")
    return (f"<span class='cc-pill' style='background:"
            f"{dashboard_data.label_tint(label)};border-color:"
            f"{dashboard_data.label_colour(label)}'>{text}</span>")


_BOX_COUNT = [0]


def _box(parent):
    """A white bordered card. The key ("card_<n>") gives it a CSS
    class, since a bordered container has no attribute of its own."""
    _BOX_COUNT[0] += 1
    return parent.container(border=True, key=f"card_{_BOX_COUNT[0]}")


def _badge(label):
    """A large label badge: tint, strong left border and text."""
    text = html.escape(dashboard_data.label_text(label) or "—")
    return (f"<span class='cc-badge' style='background:"
            f"{dashboard_data.label_tint(label)};border-color:"
            f"{dashboard_data.label_colour(label)}'>{text}</span>")


def _footnotes(lines, columns=False):
    """Small grey footnotes; columns: two columns where wide enough."""
    items = "".join(f"<li>{line}</li>" for line in lines)
    cls = "cc-foot cc-foot-2" if columns else "cc-foot"
    st.markdown(f"<div class='{cls}'><ul>{items}</ul></div>",
                unsafe_allow_html=True)


def _open_detail(campaign):
    """Drill-through: open the Campaign detail page on a campaign."""
    st.session_state[_ckey(DETAIL_KEY)] = campaign
    st.switch_page(PAGE_OBJECTS["Campaign detail"])


def _html_table(table, column_config=None, formats=None, muted=(),
                narrow=False):
    """A table as escaped HTML that fits its card.

    Headers wrap, every column stays visible (a horizontal scroll
    only as a last resort), missing values show as "—" and numbers
    are rounded for display only (data.display_value). Labels and
    formats come from column_config when given; formats maps a
    column to a printf pattern ("%.1f"). Columns in muted are small
    and grey (for example a raw config key).
    """
    config = dict(column_config or {})
    for column, pattern in (formats or {}).items():
        cfg = dict(config.get(column) or {})
        cfg["type_config"] = {"format": pattern}
        config[column] = cfg
    columns = list(table.columns)
    labels, patterns, numeric = [], [], []
    for column in columns:
        cfg = config.get(column) or {}
        labels.append(cfg.get("label") or str(column).replace("_", " "))
        patterns.append((cfg.get("type_config") or {}).get("format"))
        numeric.append(pd.api.types.is_numeric_dtype(table[column])
                       and not pd.api.types.is_bool_dtype(table[column]))
    head = "".join(
        f"<th{' class=n' if is_number else ''}>{html.escape(label)}</th>"
        for label, is_number in zip(labels, numeric))
    body = []
    for row in table.itertuples(index=False, name=None):
        cells = "".join(
            f"<td{' class=n' if is_number else ''}"
            f"{' class=cc-key' if column in muted else ''}>"
            f"{html.escape(dashboard_data.display_value(column, value, pattern))}"
            "</td>"
            for column, value, pattern, is_number in zip(
                columns, row, patterns, numeric))
        body.append(f"<tr>{cells}</tr>")
    extra = " cc-narrow" if narrow else ""
    return (f"<div class='cc-scroll'><table class='cc-table cc-tight{extra}'>"
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


def _table(table, file_name=None, column_config=None, key=None,
           height="auto", hide=(), display=None, formats=None, muted=(),
           narrow=False):
    """A table as escaped HTML, with a CSV download of the raw table.

    The download is the table's raw values (no display rounding) and
    all its columns; hide only leaves columns out of the display (for
    example a campaign name already shown on the page). display, when
    given, is the table shown instead (plain headers and values from
    a data.*_display helper); the download stays the raw table.
    """
    source = display if display is not None else table
    shown = source.drop(columns=[column for column in hide
                                 if column in source.columns]) \
        if source is not None else source
    # Group keys shown by their display names; the download keeps keys.
    shown = dashboard_data.with_group_names(
        shown, _CTX.get("group_names") or {}, _CTX.get("journey_pool"))
    # Label and flag keys shown by their readable names; same reason.
    shown = dashboard_data.readable_keys(shown)
    if shown is None or shown.empty:
        st.caption("No rows.")
    else:
        st.markdown(_html_table(shown, column_config, formats, muted,
                                narrow), unsafe_allow_html=True)
    if file_name:
        st.download_button(
            "Download CSV", dashboard_data.csv_bytes(table),
            file_name=file_name, mime="text/csv",
            key=key or f"download_{file_name}")


# --- Act ----------------------------------------------------------

def _fmt(value, pattern):
    """A formatted number, or an em dash for a missing one."""
    if value is None or pd.isna(value):
        return "—"
    return pattern.format(value)


def _action_html(table):
    """The ranked action table as HTML.

    Numeric columns (#, Ratio, Tracked actions) are right-aligned,
    text columns left-aligned; every cell sits at the top of its
    row. The label cell is a pill that never wraps. Status: "Ended"
    in the secondary colour. Trend: "—" when not active, "Worsening"
    in bold. Action: the headline (up to the first "; ") on line 1,
    the detail smaller and grey on line 2. The label period is
    written "31 May – 13 Jul 2026". All of it is display only.
    """
    head = ("<tr><th class='n'>#</th><th>Campaign</th>"
            "<th class='lab'>Final label</th>"
            "<th>Status</th><th class='n'>Ratio</th>"
            "<th class='n'>Tracked actions</th><th>Trend</th>"
            "<th class='act'>Action</th><th>Label period</th></tr>")
    body = []
    for _, row in table.iterrows():
        headline, detail = dashboard_data.split_action(row["action"])
        action = html.escape(headline or "—")
        if detail:
            action += (f"<div class='cc-act-detail'>{html.escape(detail)}"
                       "</div>")
        status = dashboard_data.status_text(row["status_now"])
        status_cls = " class='cc-ended'" if status == "Ended" else ""
        trend = html.escape(dashboard_data.trend_text(row["recent_trend"]))
        if trend == "Worsening":
            trend = f"<b>{trend}</b>"
        period = _period_html(dashboard_data.period_text(
            row["label_period"]))
        body.append(
            "<tr>"
            f"<td class='n'>{int(row['rank'])}</td>"
            f"<td class='cmp'><b>{html.escape(str(row['campaign']))}</b></td>"
            f"<td class='lab'>{_pill(row['label'])}</td>"
            f"<td{status_cls}>{html.escape(status)}</td>"
            f"<td class='n'>{_fmt(row['ratio_to_benchmark'], '{:.2f}x')}</td>"
            f"<td class='n'>{_fmt(row['tracked_actions'], '{:,.0f}')}</td>"
            f"<td>{trend}</td>"
            f"<td class='act'>{action}</td>"
            f"<td class='per'>{period}</td>"
            "</tr>")
    return (f"<div class='cc-scroll'><table class='cc-table cc-act'>"
            f"<thead>{head}</thead><tbody>{''.join(body)}</tbody>"
            "</table></div>")


def _period_html(text):
    """A formatted period that may break only after its en dash
    ("31 May –" / "13 Jul 2026" on a narrow screen), never inside a
    date. "—" when there is no period."""
    if not text:
        return "—"
    first, sep, last = text.partition(" – ")
    if not sep:
        return f"<span class='nw'>{html.escape(text)}</span>"
    return (f"<span class='nw'>{html.escape(first)} –</span> "
            f"<span class='nw'>{html.escape(last)}</span>")


def _readable(value, keep=False):
    """Text for a cell: empty for missing; underscores to spaces."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "—"
    return str(value) if keep else str(value).replace("_", " ")




def _act_definitions(ctx, kpi):
    """The "How to read this" bullets, lead term in bold."""
    lines = dashboard_data.how_to_read_lines(
        ctx["config"], kpi, ctx["group_names"], ctx["all_recommendations"],
        ctx["tables"]["benchmarks"], ctx["currency"])
    return [(f"<b>{html.escape(lead)}</b>: " if lead else "")
            + html.escape(text) for lead, text in lines]


def _tile_line(line, with_label=False):
    """One campaign in a tile: the name in bold, then a smaller
    secondary line with status (or label) and advice."""
    detail = dashboard_data.tile_detail(line, with_label=with_label)
    sub = (f"<div class='cc-tile-sub'>{html.escape(detail)}</div>"
           if detail else "")
    return (f"<div class='cc-tile-camp'><div class='cc-tile-name'>"
            f"{html.escape(line['campaign'])}</div>{sub}</div>")


def _tile_title(text, count):
    """A tile's title line, in the card-title style."""
    return (f"<div class='cc-card-title'>"
            f"{html.escape(dashboard_data.tile_title(text, count))}</div>")


def _tiles_html(summary):
    """The four decision tiles: three labels, then Running now."""
    tiles = []
    for tile in summary["tiles"]:
        label = tile["label"]
        lines = "".join(_tile_line(line) for line in tile["lines"])
        if tile["more"]:
            lines += (f"<div class='cc-tile-more'>+{tile['more']} more, "
                      "see the table</div>")
        tiles.append(
            "<div class='cc-tile' style='background:"
            f"{dashboard_data.label_tint(label)};border-left-color:"
            f"{dashboard_data.label_colour(label)}'>"
            + _tile_title(dashboard_data.label_text(label), tile["count"])
            + f"{lines}</div>")
    running = summary["running"]
    lines = "".join(_tile_line(line, with_label=True) for line in running)
    if not running:
        lines = "<div class='cc-tile-more'>No campaign is active.</div>"
    tiles.append(
        "<div class='cc-tile' style='background:#FFFFFF;"
        "border:1px solid #D9CFC0;border-left:5px solid #D9CFC0'>"
        + _tile_title("Running now", len(running)) + f"{lines}</div>")
    return f"<div class='cc-tiles'>{''.join(tiles)}</div>"


def _totals_strip_html(kpi, currency):
    """The slim totals strip: one white bar, four items (name, value,
    one caption) with thin dividers. Values from benchmarks.csv; the
    filters never change them."""
    items = "".join(
        f"<div class='cc-tot'><div class='cc-tot-l'>{html.escape(name)}"
        f"</div><div class='cc-tot-v'>{html.escape(value)}</div>"
        f"<div class='cc-tot-c'>{html.escape(caption)}</div></div>"
        for name, value, caption in
        dashboard_data.totals_strip_items(kpi, currency))
    return f"<div class='cc-totals'>{items}</div>"


def _not_comparable(ctx):
    """The Not comparable card (an expander) under the chart, or
    nothing when the client has no not-comparable campaign."""
    kpi = dashboard_data.kpi_values(ctx["tables"]["benchmarks"])
    lines = dashboard_data.not_comparable_lines(
        ctx["all_recommendations"], ctx["group_names"], kpi["benchmark"],
        ctx["currency"])
    if not lines:
        return
    with st.expander(f"Not comparable ({len(lines)})"):
        items = "".join(
            f"<div class='cc-nc'><div class='cc-tile-name'>"
            f"{html.escape(line['name'])}</div>"
            f"<div class='cc-nc-sub'>{html.escape(line['sub'])}</div>"
            f"<div class='cc-nc-sub'>{html.escape(line['cost'])}</div></div>"
            for line in lines)
        st.markdown(
            f"<p class='cc-take'>"
            f"{html.escape(dashboard_data.NOT_COMPARABLE_INTRO)}</p>{items}",
            unsafe_allow_html=True)


def _page_act(ctx):
    """Which campaigns should we continue, test or pause?"""
    _heading("Act", "Which campaigns should we continue, test or pause?",
             ctx)
    tables = ctx["tables"]
    currency = ctx["currency"]
    recs = ctx["all_recommendations"]

    # Filters: display only, they hide table rows and bars. Their
    # labels match the card titles (18px, weight 600).
    with st.container(key="cc_filters"):
        filters = st.columns(3)
        # Options are the group keys (the filter matches on them);
        # each is shown by its display name.
        names = ctx["group_names"]
        group = filters[0].selectbox(
            "Campaign group", dashboard_data.group_options(recs),
            format_func=lambda key: names.get(key, key),
            key=_ckey("act_group"))
        status = filters[1].selectbox(
            "Status now", dashboard_data.status_options(recs),
            key=_ckey("act_status"))
        min_actions = filters[2].number_input(
            "Minimum tracked actions", min_value=0, value=0, step=10,
            key="act_min_actions",
            help="Display filter only: hides campaigns with fewer tracked "
                 "actions in their label period. Labels do not change.")
    view = dashboard_data.filter_view(recs, group, status, min_actions)

    # Decision tiles: all campaigns, never filtered.
    st.markdown(_tiles_html(dashboard_data.act_summary(recs)),
                unsafe_allow_html=True)

    # Totals strip: all campaigns in the totals, never filtered.
    kpi = dashboard_data.kpi_values(tables["benchmarks"])
    st.markdown(_totals_strip_html(kpi, currency), unsafe_allow_html=True)

    # Row 1: the table (left); the chart with Not comparable under it.
    table = dashboard_data.action_table(view, tables["recent_trend"])
    left, right = st.container(key="cc_act_row1").columns([1.85, 1])
    with _box(left):
        show_hidden = st.checkbox(
            "Also show insufficient data / not judged campaigns",
            value=False, key="act_show_hidden")
        if not show_hidden:
            table = table.loc[table["label"].isin(
                dashboard_data.JUDGED_LABELS)].reset_index(drop=True)
        if table.empty:
            st.info("No campaign matches the filters.")
        else:
            st.markdown(_action_html(table), unsafe_allow_html=True)
            st.caption("Sorted by decision: Pause or review, then Test, "
                       "then Continue; the highest ratio first within "
                       "each. \"—\" = no recent trend (the campaign is "
                       "not active).")
            # The picker row sits at the bottom of the card (see STYLE).
            picks = st.container(key="cc_act_picks").columns(
                [3, 1, 1], vertical_alignment="bottom")
            campaign = picks[0].selectbox(
                "Campaign", list(table["campaign"]), key=_ckey("act_pick"))
            if picks[1].button("Open detail", type="primary",
                               key="act_open", width="stretch"):
                _open_detail(campaign)
            picks[2].download_button(
                "Download CSV",
                dashboard_data.csv_bytes(table.drop(columns=["label"])),
                file_name="actions.csv", mime="text/csv",
                key="act_download", width="stretch")
    with right:
        with _box(st):
            _card_title("Ratio to benchmark (cost per tracked action)")
            bars = dashboard_data.ratio_bar_rows(table, recs,
                                                 cap=charts.RATIO_CAP)
            if bars.empty:
                st.info("No judged campaign with a ratio matches the "
                        "filters.")
            else:
                lines = dashboard_data.reference_lines(
                    ctx["config"], kpi["benchmark"])
                st.plotly_chart(charts.ratio_bar(bars, lines, currency),
                                width="stretch", key="act_ratio",
                                config={"displayModeBar": False})
                st.caption(dashboard_data.ratio_note(lines, bars))
        _not_comparable(ctx)

    # Row 2: how to read this, full width.
    with st.expander("How to read this"):
        _footnotes(_act_definitions(ctx, kpi), columns=True)


# --- Context ------------------------------------------------------

def _takeaway(text):
    """The one-sentence takeaway under a card's question."""
    st.markdown(f"<p class='cc-take'>{html.escape(text)}</p>",
                unsafe_allow_html=True)


def _money(value, currency):
    return _fmt(value, "{:,.2f}") + (f" {currency}"
                                     if value is not None
                                     and not pd.isna(value) else "")


def _recent_html(rows, currency):
    """Prior vs recent window per active campaign, as small bars.

    Bar lengths are relative to the largest value shown. A rise, as
    judged by the pipeline (recent_trend "worsening"), gets a warning
    tag; label colours are never used here.
    """
    values = pd.concat([rows["prior_cost_per_tracked_action"],
                        rows["recent_cost_per_tracked_action"]])
    top = float(values.max()) if values.notna().any() else 0.0
    out = []
    for _, row in rows.iterrows():
        def bar(value, colour):
            if top <= 0 or value is None or pd.isna(value):
                return ""
            width = max(2.0, 100.0 * float(value) / top)
            return (f"<span class='cc-bar' style='width:{width:.0f}px;"
                    f"background:{colour}'></span>")
        ratio = row["recent_vs_prior_ratio"]
        trend = dashboard_data.value_text(row["recent_trend"])
        if str(row["recent_trend"]) == "worsening":
            flag = f"<span class='cc-tag'>⚠ {html.escape(trend)}</span>"
        else:
            flag = f"<span class='cc-muted'>{html.escape(trend)}</span>"
        out.append(
            "<tr>"
            f"<td rowspan='2' style='width:30%'><b>"
            f"{html.escape(str(row['campaign']))}</b></td>"
            f"<td>Prior window<br><span class='cc-muted'>"
            f"{html.escape(dashboard_data.period_text(row['prior_window']) or '—')}"
            "</span></td>"
            f"<td class='nw'>{bar(row['prior_cost_per_tracked_action'], charts.NEUTRAL_LIGHT)} "
            f"{html.escape(_money(row['prior_cost_per_tracked_action'], currency))}</td>"
            f"<td rowspan='2' class='nw' style='text-align:right'>"
            f"<span class='cc-muted'>Recent / prior</span><br>"
            f"<span style='font-size:var(--cc-t-value);font-weight:600;"
            f"color:#254C31'>"
            f"{_fmt(ratio, '{:.2f}x')}</span><br>{flag}</td></tr>"
            "<tr>"
            f"<td>Recent window<br><span class='cc-muted'>"
            f"{html.escape(dashboard_data.period_text(row['recent_window']) or '—')}"
            "</span></td>"
            f"<td class='nw'>{bar(row['recent_cost_per_tracked_action'], charts.NEUTRAL)} "
            f"{html.escape(_money(row['recent_cost_per_tracked_action'], currency))}</td>"
            "</tr>")
    return f"<table class='cc-rt'>{''.join(out)}</table>"


def _trend_campaign(ctx, key="ctx_trend_campaign"):
    """The campaign for the monthly trend: first active, or chosen.

    The pick is remembered in a plain session key, so the Method
    page's picker starts on the campaign last picked on Context.
    """
    tables = ctx["tables"]
    campaigns = sorted(set(tables["timeline_by_campaign"]["campaign"]))
    if not campaigns:
        return None
    rows = dashboard_data.recent_trend_rows(
        tables["recent_trend"], ctx["all_recommendations"])
    active = [name for name in rows["campaign"] if name in campaigns]
    default = active[0] if active else campaigns[0]
    remembered = st.session_state.get(_ckey("_trend_pick"))
    if remembered in campaigns:
        default = remembered
    picked = st.selectbox("Campaign for the monthly trend", campaigns,
                          index=campaigns.index(default), key=_ckey(key))
    st.session_state[_ckey("_trend_pick")] = picked
    return picked


def _card_recent(ctx):
    """(a) Has performance changed recently?"""
    tables = ctx["tables"]
    currency = ctx["currency"]
    _card_title("Has performance changed recently?")
    rows = dashboard_data.recent_trend_rows(
        tables["recent_trend"], ctx["all_recommendations"])
    _takeaway(dashboard_data.trend_takeaway(rows))
    if not rows.empty:
        shown, more = dashboard_data.recent_rows_capped(rows, 5)
        st.markdown(_recent_html(shown, currency), unsafe_allow_html=True)
        if more:
            st.caption(f"+{more} more, see the recent trend table.")
    campaign = _trend_campaign(ctx)
    if campaign is not None:
        table = dashboard_data.trend_with_flags(
            tables["timeline_by_campaign"], campaign)
        st.plotly_chart(charts.trend_line(table, "month", None,
                                          currency, height=280),
                        width="stretch", key="ctx_trend_chart")
        st.caption("Monthly cost per tracked action. Hollow ring = "
                   "partial month (the campaign ran only part of it) or "
                   "lagged month (days still being reported). Do not "
                   "read a jump in those months as a change.")
    if not rows.empty:
        with st.expander("Recent trend table"):
            raw = rows.drop(columns=["recent_tracked_actions"])
            _table(raw, "recent_trend.csv", key="ctx_recent",
                   display=dashboard_data.recent_rows_display(raw),
                   column_config={
                       "campaign": WIDE("Campaign", pinned=True),
                       "final_label": WIDE("Final label"),
                       "recent_trend": WIDE("Trend"),
                       "recent_window": WIDE("Recent window"),
                       "recent_cost_per_tracked_action": NUM(
                           f"Recent ({currency})", format="%.2f"),
                       "prior_window": WIDE("Prior window"),
                       "prior_cost_per_tracked_action": NUM(
                           f"Prior ({currency})", format="%.2f"),
                       "recent_vs_prior_ratio": NUM(
                           "Recent / prior", format="%.2fx"),
                   })
    return campaign


def _weekday_parts(ctx):
    """(pooled weekday table or None, what-if rows, what-if range)."""
    tables = ctx["tables"]
    try:
        pooled = dashboard_data.weekday_core_table(tables["weekday_core"])
    except ValueError as exc:
        st.error(str(exc))
        pooled = None
    rows, span = dashboard_data.what_if_parts(
        tables["what_if_weekday_shift"])
    return pooled, rows, span


def _card_weekday(ctx, pooled):
    """(b) Do weekdays differ?"""
    currency = ctx["currency"]
    _card_title("Do weekdays differ?")
    if pooled is None:
        return
    _takeaway(dashboard_data.weekday_takeaway(pooled, currency))
    busiest = dashboard_data.most_clicks_weekday(pooled)
    st.plotly_chart(charts.weekday_bar(pooled, currency,
                                       highlight=busiest,
                                       note="most pooled clicks"),
                    width="stretch", key="ctx_weekday_chart",
                    config={"displayModeBar": False})
    outline = dashboard_data.weekday_outline_text(pooled)
    if outline:
        st.caption(f"{outline} Pooled over the campaign groups.")
    with st.expander("Pooled weekday table"):
        _table(pooled, "weekday_pooled.csv", key="ctx_weekday_pooled",
               display=dashboard_data.pooled_weekday_display(
                   pooled, currency),
               formats=dashboard_data.POOLED_WEEKDAY_FORMATS)


def _card_what_if(ctx, rows, span):
    """(c) What would moving spend do?"""
    currency = ctx["currency"]
    _card_title("What would moving spend do?")

    def first(column):
        if column in rows.columns and not rows.empty:
            return rows[column].iloc[0]
        return None

    change = span["display"] if span is not None else first("display")
    scenario = (span or {}).get("scenario") or first("scenario")
    if change is None or (not isinstance(change, str) and pd.isna(change)):
        st.info("No what-if rows for this client.")
        return
    change = str(change)
    head, _, tail = change.partition(" (")
    sub = f"({tail}" if tail else ""
    st.markdown(
        "<div class='cc-big'><div class='cc-big-n'>"
        f"{html.escape(head)}</div>"
        + (f"<div style='font-size:var(--cc-t-body)'>{html.escape(sub)}</div>"
           if sub else "") + "</div>", unsafe_allow_html=True)
    if scenario and not pd.isna(scenario):
        st.markdown(f"<p class='cc-take' style='margin-top:12px'>"
                    f"{html.escape(str(scenario))}.</p>",
                    unsafe_allow_html=True)
    st.markdown(f"<p class='cc-take'>"
                f"{html.escape(dashboard_data.what_if_note(currency))}</p>",
                unsafe_allow_html=True)
    with st.expander("What-if by variant"):
        _what_if(rows, None, currency)


def _card_journey(ctx):
    """(d) How do people reach the restaurant?"""
    tables = ctx["tables"]
    _card_title("How do people reach the restaurant?")
    journey_raw = tables["journey_by_campaign"]
    _takeaway(dashboard_data.journey_takeaway(journey_raw))
    long = dashboard_data.journey_intent_long(journey_raw)
    if long.empty:
        st.caption("No journey rows.")
    else:
        st.plotly_chart(charts.intent_stack(long), width="stretch",
                        key="ctx_journey_chart")


def _journey_tables(ctx, expanded=False):
    """Journey table and break-even, full width (too many columns
    for a half-width card)."""
    tables = ctx["tables"]
    journey_raw = tables["journey_by_campaign"]
    currency = ctx["currency"]
    with st.expander("Journey table", expanded=expanded):
        st.caption(dashboard_data.JOURNEY_NOTE)
        _table(journey_raw, "journey.csv", key="ctx_journey",
               display=dashboard_data.journey_table_display(
                   dashboard_data.with_group_names(
                       journey_raw, ctx["group_names"],
                       ctx.get("journey_pool")), currency),
               formats=dashboard_data.journey_formats(currency))
    break_even = ctx["break_even"]
    if break_even is not None:
        with st.expander("Break-even (illustration: tracked actions are "
                         "not visits)"):
            _table(dashboard_data.display_table(break_even),
                   "break_even.csv", key="ctx_break_even", column_config={
                       "campaign": WIDE("Campaign", width="large",
                                        pinned=True),
                       "note": WIDE("Note", width="large")})


def _completeness(ctx, campaign):
    """Data completeness: lag check and the monthly trend table."""
    tables = ctx["tables"]
    config = ctx["config"]
    configured = (config.get("analysis", {}).get("recent_trend", {})
                  .get("conversion_lag_days"))
    lag_check = ctx["optional"]["lag_check"]
    if lag_check is None:
        st.info("The lag check is not turned on for this client "
                "(recent_trend.lag_check_days in its config).")
    else:
        summary = dashboard_data.lag_check_summary(lag_check)
        _takeaway(dashboard_data.lag_takeaway(summary, configured))
        st.markdown("**Lag check**")
        st.caption("Tracked actions can arrive days late. The lag check "
                   "reruns the recent signals with other lags and counts "
                   "what changes.")
        _table(summary, "lag_check_summary.csv", key="ctx_lag", narrow=True,
               column_config={
                   "lag": NUM("Lag (days)", format="%d"),
                   "trend_changes": NUM("Trend changes", format="%d"),
                   "label_changes": NUM("Label changes", format="%d")})
        with st.expander("All lag-check counts"):
            _table(lag_check, "lag_check.csv", key="ctx_lag_all")
    if campaign is not None:
        st.markdown(f"**Monthly trend: {campaign}**")
        st.caption("Month note: partial (the campaign ran only part of "
                   "the month) or lagged (days still being reported).")
        table = dashboard_data.trend_with_flags(
            tables["timeline_by_campaign"], campaign)
        _table(table, f"monthly_{campaign}.csv", key="ctx_month_table",
               display=dashboard_data.month_table_display(
                   table, ctx["currency"]),
               formats=dashboard_data.TREND_TABLE_FORMATS)


def _distorting(ctx):
    """Is one campaign distorting a weekday? (inside an expander)."""
    optional = ctx["optional"]
    mix = optional["weekday_mix_by_campaign"]
    loo = optional["weekday_leave_one_out"]
    top = optional["weekday_top_days"]
    focus = (top["weekday"].iloc[0]
             if top is not None and not top.empty else None)
    full = {day[:3]: day for day in dashboard_data.WEEKDAYS}
    label = full.get(focus, focus) if focus else "one weekday"
    with st.expander(f"Is one campaign distorting {label}?"):
        if mix is None or loo is None:
            st.info("This analysis is not switched on for this client.")
        else:
            _weekday_breakdown(
                mix, loo, top, focus,
                dashboard_data.baseline_label(ctx["config"]))


def _weekday_breakdown(mix, loo, top, focus, baseline="Mon-Thu"):
    """Who makes up one weekday, and the weekday with each left out.

    The picker shows full weekday names; its values stay the short
    names the tables use."""
    short = [day[:3] for day in dashboard_data.WEEKDAYS
             if day[:3] in set(mix["weekday"])]
    weekday = st.selectbox(
        "Weekday to break down", short,
        index=short.index(focus) if focus in short else 0,
        format_func=dashboard_data.full_weekday,
        key=_ckey("ctx_weekday"),
        help="Default: the weekday with the most pooled clicks")
    name = dashboard_data.full_weekday(weekday)
    loo_table = dashboard_data.leave_one_out_for_weekday(loo, weekday)
    takeaway = dashboard_data.leave_one_out_takeaway(
        loo_table, weekday, baseline)
    if takeaway:
        _takeaway(takeaway)
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown(f"**Who makes up {name}?**")
        share = dashboard_data.weekday_focus_table(mix, weekday)
        st.plotly_chart(charts.share_bar(share, name), width="stretch",
                        key="ctx_share_chart",
                        config={"displayModeBar": False})
    with right:
        st.markdown(f"**{name} with one campaign left out**")
        st.caption(f"Closest to the {baseline} baseline first: that "
                   f"campaign explains most of the weekday's difference.")
        loo_columns = [column for column in (
            "left_out", "actions_per_click_vs_baseline",
            "actions_per_click", "clicks") if column in loo_table]
        _table(loo_table[loo_columns],
               f"weekday_leave_one_out_{weekday}.csv", key="ctx_loo",
               display=dashboard_data.leave_one_out_display(
                   loo_table[loo_columns]),
               column_config={
                   "left_out": WIDE("Left out", pinned=True),
                   "actions_per_click_vs_baseline": NUM(
                       f"vs {baseline}", format="%.2fx"),
                   "actions_per_click": NUM("Tracked actions per click",
                                            format="%.3f"),
                   "clicks": NUM("Clicks", format="%.0f")})
    if top is not None and not top.empty:
        top_weekday = top["weekday"].iloc[0]
        top_name = dashboard_data.full_weekday(top_weekday)
        st.markdown(f"**Top {len(top)} {top_name}s by pooled clicks** "
                    f"(together {top['share_of_weekday_clicks'].sum():.1%}"
                    f" of {top_name} clicks)")
        _table(top, "weekday_top_days.csv", key="ctx_top",
               display=dashboard_data.top_days_display(top, top_weekday),
               formats=dashboard_data.top_days_formats(top_weekday))


def _what_if(rows, span, currency):
    """Moving weekday spend to the weekend, per variant of the groups."""
    if span is not None:
        with _box(st):
            st.metric("Change in tracked actions, range across variants",
                      span["display"])
    columns = [column for column in (
        "groups", "scenario", "spend_moved",
        "tracked_actions_before", "tracked_actions_after", "display")
        if column in rows.columns]
    shown = rows[columns].copy()
    for column in ("spend_moved", "tracked_actions_before",
                   "tracked_actions_after"):
        if column in shown.columns:
            shown[column] = shown[column].round(0)
    _table(shown, "what_if.csv", key="ctx_what_if", column_config={
        "groups": WIDE("Groups"),
        "scenario": WIDE("Scenario"),
        "spend_moved": NUM(f"Spend moved ({currency})", format="%.0f"),
        "tracked_actions_before": NUM("Actions before", format="%.0f"),
        "tracked_actions_after": NUM("Actions after", format="%.0f"),
        "display": WIDE("Change")})


def _label_steps(ctx):
    """"How a label is decided": four numbered step cards (Act tile
    style), texts from data.label_steps (config and benchmarks)."""
    kpi = dashboard_data.kpi_values(ctx["tables"]["benchmarks"])
    steps = dashboard_data.label_steps(
        ctx["config"], kpi, ctx["group_names"], ctx["currency"],
        ctx["tables"]["benchmarks"])
    cards = "".join(
        f"<div class='cc-tile cc-step'><div class='cc-card-title'>"
        f"{number}. {html.escape(title)}</div>"
        f"<div class='cc-step-text'>{html.escape(text)}</div></div>"
        for number, (title, text) in enumerate(steps, start=1))
    st.markdown("<p class='cc-card-title'>How a label is decided</p>"
                f"<div class='cc-tiles cc-steps'>{cards}</div>",
                unsafe_allow_html=True)


def _method_definitions(ctx, expanded=False):
    """Benchmarks and the threshold check, in an expander."""
    tables = ctx["tables"]
    with st.expander("Method and definitions", expanded=expanded):
        st.markdown("**Benchmarks**")
        benchmarks = tables["benchmarks"]
        _table(benchmarks, "benchmarks.csv", key="ctx_benchmarks",
               display=dashboard_data.benchmarks_display(
                   benchmarks, ctx["group_names"], ctx["currency"]),
               formats=dashboard_data.BENCHMARK_FORMATS)
        st.caption(dashboard_data.BENCHMARK_NOTE)

        st.markdown("**Do the labels hold if the thresholds move?**")
        sensitivity = tables["recommendation_sensitivity"]
        stable = sensitivity.drop_duplicates("campaign")["label_stable"]
        st.caption(f"{int(stable.sum())} of {len(stable)} campaigns keep "
                   f"the same label in every threshold combination "
                   f"(labels before the trend override).")
        unstable = sensitivity[~sensitivity["label_stable"].astype(bool)]
        if not unstable.empty:
            moving = unstable["campaign"].nunique()
            _takeaway(f"{moving} campaign{'s' if moving != 1 else ''} "
                      f"change{'' if moving != 1 else 's'} label in some "
                      f"threshold combination.")
            with st.expander("Labels that move"):
                _table(unstable, None, key="ctx_sensitivity_unstable",
                       display=dashboard_data.sensitivity_display(
                           unstable, ctx["group_names"]),
                       formats=dashboard_data.SENSITIVITY_FORMATS)
        with st.expander(f"Show all {len(sensitivity)} rows"):
            _table(sensitivity, "recommendation_sensitivity.csv",
                   key="ctx_sensitivity",
                   display=dashboard_data.sensitivity_display(
                       sensitivity, ctx["group_names"]),
                   formats=dashboard_data.SENSITIVITY_FORMATS)



def _settings(ctx, expanded=False):
    """The volume rule and thresholds from the config (collapsed)."""
    config = ctx["config"]
    with st.expander("Settings", expanded=expanded):
        _table(dashboard_data.rules_table(config, ctx["group_names"]),
               "rules.csv", key="ctx_rules",
               display=dashboard_data.settings_display(
                   config, ctx["group_names"]),
               muted=("Key",))


def _what_counts(ctx, expanded=False):
    """What counts as a tracked action: the action table, its scope
    and the engagement share."""
    tables = ctx["tables"]
    with st.expander("What counts as a tracked action", expanded=expanded):
        mix = tables["conversion_mix_by_campaign"]
        shares = dashboard_data.conversion_shares(mix)
        raw = shares[["action", "action_group", "tracked_actions",
                      "share_pct"]].copy()
        raw.columns = ["Action", "Action group", "Tracked actions",
                       "Share of tracked actions (%)"]
        display = raw.copy()
        display["Action group"] = display["Action group"].map(
            lambda g: dashboard_data.ACTION_GROUP_TEXT.get(g, g))
        st.caption(dashboard_data.what_counts_caption(
            mix, ctx["optional"].get("conversion_mix_by_campaign_month")))
        show_zero = st.checkbox("Show zero rows", value=False,
                                key="ctx_conversion_zero")
        if not show_zero:
            display = display.loc[display["Tracked actions"] != 0]
        _table(raw, "tracked_actions_by_action.csv",
               key="ctx_conversion", display=display,
               column_config={"Action": WIDE("Action", width="large")})
        st.caption(
            "Engagement actions (menu views, website visits, other "
            "engagements) are "
            f"{dashboard_data.engagement_share_all(mix):.2%} of all tracked "
            "and engagement actions but are not counted as tracked "
            "actions.")


def _page_context(ctx):
    """Can we trust these labels, and when should we run campaigns?

    A 2x2 grid of cards, each a question, a takeaway and a chart;
    then the weekday breakdown. Data completeness, the journey table
    and the method are on the Method page.
    """
    _heading("Context", "Can we trust these labels, and when should we "
             "run campaigns?", ctx)
    pooled, rows, span = _weekday_parts(ctx)
    top = st.container(key="cc_eq_ctx_top").columns(2)
    with _box(top[0]):
        _card_recent(ctx)
    with _box(top[1]):
        _card_weekday(ctx, pooled)
    bottom = st.container(key="cc_eq_ctx_bottom").columns(2)
    with _box(bottom[0]):
        _card_what_if(ctx, rows, span)
    with _box(bottom[1]):
        _card_journey(ctx)
    _distorting(ctx)


def _page_method(ctx):
    """How were these labels built?

    Logic first, tables second: how a label is decided (four steps),
    then the method and definitions, what counts as a tracked action,
    the settings (collapsed), data completeness (lag check, monthly
    trend) and the journey table (and break-even). The monthly trend
    has its own campaign picker here; it starts on the campaign last
    picked on Context.
    """
    _heading("Method", "How were these labels built?", ctx)
    _label_steps(ctx)
    _method_definitions(ctx, expanded=True)
    _what_counts(ctx, expanded=True)
    _settings(ctx)
    with st.expander("Data completeness (lag check, monthly trend)",
                     expanded=True):
        campaign = _trend_campaign(ctx, key="method_trend_campaign")
        _completeness(ctx, campaign)
    _journey_tables(ctx, expanded=True)


# --- Campaign detail ----------------------------------------------

def _period_slider(values, label, key, default=None):
    """A from-to slider over the sorted periods; returns (start, end).

    default is the (start, end) the slider opens on; without it the
    whole range is shown.
    """
    options = sorted(set(str(value) for value in values))
    if len(options) < 2:
        return None, None
    value = default or (options[0], options[-1])
    return st.select_slider(label, options=options, value=value, key=key,
                            format_func=dashboard_data.period_label)


def _detail_trend(ctx, campaign):
    """Monthly or weekly cost per tracked action for one campaign.

    The period slider limits the rows shown (a filter, not a
    recalculation). Partial and lagged months are marked. Returns
    (view, rows shown, file key) for the table under the runs, or
    None when there are no rows.
    """
    tables = ctx["tables"]
    currency = ctx["currency"]
    view = st.radio("View", ["Monthly", "Weekly"], horizontal=True,
                    key="detail_view")
    if view == "Monthly":
        table = dashboard_data.trend_with_flags(
            tables["timeline_by_campaign"], campaign)
        x_field, key = "month", "month"
    else:
        table = dashboard_data.weekly_for_campaign(
            tables["weekly_by_campaign"], campaign)
        x_field, key = "week_start", "week"
    if table.empty:
        st.caption("No monthly or weekly rows: the trend tables cover "
                   "the time groups in the config.")
        return None
    default = None
    if view == "Monthly" and "source" in table.columns:
        # Open on the daily range, not the monthly-history range: the
        # history months are still there if the slider is widened.
        day_months = sorted(str(month) for month, source in
                            zip(table["month"], table["source"])
                            if source == "day")
        if len(day_months) >= 2:
            default = (day_months[0], day_months[-1])
    start, end = _period_slider(table[x_field], "Period",
                                f"detail_period_{key}", default=default)
    table = dashboard_data.filter_period(table, x_field, start, end)
    st.plotly_chart(charts.trend_line(
        table, x_field, None, currency,
        freq="MS" if x_field == "month" else "W-MON"),
        width="stretch", key=f"detail_trend_{key}")
    if "month_note" in table.columns:
        st.caption("Hollow ring = partial or lagged month.")
    history = dashboard_data.monthly_history_text(
        table, ctx["date_range"][0])
    if history:
        st.caption(history)
    return view, table, key


def _trend_table(trend, campaign):
    """The monthly or weekly table of the trend card ("Monthly
    figures"), in a collapsed expander under the runs."""
    if trend is None:
        return
    view, table, key = trend
    currency = _CTX.get("currency", "SEK")
    shown = (dashboard_data.month_table_display(table, currency)
             if key == "month" else
             dashboard_data.week_table_display(table, currency))
    with st.expander(f"{view} figures"):
        _table(table, f"{key}ly_{campaign}.csv",
               key=f"detail_trend_table_{key}", display=shown,
               formats=dashboard_data.TREND_TABLE_FORMATS)


def _stat_tile(column, title, value_html, caption=""):
    """A detail-page tile: title, large value, optional caption."""
    caption_html = (f"<div class='cc-muted' style='margin-top:6px'>"
                    f"{html.escape(caption)}</div>" if caption else "")
    column.markdown(
        f"<div class='cc-stat'><div class='cc-stat-title'>"
        f"{html.escape(title)}</div>{value_html}{caption_html}</div>",
        unsafe_allow_html=True)


RUN_COLUMNS = (
    ("run_number", "Run", "{:.0f}", True),
    ("run_label", "Run label", None, False),
    ("period", "Period", None, False),
    ("active_days", "Days", "{:.0f}", True),
    ("spend", "Spend ({currency})", "{:,.0f}", True),
    ("conversions", "Tracked actions", "{:,.0f}", True),
    ("cost_per_conversion", "Cost per tracked action ({currency})", "{:,.2f}",
     True),
    ("ratio_to_benchmark", "Ratio", "{:.2f}x", True),
)


def _runs_html(runs, currency):
    """The runs table as HTML: run label as a pill, "—" if missing.

    Start and end are shown as one period ("31 May – 13 Jul 2026");
    a run labelled insufficient data shows "—" for its ratio (it was
    not judged). The CSV download keeps the ISO start and end."""
    runs = runs.copy()
    if "start" in runs.columns and "end" in runs.columns:
        runs["period"] = [dashboard_data.format_period(a, b)
                          for a, b in zip(runs["start"], runs["end"])]
    if "ratio_to_benchmark" in runs.columns and "run_label" in runs.columns:
        runs.loc[runs["run_label"] == "insufficient_data",
                 "ratio_to_benchmark"] = float("nan")
    columns = [spec for spec in RUN_COLUMNS if spec[0] in runs.columns]
    head = "".join(
        f"<th{' class=n' if numeric else ''}>"
        f"{html.escape(title.format(currency=currency))}</th>"
        for _key, title, _pattern, numeric in columns)
    body = []
    for _, row in runs.iterrows():
        cells = []
        for key, _title, pattern, numeric in columns:
            value = row[key]
            if key == "run_label":
                cells.append(f"<td>{_pill(value)}</td>")
            elif pattern:
                cells.append(f"<td class='n'>{_fmt(value, pattern)}</td>")
            elif key == "period":
                cells.append(f"<td>{_period_html(value)}</td>")
            else:
                cells.append(
                    f"<td class='nw'>{html.escape(_readable(value, True))}"
                    "</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return (f"<div class='cc-scroll'><table class='cc-table cc-tight'>"
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


def _runs_card(ctx, campaign):
    """Runs table: existing columns plus run label, "—" for missing."""
    currency = ctx["currency"]
    runs = dashboard_data.run_recommendations_for_campaign(
        ctx["tables"]["recommendations_by_run"], campaign)
    head = st.columns([3, 1], vertical_alignment="center")
    head[0].markdown("<p class='cc-card-title'>Runs</p>",
                     unsafe_allow_html=True)
    if runs.empty:
        st.caption("No runs: runs are built only for the run groups in "
                   "the config.")
        return
    order = [column for column in (
        "run_number", "run_label", "start", "end", "active_days",
        "spend", "conversions", "cost_per_conversion",
        "ratio_to_benchmark") if column in runs.columns]
    runs = runs[order]
    download = runs.copy()
    download["run_label"] = download["run_label"].map(
        dashboard_data.label_text)
    head[1].download_button(
        "Download CSV",
        dashboard_data.csv_bytes(dashboard_data.display_table(download)),
        file_name=f"runs_{campaign}.csv", mime="text/csv",
        key="detail_runs_download", width="stretch")
    st.markdown(_runs_html(runs, currency), unsafe_allow_html=True)
    st.caption("Each run judged on its own; the final label comes from "
               "the latest run with enough data or the recent window.")


def _recent_window_days(config):
    """recent_trend.recent_window_days from the config, or None."""
    return (((config or {}).get("analysis") or {}).get(
        "recent_trend") or {}).get("recent_window_days")


def _trend_row(recent_trend, campaign):
    """The campaign's recent_trend.csv row (a Series), or None."""
    if recent_trend is None or recent_trend.empty:
        return None
    part = recent_trend.loc[recent_trend["campaign"] == campaign]
    return None if part.empty else part.iloc[0]


def _why_lines(ctx, row, campaign):
    """"Why this label" lines (data.why_lines) for one campaign."""
    config = ctx["config"]
    names = ctx["group_names"]
    _judged, bench = dashboard_data.scope_groups(
        config, ctx["tables"]["benchmarks"])
    runs = ctx["tables"]["recommendations_by_run"]
    run_count = int((runs["campaign"] == campaign).sum())
    window = (((config.get("analysis") or {}).get(
        "recommendation_rules") or {}).get("recent_label") or {}).get(
        "window_days")
    return dashboard_data.why_lines(
        row, run_count,
        dashboard_data.names_and([names.get(g, g) for g in bench]),
        window, names, ctx["currency"])


def _page_detail(ctx):
    """How has this campaign performed? Tiles, action and reasons,
    runs (with the trend table) and the trend chart, then weekday
    pattern and journey. Each row is a keyed container whose columns
    are equal height (see STYLE), so no column leaves a large blank
    area beside the other."""
    tables = ctx["tables"]
    currency = ctx["currency"]
    recs = ctx["all_recommendations"]
    ranked = list(dashboard_data.action_table(recs)["campaign"])
    options = ranked + sorted(set(recs["campaign"]) - set(ranked))
    _heading("Campaign detail", "How has this campaign performed?", ctx)
    # The campaign picker sits in the filter area under the top row.
    picker = st.columns([1, 2])[0]
    if not options:
        st.info("No campaigns.")
        return
    if st.session_state.get(_ckey(DETAIL_KEY)) not in options:
        st.session_state[_ckey(DETAIL_KEY)] = options[0]
    campaign = picker.selectbox(
        "Campaign", options, key=_ckey(DETAIL_KEY),
        help="Ordered as in the Act ranking; not-comparable last.")
    detail = dashboard_data.campaign_detail(
        recs, tables["recent_trend"], campaign)
    for key in ("reason", "trend_reason"):
        detail[key] = dashboard_data.replace_group_keys(
            detail[key], ctx["group_names"])
    row = recs.set_index("campaign").loc[campaign]
    ratio = row.get("label_ratio")

    # Five tiles: the Action sits in the tile row (wider), so it has
    # no card of its own with blank space beside the reasons.
    tiles = st.container(key="cc_detail_tiles").columns([1, 1, 1, 1, 1.6])
    _stat_tile(tiles[0], "Final label",
               f"<div style='margin-top:6px'>{_badge(detail['label'])}"
               "</div>",
               f"From {detail['label_from'].replace('_', ' ')}"
               + (f", {dashboard_data.period_text(detail['label_period'])}"
                  if detail["label_period"] else ""))
    _stat_tile(tiles[1], "Status now",
               "<div class='cc-stat-v'>" + html.escape(
                   dashboard_data.value_text(detail["status_now"]))
               + "</div>",
               "Based on the last days of the data.")
    _stat_tile(tiles[2], "Recent trend",
               "<div class='cc-stat-v'>" + html.escape(
                   dashboard_data.value_text(detail["recent_trend"]))
               + "</div>",
               dashboard_data.trend_window_caption(ctx["config"])
               or "Recent window against the prior window.")
    _stat_tile(tiles[3], "Ratio to benchmark",
               "<div class='cc-stat-v'>"
               + _fmt(ratio, "{:.2f}x") + "</div>",
               "Cost per tracked action in the label period / its "
               "benchmark.")

    headline, extra = dashboard_data.split_action(detail["action"])
    _stat_tile(tiles[4], "Action",
               f"<div style='font-weight:600;margin-top:6px'>"
               f"{html.escape(headline or '—')}</div>"
               + (f"<div class='cc-act-detail'>{html.escape(extra)}</div>"
                  if extra else ""))
    with _box(st):
        _card_title("Why this label")
        st.markdown("".join(
            f"<p class='cc-take' style='margin:0 0 2px'>{html.escape(line)}"
            "</p>" for line in _why_lines(ctx, row, campaign)),
            unsafe_allow_html=True)
        trend_row = _trend_row(tables["recent_trend"], campaign)
        line = dashboard_data.trend_line(
            trend_row, _recent_window_days(ctx["config"]))
        if line:
            st.markdown(f"<p class='cc-take'>{html.escape(line)}</p>",
                        unsafe_allow_html=True)
        else:
            st.caption(dashboard_data.NO_TREND_TEXT)

    # Runs with the trend table under them | the trend chart. The
    # right column is filled first: the table follows its view and
    # period.
    runs, trend = st.container(key="cc_detail_main").columns([1.2, 1])
    with _box(trend):
        _card_title("Trend")
        shown = _detail_trend(ctx, campaign)
    with _box(runs):
        _runs_card(ctx, campaign)
        _trend_table(shown, campaign)

    weekday_col, journey_col = st.container(
        key="cc_detail_more").columns(2)
    with weekday_col:
        with st.expander("Weekday pattern"):
            by_campaign = tables["weekday_by_campaign"]
            if campaign not in set(by_campaign["campaign"]):
                st.caption("No weekday rows: weekday tables cover the "
                           "time groups in the config.")
            else:
                weekday = dashboard_data.weekday_campaign_table(
                    by_campaign, campaign)
                st.caption("This campaign's cost per tracked action by "
                           "weekday.")
                st.plotly_chart(charts.weekday_bar(
                    weekday, currency,
                    highlight=dashboard_data.most_clicks_weekday(weekday)),
                    width="stretch", key="detail_weekday",
                    config={"displayModeBar": False})
                notes = " ".join(text for text in (
                    dashboard_data.weekday_outline_text(weekday),
                    dashboard_data.low_weekday_volume_text(
                        weekday, ctx["config"])) if text)
                if notes:
                    st.caption(notes)
                with st.expander("Weekday table"):
                    _table(weekday, f"weekday_{campaign}.csv",
                           key="detail_weekday_table",
                           display=dashboard_data.pooled_weekday_display(
                               weekday, currency),
                           formats=dashboard_data.POOLED_WEEKDAY_FORMATS)
    with journey_col:
        with st.expander("How do people reach the restaurant?"):
            journey = dashboard_data.journey_row(
                tables["journey_by_campaign"], campaign)
            if journey.empty:
                st.caption("No journey row: the journey covers the time "
                           "groups in the config.")
            else:
                st.caption("How this campaign's tracked actions split "
                           "into directions, calls and store visits.")
                long = dashboard_data.journey_intent_long(journey)
                st.plotly_chart(charts.intent_stack(long),
                                width="stretch",
                                key="detail_journey_chart")
                keep = [column for column in (
                    "spend", "clicks", "tracked_actions",
                    "engagement_actions", "tracked_actions_per_click",
                    "cost_per_tracked_action")
                    if column in journey.columns]
                _table(journey[keep], key="detail_journey",
                       column_config={
                           "spend": NUM(f"Spend ({currency})",
                                        format="%.0f"),
                           "clicks": NUM("Clicks", format="%.0f"),
                           "tracked_actions": NUM("Tracked actions",
                                                  format="%.0f"),
                           "engagement_actions": NUM(
                               "Engagement actions", format="%.0f"),
                           "tracked_actions_per_click": NUM(
                               "Tracked actions per click", format="%.3f"),
                           "cost_per_tracked_action": NUM(
                               f"Cost per tracked action ({currency})",
                               format="%.2f")})


PAGE_TITLES = ("Act", "Context", "Campaign detail", "Method")
PAGE_OBJECTS = {}
_CTX = {}


def act():
    """Act page (st.navigation entry)."""
    _page_act(_CTX)
    _caveat(_CTX)


def context():
    """Context page (st.navigation entry)."""
    _page_context(_CTX)
    _caveat(_CTX)


def campaign_detail():
    """Campaign detail page (st.navigation entry)."""
    _page_detail(_CTX)
    _caveat(_CTX)


def method():
    """Method page (st.navigation entry)."""
    _page_method(_CTX)
    _caveat(_CTX)


def _load(client):
    """Config, tables and context for one client."""
    config = dashboard_data.load_config(
        dashboard_data.client_config_path(client))
    output_root = dashboard_data.client_output_root(client, config)
    tables = dashboard_data.load_tables(config, output_root=output_root)
    optional = dashboard_data.load_optional_tables(
        config, output_root=output_root)
    paths = dashboard_data.table_paths(config, output_root=output_root)
    names = dashboard_data.group_names(config)
    return {
        "client": client,
        "config": config,
        "group_names": names,
        "journey_pool": dashboard_data.journey_pool_label(config, names),
        "currency": config.get("currency", "SEK"),
        "tables": tables,
        "optional": optional,
        "break_even": dashboard_data.load_break_even(
            config, output_root=output_root),
        "date_range": dashboard_data.data_date_range(
            tables["campaign_summary_day"]),
        "updated": dashboard_data.last_updated(paths.values()),
    }


LOGO_TYPES = {".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
              ".webp": "image/webp"}


LOGO_HEIGHT = 216  # pixels kept in memory: sharp at 72px on 2x-3x screens


@st.cache_data(show_spinner=False)
def _logo_data(path_text, mtime):
    """(media type, base64, width/height ratio) of the logo,
    downscaled in memory.

    A raster logo taller than LOGO_HEIGHT is resized (aspect ratio
    kept) so a large file is not sent in full on every rerun. The
    file on disk is never changed. mtime is part of the cache key.
    An SVG has no raster size, so its ratio is 1.
    """
    path = Path(path_text)
    kind = LOGO_TYPES.get(path.suffix.lower(), "image/png")
    raw = path.read_bytes()
    ratio = 1.0
    if kind != "image/svg+xml":
        try:
            import io
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as image:
                ratio = image.width / image.height
                if image.height > LOGO_HEIGHT:
                    width = round(image.width * LOGO_HEIGHT / image.height)
                    small = image.resize((width, LOGO_HEIGHT),
                                         Image.LANCZOS)
                    out = io.BytesIO()
                    small.save(out, format="PNG", optimize=True)
                    raw, kind = out.getvalue(), "image/png"
        except Exception:  # an unreadable image: send the file as is
            pass
    return kind, base64.b64encode(raw).decode("ascii"), ratio


def _logo_img(path):
    """The logo as an inline <img> (read locally, never uploaded)."""
    kind, data, _ratio = _logo_data(str(path), path.stat().st_mtime)
    return (f"<img class='cc-logo' alt='Logo' "
            f"src='data:{kind};base64,{data}'>")


def _header(clients, pages=None, current=None):
    """The header, two rows at every width: the heading row (the
    one-line heading and the data line under it at the left, the
    logo or wordmark at the right edge) and the tabs row (the page
    tabs at the left, under the heading text; the client picker at
    the right, then the menu).

    The logo comes from branding.logo_path in the client config; when
    the key or the file is missing, the wordmark shows in its place.
    The logo follows the picked client, so the heading row is a
    placeholder filled by the page's _heading after the picker has
    run. pages: the st.Page objects for the tabs (none in tests that
    run one page); current: the page being shown, whose tab is
    underlined.
    """
    with st.container(key="cc_header"):
        _TOP["slot"] = st.empty()
        with st.container(key="cc_controls", horizontal=True, wrap=False,
                          vertical_alignment="center"):
            with st.container(key="cc_nav", horizontal=True, wrap=False,
                              width="content"):
                for number, page in enumerate(pages or ()):
                    active = current is not None and \
                        page.url_path == current.url_path
                    state = "on" if active else f"off_{number}"
                    with st.container(key=f"cc_nav_{state}",
                                      width="content"):
                        st.page_link(page, label=page.title)
            with st.container(key="cc_picker", width=160):
                client = st.selectbox("Client", clients, index=0,
                                      key="client",
                                      label_visibility="collapsed")
    try:
        config = dashboard_data.load_config(
            dashboard_data.client_config_path(client))
    except FileNotFoundError:
        config = {}
    logo = dashboard_data.logo_path(config)
    _TOP["brand"] = _logo_img(logo) if logo is not None else WORDMARK
    return client


def main():
    """Header (heading with the logo at the right; tabs and picker
    below), load the tables, run a page."""
    st.set_page_config(page_title="CampaignCompass", layout="wide",
                       initial_sidebar_state="collapsed")
    st.markdown(STYLE, unsafe_allow_html=True)
    pages = [st.Page(act, title="Act", default=True),
             st.Page(context, title="Context"),
             st.Page(campaign_detail, title="Campaign detail"),
             st.Page(method, title="Method")]
    PAGE_OBJECTS.update(zip(PAGE_TITLES, pages))
    page = st.navigation(pages, position="hidden")
    client = _header(dashboard_data.list_clients(), pages, page)
    if st.session_state.get("_client") != client:
        for key in CLIENT_WIDGETS:
            st.session_state.pop(key, None)
        st.session_state["_client"] = client
    try:
        ctx = _load(client)
    except FileNotFoundError as exc:
        st.error(f"{exc}")
        st.stop()
    recs = ctx["tables"]["recommendations_by_campaign"]
    ctx["all_recommendations"] = recs
    ctx["campaigns"] = sorted(recs["campaign"])
    _CTX.clear()
    _CTX.update(ctx)
    page.run()


if __name__ == "__main__":
    main()
