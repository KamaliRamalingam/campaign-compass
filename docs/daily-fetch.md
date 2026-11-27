# Daily Google Ads fetch (issue #74)

The pipeline used to run on CSV exports downloaded by hand from
the Google Ads UI. `src/fetch_ads.py` fetches the same three
exports from the Google Ads API instead, and `bash run.sh --fetch`
runs the fetch and then the whole pipeline on the fresh data.
A launchd job on the Mac runs it every day.

## What the fetch does

`src/fetch_ads.py --config config/restaurant.yaml`:

1. Reads the client config for the export format (title lines,
   encoding, delimiter, column headers), the date ranges
   (`analysis.daily_start` / `daily_end`, `analysis.monthly_end`)
   and the conversion breakdown file.
2. Reads the API credentials from `config/ads_api.yaml`
   (git-ignored, never committed).
3. Queries the Google Ads API (GAQL) and writes the three
   exports the loader reads, in the exact format of the manual
   exports (2 title lines, utf-8-sig, comma, headers from the
   config):
   - campaign by day: one row per campaign per day, from
     `daily_start` to today.
   - campaign by month: one row per campaign per month, from
     `fetch.monthly_start` (default `2015-01`, set it in the
     client config to change it) to `monthly_end`.
   - conversion by campaign and month: one row per campaign,
     month and conversion action, from `fetch.monthly_start`
     to the current month. Skipped when the config has no
     `conversion_breakdown` section.
4. Updates the client config in place (the day and month input
   paths, the conversion file path, and `analysis.daily_end` =
   today) so the pipeline reads the fresh files. Every other
   line, including comments, is kept. The old exports stay in
   `data/raw/`; delete them by hand when they are no longer
   needed.
5. Prints only a summary per file: rows, date range, campaign
   count, totals. Never campaign names, rows, or any credential.

A query that returns no rows is an error: the fetch cannot
produce a valid export from nothing.

## Running it

```bash
bash run.sh --fetch
```

`--fetch` is only for the restaurant client. It fails for
`--client synthetic_b` (that client generates its own data).
When `--fetch` is used, the validation stage (T0b) is skipped:
the data came from the API itself, so there is no UI export to
check the totals against. The fetch prints its own summary so
the totals can be compared with the Ads UI by eye. Without
`--fetch`, the pipeline behaves exactly as before.

## Setup the student must do (once)

The assistant cannot do these steps: they need the student's
Google account and the Ads account.

1. **Google Cloud project.** In [Google Cloud Console](https://console.cloud.google.com/),
   create (or pick) a project and enable the **Google Ads API**.
2. **OAuth credentials.** In the same project, create OAuth 2.0
   credentials for a **Desktop app**. Note the client ID and
   client secret.
3. **Refresh token.** Authorise the Desktop app once with the
   Google account that has access to the Ads account, and keep
   the refresh token. (The google-ads library's
   `generate_user_credentials` helper does this, or any OAuth
   flow that returns a refresh token for the
   `https://www.googleapis.com/auth/adwords` scope.)
4. **Developer token.** In the Google Ads account
   ("Tamilish"), go to **Tools > API Center** and get a
   developer token. A test token is instant but only works
   with a test account; a standard token needs Google's review
   and can take days. The fetch cannot pull live data until
   this is in place.
5. **Customer ID.** The Ads account's customer ID (the number
   shown in the Ads UI, dashes optional).
6. **Credentials file.** Copy `config/ads_api.yaml.example` to
   `config/ads_api.yaml` and fill in the five values (plus
   `login_customer_id` only when access is through a manager
   account). This file is git-ignored. Never commit it, and
   never paste its contents into chat, a pull request, or an
   issue.

Then run `bash run.sh --fetch` once by hand and check the
printed summary against the Ads UI totals.

## Daily schedule (Mac, launchd)

Runs the fetch and the pipeline every day at 06:00, logging to
`outputs/logs/daily-fetch.log` (git-ignored, under `outputs/`).
Create the file `~/Library/LaunchAgents/com.campaigncompass.fetch.plist`
with this content (the repo path is the student's Mac clone):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.campaigncompass.fetch</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd /Users/kamali/projects/campaign-compass &amp;&amp; mkdir -p outputs/logs &amp;&amp; bash run.sh --fetch &gt;&gt; outputs/logs/daily-fetch.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>6</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/Users/kamali/projects/campaign-compass/outputs/logs/daily-fetch.log</string>
  <key>StandardErrorPath</key><string>/Users/kamali/projects/campaign-compass/outputs/logs/daily-fetch.log</string>
</dict>
</plist>
```

Then load it once:

```bash
launchctl load ~/Library/LaunchAgents/com.campaigncompass.fetch.plist
```

Check it ran with `tail outputs/logs/daily-fetch.log`. To stop it:
`launchctl unload ~/Library/LaunchAgents/com.campaigncompass.fetch.plist`.

## Notes and limits

- The report due 27 Nov 2026 17:00 still uses the 12 Nov 2026
  CSV exports. Live data is a post-submission improvement; it
  does not change the submitted figures.
- The most recent days may still be settling: tracked actions
  can be reported with a delay (the pipeline's
  `conversion_lag_days` is 3). The dashboard shows data
  through today, and the recent-trend logic already excludes
  the last 3 days from its windows.
- The fetch cannot be verified live until the API access above
  is set up. The tests use a fake API client, not the real
  Google Ads API.
- The deployed dashboard (Streamlit Community Cloud) does not
  run this fetch: it reads the result tables from the repo.
  The daily fetch runs on the Mac and refreshes the local
  pipeline and dashboard.
