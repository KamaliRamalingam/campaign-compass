# Method (draft)

1. Load the campaign-by-day export and validate the required columns.
2. Clean: duplicates, missing days, paused campaigns, formats.
3. Define metrics: cost per conversion, conversion rate, CTR, spend, conversions.
4. Apply the minimum-volume rule (threshold set in config).
5. Compare campaigns.
6. Compare by weekday, hour (if available) and location (if identifiable).
7. Check trend over time.
8. Apply recommendation rules: continue / test / pause / shift budget, with reasons.
9. Write result tables with a fixed schema.
10. State limits on every output.
