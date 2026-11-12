# Decision log

| Date | Decision | Evidence / notes | Status |
|---|---|---|---|
| 2026-11-12 | Cross-file tolerance set to clicks 2, cost 5.00, conversions 0.05. | Day + month totals differ from monthly totals by 1 click and 2.10 SEK, and the same gap already exists between the Google Ads UI views. | Proposed, awaiting my confirmation. |
| 2026-11-12 | Overlap finding corrected: no overlap. | The month file ends in Sep 2023, the day file starts on 2024-07-01. | Recorded. |
| 2026-11-12 | Real data range: day data 2024-07-01 to 2026-11-12 (13 campaigns); month data 2018-05 to 2023-09 (15 campaigns); no campaign rows between Oct 2023 and Jun 2024. | From the validation run on the real exports. | Recorded. |
| 2026-11-12 | Who created the six Sep 2026 campaigns, and are they tests? | The sep_2026_group in config/restaurant.yaml (two exact names plus the "The South Indian Campaign" prefix rule). | Waiting for owner. |
| 2026-11-12 | Are DrTiwari, Lorry booking and Yoga Mela unrelated to the restaurant? | They are in the exclude_pending_owner group in config/restaurant.yaml. | Waiting for owner. |
| 2026-11-12 | Provisional campaign grouping and volume rule (min_conversions 10, min_days_active 14), to be confirmed by the student. | config/restaurant.yaml, analysis.campaign_groups and analysis.volume_rule. | Waiting for owner. |
| 2026-11-12 | Recommendation rules, provisional, my decision: benchmark is the core group overall cost per conversion (calculated, not typed in); continue_max_ratio 1.0; test_max_ratio 2.0; pause_above_ratio 2.0; repeat_min_runs 2. | config/restaurant.yaml, analysis.recommendation_rules. | Provisional, my decision. |
| 2026-11-12 | Conversion action groups are provisional, my decision. | config/restaurant.yaml, conversion_breakdown.action_groups (high_intent, engagement; anything else is unmapped). | Provisional, my decision. |
| 2026-11-12 | Conversions in this account are Google local actions and calls, not bookings or orders. Wording: tracked actions. | src/conversion_mix.py and its outputs. | Recorded. |
| 2026-11-12 | Recent-trend rule compares against the prior 28 days as well as the run average; thresholds 1.3 and 0.77 are provisional, my decision, 2026-11-12. | config/restaurant.yaml, analysis.recent_trend (worsening_vs_prior_ratio 1.3, improving_vs_prior_ratio 0.77; worsening_ratio 1.5 and improving_ratio 0.67 against the run average kept). | Provisional, my decision. |
