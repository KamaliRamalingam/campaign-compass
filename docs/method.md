# Method

The pipeline runs in this order from `bash run.sh`. Each stage reads only the config and the outputs of the stage before it. The full stage list with config keys is in the README, section 4.

1. **Validate** the raw exports against the totals shown in the Google Ads UI.
2. **Load** the campaign-by-day and campaign-by-month exports into standard tables and check the required columns.
3. **Clean**: keep rows inside the analysis ranges, drop duplicate rows on date and campaign, and flag rows with missing or negative values. Missing days are not filled.
4. **Group** each campaign from the config. A campaign in no group is reported as ungrouped, never dropped.
5. **Metrics** per campaign on active days: spend, clicks, tracked actions, cost per tracked action, tracked actions per click, and a volume flag.
6. **Time patterns**: weekday and monthly tables, a timeline, and runs (stretches of activity split by a gap of more than `run_gap_days`). The weekday decomposition splits the pooled weekday cells by campaign.
7. **Recommendations**: each run's cost per tracked action is compared with the core benchmark (calculated, leave-one-out). Labels: continue, test, pause or review, insufficient data, not comparable, not judged. Active campaigns are labelled from their last 90 days, and a worsening trend never shows continue.
8. **Conversion mix**: tracked actions by conversion action and action group (high intent, engagement, unmapped).
9. **Recent trend**: the recent 28 days against the prior 28 days and the run average (worsening, improving, stable, insufficient data). The lag check reruns this with other reporting lags.
10. **Acquisition journey, what-if and break-even**: the journey table, a linear what-if weekday shift (an estimate, not a bound), and break-even only when an average revenue per visit is set.
11. **Dashboard**: reads the result tables only and recomputes nothing.

Every output states the data range, the last-updated date and the caveat: tracked actions only, not bookings or orders, and not proof of cause. The exports have no hour column, so there is no hour-of-day analysis.
