# Power BI build guide

Follow these steps in Power BI Desktop to rebuild the three-page report. The interactive HTML dashboard in `dashboard/index.html` is the visual reference: same pages, same questions, same numbers. Build time is roughly 2 to 3 hours.

When you finish, check your numbers against the "Reference values" at the bottom. If they match, the model and measures are right.

## Quick start: open the prebuilt model (saves about an hour)

`powerbi/TGV_Punctuality.pbip` is a Power BI Project with steps 1 to 3 below already done: the four tables, the four relationships, the date table, and all 24 DAX measures. The data is embedded in the model, so there is no file path to set. It also has the three empty pages (Home, Overview, Routes & Causes). You only build the visuals (steps 4 to 8).

1. In Power BI Desktop: **File > Options and settings > Options > Preview features**, tick **Power BI Project (.pbip) save option** if it is not already on, then restart Power BI.
2. Open `powerbi/TGV_Punctuality.pbip`. The Data pane shows the tables but they are empty until you refresh. You may see two yellow bars saying relationships or tables need to be refreshed.
3. Click **Home > Refresh** once and wait about 10 seconds. The bars disappear and the tables are filled.
4. Check the model against the reference values at the bottom of this guide, then continue at step 4 (Theme).

To regenerate the project after changing `powerbi/measures.dax` or the data: `python scripts/make_pbip.py`. It overwrites the model files, so do not run it after you started building visuals.

Do not use File > Export > Power BI template on this project: the template exported from it fails to load ("cyclic reference" on `dim_route`). Save your work as a `.pbip` (or build a new `.pbix` from scratch by following steps 1 to 3 below).

How it was checked: the project was opened in Power BI Desktop, **Home > Refresh** was clicked, and the model was queried with DAX. The totals, the filtered reference line, the year-over-year measure and the cause shares matched the reference values below. The three report pages open empty, as intended.

## 1. Load the data

1. **Home > Get data > Text/CSV**, load these four files from `data/processed/`: `fact_route_month.csv`, `fact_delay_cause.csv`, `dim_route.csv`, `dim_date.csv`.
2. In Power Query for each table:
   - Set `month` (in the two facts and `dim_date`) to **Date**.
   - Set all count columns in `fact_route_month` to **Whole number** and `avg_delay_late_trains_min` to **Decimal number**.
   - In `dim_route`, set `is_paris_route` to **True/False**.
   - Rename the queries to `fact_route_month`, `fact_delay_cause`, `dim_route`, `dim_date`.
3. In `dim_date`, select `month_name` and **Column tools > Sort by column > `month_number`**, so months sort Jan to Dec instead of alphabetically.
4. **Close and apply**.

## 2. Model

In **Model view**, create these one-to-many relationships (single direction, dimension filters fact):

| From (many) | To (one) |
|-------------|----------|
| `fact_route_month[route_id]` | `dim_route[route_id]` |
| `fact_route_month[month]` | `dim_date[month]` |
| `fact_delay_cause[route_id]` | `dim_route[route_id]` |
| `fact_delay_cause[month]` | `dim_date[month]` |

Mark `dim_date` as the date table (**Table tools > Mark as date table**, column `month`).

Hide the key columns and the raw count columns from the report view so that only measures are used in visuals.

## 3. Measures

Create an empty table (**Enter data**, name it `_Measures`) and paste the measures from [`powerbi/measures.dax`](../powerbi/measures.dax). Set formats:

- `Cancellation Rate`, `Late Arrival Rate`, `Over 30 Rate`, `Over 60 Rate`, `On Time Rate`, `Cause Share`: percentage, 1 decimal.
- `Late Rate YoY Change (pts)`: percentage, 1 decimal, with a `+` sign (custom format `+0.0%;-0.0%`). Power BI shows `%` for this measure, read it as percentage points.
- Volumes: whole number with thousands separator.
- `Avg Delay of Late Trains (min)`: decimal, 1 place.

**Why ratios of sums:** averaging each route-month's rate would give a one-train month the same weight as a 1,000-train month. Every rate here is `SUM(numerator) / SUM(denominator)`.

## 4. Theme

**View > Themes > Browse for themes** and import [`powerbi/sncf_theme.json`](../powerbi/sncf_theme.json). Set the canvas to 16:9 (page size 1280 x 720).

## 5. Page 1: Home

A landing page, like the home page of a web app.

- A navy header band with the title "TGV Punctuality" and the subtitle "SNCF open data, 2018 to 2026".
- Three **page navigator buttons** (Insert > Buttons > Navigator > Page navigator).
- One large card: `[Late Arrival Rate]` with its category label.
- Three **text boxes** with the headline findings (copy them from the Home page of the HTML dashboard).
- A text box with the source, licence (ODbL) and the caveat that route-level totals are not the official SNCF regularity.

## 6. Page 2: Overview

**Filters (left or top):** slicers for `dim_route[service]`, `dim_route[journey_band]`, `dim_date[year]`. Set **Sync slicers** so they apply to all pages.

**Axis buttons (the equivalent of the vehicle-type icons in the Uber example):**
1. Add a slicer on `dim_route[axis]`, style **Tile** (Format > Slicer settings > Style).
2. Optionally replace the tiles with a **Button slicer** with one icon per axis. Click an axis and the whole page filters.

**KPI cards (top row, 5 cards):** `[Trains Planned]`, `[Cancellation Rate]`, `[Late Arrival Rate]`, `[Over 60 Rate]`, `[Avg Delay of Late Trains (min)]`.

**Charts:**

| Visual | Fields |
|--------|--------|
| Line chart, late-arrival rate over time | X: `dim_date[month]` (continuous), Y: `[Late Arrival Rate]` |
| Column chart, cancellation rate | X: `dim_date[month]`, Y: `[Cancellation Rate]` |
| Bar chart, late-arrival rate by axis | Axis: `dim_route[axis]`, X: `[Late Arrival Rate]`, sorted descending |
| Donut, what happened to planned trains | See below |

For the donut, create a small disconnected table `Outcome` (Enter data) with the rows `On time`, `Late under 15 min`, `Late 15 to 30 min`, `Late 30 to 60 min`, `Late over 60 min`, `Cancelled`, and a measure with `SWITCH(SELECTEDVALUE(Outcome[Outcome]), ...)` that returns, respectively, `[Trains Run]-[Late Arrivals]`, `[Late Arrivals]-[Late Over 15]`, `[Late Over 15]-[Late Over 30]`, `[Late Over 30]-[Late Over 60]`, `[Late Over 60]`, `[Trains Cancelled]`. Use the measure as the donut value and `Outcome[Outcome]` as the legend.

**Month / Quarter toggle (like the Uber example):** create two bookmarks, one with the line chart on `dim_date[month]` and one on `dim_date[quarter]`, and two buttons that switch between them. Alternatively use a **field parameter** (Modeling > New parameter > Fields) with `month`, `quarter` and `year`, and use it as the X axis.

## 7. Page 3: Routes & Causes

| Visual | Fields |
|--------|--------|
| Table, routes ranked | `dim_route[route]`, `[Trains Run]`, `[Late Arrival Rate]`, `[Over 60 Rate]`, `[Total Delay Hours]`. Visual filter: `[Trains Run]` is at least 2000. Sort by late rate. |
| Bar chart, causes | Axis: `fact_delay_cause[cause]`, X: `[Cause Share]` |
| Matrix, seasonality heatmap | Rows: `dim_date[year]`, columns: `dim_date[month_name]`, values: `[Late Arrival Rate]`. **Format > Cell elements > Background colour > Gradient** (white to red) |
| Clustered bar, severe delays by journey length | Axis: `dim_route[journey_band]`, X: `[Over 30 Rate]` and `[Over 60 Rate]` |

**Tooltip page (optional, impressive in a demo):** create a hidden page of type Tooltip with a card for `[Late Arrival Rate]`, `[Late Rate YoY Change (pts)]` and `[Total Delay Hours]`, then assign it as the tooltip of the route table.

## 8. Polish checklist

- Titles on every visual, with units. Remove the default "Sum of ..." labels.
- Align visuals on the grid, same spacing and corner radius.
- Use `[Late Rate Colour]` as a conditional-format field for the late-rate KPI.
- **View > Selection pane:** give each visual a clear name, and set the tab order.
- Add alt text to the visuals (Format > General > Alt text).
- Test every slicer combination. Click a bar and check that all visuals respond.

## 9. Publish and share

1. Save as `powerbi/TGV_Punctuality.pbix`. The file is small (about 3 MB of data), so it can be committed.
2. **File > Export > PDF** gives a static copy. Take a 1280 x 720 screenshot of each page for the README.
3. To record the "click and everything filters" demo for LinkedIn, use a screen recorder (Windows: Win+G, or Xbox Game Bar) and keep it under 30 seconds. Turn it into a GIF or upload the video directly.
4. Publishing to the Power BI Service needs a work or school account. Without one, the HTML dashboard is the shareable version (see `dashboard/` and GitHub Pages).

## Reference values (full data, no filters)

Use these to check your report.

| Measure | Value |
|---------|------:|
| Trains Planned | 3,529,822 |
| Trains Cancelled | 106,788 |
| Trains Run | 3,423,034 |
| Late Arrivals | 501,864 |
| Cancellation Rate | 3.0% |
| Late Arrival Rate | 14.7% |
| Over 60 Rate | 2.1% |
| Avg Delay of Late Trains (min) | 35.1 |
| Total Delay Hours | 293,930 |

With filters `service = National`, `axis = Cross-country`, `year = 2025`: Trains Planned 50,560, Trains Run 50,212, Late Arrivals 10,358, Over 60: 2,362.
