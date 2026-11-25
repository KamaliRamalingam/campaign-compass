# Data dictionary

Input columns from the Google Ads exports, as mapped in `config/restaurant.yaml` (`columns` and `conversion_breakdown.columns`). Another client maps its own headers in its own config.

## Campaign by day and campaign by month

| Column (logical name) | Export header | Meaning | Type | Notes |
|---|---|---|---|---|
| date | Day (day file), Month (month file) | Day or month of the row | date | Required |
| campaign | Campaign | Campaign name | text | Required |
| cost | Cost | Spend in the account currency | number | Required; currency symbol stripped on load |
| clicks | Clicks | Ad clicks | integer | Required |
| conversions | Conversions | Tracked actions counted by the account (mainly get-directions requests and phone calls) | number | Required; not bookings or orders |
| impressions | Impr. | Ad impressions | integer | Optional |

## Conversion by campaign and month

| Column (logical name) | Export header | Meaning | Type | Notes |
|---|---|---|---|---|
| campaign | Campaign | Campaign name | text | |
| month | Month | Month of the row | date | |
| action | Conversion action | Name of the conversion action | text | Mapped to an action group (high intent, engagement, unmapped) |
| conversions | Conversions | Conversions counted for bidding (tracked actions) | number | |
| all_conversions | All conv. | All conversions, including engagement actions | number | Used for the engagement share |

## Derived metrics

| Metric | Definition |
|---|---|
| cost per tracked action | cost / conversions (empty when conversions is 0) |
| tracked actions per click | conversions / clicks |
| ratio to benchmark | cost per tracked action / core benchmark (leave-one-out) |
| active day | a day with any activity; missing days are not filled |
