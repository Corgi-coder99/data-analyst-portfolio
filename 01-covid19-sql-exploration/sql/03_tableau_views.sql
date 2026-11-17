/* =====================================================================
   PROJECT 1 - COVID-19 EXPLORATION  |  03_tableau_views.sql
   Reusable views ready for Tableau / Power BI (connect to these, not raw tables)
   Requires: covid_clean
   ===================================================================== */

-- V1. One row per country with headline metrics (map / bar charts)
CREATE OR REPLACE VIEW v_country_summary AS
SELECT continent, country, iso_code,
       MAX(population)                                                      AS population,
       MAX(total_cases)                                                     AS total_cases,
       MAX(total_deaths)                                                    AS total_deaths,
       ROUND(MAX(total_deaths) * 100.0 / NULLIF(MAX(total_cases), 0), 2)    AS case_fatality_rate_pct,
       ROUND(MAX(total_cases)  * 100.0 / NULLIF(MAX(population), 0), 2)     AS pct_population_infected,
       ROUND(MAX(total_deaths) * 1000000.0 / NULLIF(MAX(population), 0), 0) AS deaths_per_million,
       ROUND(MAX(people_fully_vaccinated) * 100.0 / NULLIF(MAX(population), 0), 1) AS pct_fully_vaccinated
FROM covid_clean
GROUP BY continent, country, iso_code;

-- V2. Continent totals
CREATE OR REPLACE VIEW v_continent_deaths AS
SELECT continent, SUM(total_deaths) AS total_deaths, SUM(total_cases) AS total_cases
FROM v_country_summary
GROUP BY continent;

-- V3. Global monthly series (line chart)
CREATE OR REPLACE VIEW v_global_monthly AS
SELECT CAST(DATE_TRUNC('month', date) AS DATE) AS month,
       SUM(new_cases)  AS new_cases,
       SUM(new_deaths) AS new_deaths,
       ROUND(SUM(new_deaths) * 100.0 / NULLIF(SUM(new_cases), 0), 2) AS death_rate_pct
FROM covid_clean
GROUP BY 1;

-- V4. Daily rolling vaccination per country (CTE + window function)
CREATE OR REPLACE VIEW v_vaccination_progress AS
WITH rolling AS (
    SELECT country, continent, date, population, new_vaccinations,
           SUM(new_vaccinations) OVER (PARTITION BY country ORDER BY date
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS rolling_doses,
           total_vaccinations, people_vaccinated, people_fully_vaccinated
    FROM covid_clean
)
-- rolling_doses = sum of reported daily doses (lower bound when days are missing)
-- total_vaccinations = official cumulative figure, prefer it for coverage charts
SELECT *, ROUND(rolling_doses * 100.0 / NULLIF(population, 0), 2) AS daily_sum_doses_per_100,
       ROUND(total_vaccinations * 100.0 / NULLIF(population, 0), 2) AS reported_total_doses_per_100
FROM rolling;

-- V5. Vietnam daily timeline with 7-day moving average
CREATE OR REPLACE VIEW v_vietnam_timeline AS
SELECT date, new_cases, new_deaths, total_cases, total_deaths,
       ROUND(AVG(new_cases)  OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS new_cases_7d_avg,
       ROUND(AVG(new_deaths) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS new_deaths_7d_avg,
       stringency_index
FROM covid_clean
WHERE country = 'Vietnam';

-- Export examples for Tableau (DuckDB):
-- COPY (SELECT * FROM v_country_summary) TO 'data/export_country_summary.csv' (HEADER);
-- COPY (SELECT * FROM v_global_monthly)  TO 'data/export_global_monthly.csv'  (HEADER);
