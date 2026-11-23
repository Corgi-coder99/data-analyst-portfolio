# Data quality log

Every rule applied by `scripts/clean_and_model.py`, with the number of rows it touched.

| Rule | Rows | Treatment |
|------|-----:|-----------|
| Raw rows loaded | 12,907 | One row per route (departure to arrival station) per month, Jan 2018 to the latest month |
| Duplicate route-month keys | 0 | Checked: none found, no rows removed |
| Cancellations greater than planned trains | 63 | Mostly April 2020 (lockdown, 0 planned trains still reported cancellations). Planned trains raised to the number cancelled so rates never exceed 100% |
| Negative counts of trains more than 30 min late | 43 | Impossible values, set to 0 |
| Late-train counts above the trains that actually ran (all five columns) | 3 | Capped at trains run, which keeps every rate between 0 and 100% |
| Rows where the late thresholds are not nested (e.g. more trains over 60 min than over 30 min) | 388 | Counts raised to the more severe bucket, so the chain late arrivals >= over 15 >= over 30 >= over 60 always holds |
| Negative average arrival delay of late trains | 2 | A delayed train cannot arrive early on average, set to missing and excluded from delay-minute totals |
| Implausible values in retard_moyen_tous_trains_arrivee (below -30 min) | 9 | The column is not used. Delay is rebuilt from the average delay of late trains x number of late trains |
| Average journey time equal to 0 | 73 | Months with no planned train. Set to missing |
| Route names shared by a National and an International service | 32 | Label suffixed with the service so that every route name is unique (needed for ranking in Power BI) |
| Distinct routes (service, departure, arrival) | 146 | Directional routes, one row each in dim_route |
| Route-months with late trains but no cause shares reported | 81 | Kept in the facts. Excluded from the cause breakdown, which is an estimate |
| Clean fact rows written | 12,907 | 2018-01 to 2026-09, 146 routes |
