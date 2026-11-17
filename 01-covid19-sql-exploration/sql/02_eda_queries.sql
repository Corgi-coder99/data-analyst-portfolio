/* =====================================================================
   PROJECT 1 - COVID-19 EXPLORATION  |  02_eda_queries.sql
   Requires: covid_clean (see 01_data_cleaning.sql)
   Techniques: CTE, Window functions (SUM OVER, LAG, ROW_NUMBER), CASE WHEN,
               aggregates, JOIN, NULLIF for safe division
   ===================================================================== */

-- =====================================================================
-- Q1. Case Fatality Rate by country (total_deaths / total_cases)
--     Use the LATEST row per country because
--     total_* columns are cumulative.
-- =====================================================================
WITH latest AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY country ORDER BY date DESC) AS rn
    FROM covid_clean
    WHERE total_cases IS NOT NULL
)
SELECT country, continent, total_cases, total_deaths,
       ROUND(total_deaths * 100.0 / NULLIF(total_cases, 0), 2) AS case_fatality_rate_pct
FROM latest
WHERE rn = 1 AND total_cases >= 100000          -- ignore tiny samples
ORDER BY case_fatality_rate_pct DESC NULLS LAST
LIMIT 15;

-- Q1b. Vietnam spotlight
WITH latest AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY country ORDER BY date DESC) AS rn
    FROM covid_clean WHERE total_cases IS NOT NULL
)
SELECT country, date AS as_of, total_cases, total_deaths, population,
       ROUND(total_deaths * 100.0 / NULLIF(total_cases, 0), 3)       AS case_fatality_rate_pct,
       ROUND(total_cases  * 100.0 / NULLIF(population, 0), 2)        AS infected_pct_of_population
FROM latest
WHERE rn = 1 AND country = 'Vietnam';

-- =====================================================================
-- Q2. Infection rate vs population (MAX(total_cases) / population)
-- =====================================================================
SELECT country, MAX(population) AS population,
       MAX(total_cases)         AS peak_total_cases,
       ROUND(MAX(total_cases) * 100.0 / NULLIF(MAX(population), 0), 2) AS pct_population_infected
FROM covid_clean
GROUP BY country
HAVING MAX(population) >= 1000000          -- skip micro-states
ORDER BY pct_population_infected DESC NULLS LAST
LIMIT 15;

-- Q2b. Same metric bucketed with CASE WHEN
WITH c AS (
    SELECT country,
           MAX(total_cases) * 100.0 / NULLIF(MAX(population), 0) AS pct_infected
    FROM covid_clean GROUP BY country
    HAVING MAX(population) >= 1000000          -- same filter as Q2
)
SELECT CASE WHEN pct_infected IS NULL THEN 'No data'
            WHEN pct_infected < 5   THEN '1. < 5%'
            WHEN pct_infected < 20  THEN '2. 5-20%'
            WHEN pct_infected < 40  THEN '3. 20-40%'
            ELSE                         '4. >= 40%' END AS infection_band,
       COUNT(*) AS countries
FROM c
GROUP BY 1
ORDER BY 1;

-- Q2c. Top 3 countries per continent by infection rate (ROW_NUMBER)
WITH c AS (
    SELECT continent, country,
           MAX(total_cases) * 100.0 / NULLIF(MAX(population), 0) AS pct_infected
    FROM covid_clean
    WHERE total_cases IS NOT NULL
    GROUP BY continent, country
    HAVING MAX(population) >= 1000000
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY continent ORDER BY pct_infected DESC) AS rk
    FROM c
)
SELECT continent, rk, country, ROUND(pct_infected, 2) AS pct_infected
FROM ranked WHERE rk <= 3
ORDER BY continent, rk;

-- =====================================================================
-- Q3. Continent breakdown: cumulative deaths
--     Take MAX per country FIRST, then SUM,
--     otherwise cumulative values would be added up repeatedly.
-- =====================================================================
WITH country_deaths AS (
    SELECT continent, country, MAX(total_deaths) AS deaths, MAX(population) AS pop
    FROM covid_clean
    GROUP BY continent, country
)
SELECT continent,
       SUM(deaths)                                   AS total_deaths,
       SUM(pop)                                      AS population,
       -- denominator only counts countries that report deaths
       ROUND(SUM(deaths) * 1000000.0 / NULLIF(SUM(pop) FILTER (WHERE deaths IS NOT NULL), 0), 0) AS deaths_per_million
FROM country_deaths
GROUP BY continent
ORDER BY total_deaths DESC;

-- =====================================================================
-- Q4. Global numbers over time
-- =====================================================================
-- Q4a. Monthly global new cases, new deaths, death rate, month-over-month change (LAG)
WITH monthly AS (
    SELECT DATE_TRUNC('month', date) AS month,
           SUM(new_cases)  AS new_cases,
           SUM(new_deaths) AS new_deaths
    FROM covid_clean
    GROUP BY 1
    -- drop the last month: it is incomplete (data ends mid-month)
    HAVING DATE_TRUNC('month', MAX(date)) < (SELECT DATE_TRUNC('month', MAX(date)) FROM covid_clean)
)
-- Caveat: 2022-12 (+710% MoM) and 2023-02 (death rate ~2%) are bulk/backlog reporting artifacts in the source
SELECT CAST(month AS DATE) AS month, new_cases, new_deaths,
       ROUND(new_deaths * 100.0 / NULLIF(new_cases, 0), 2)                    AS death_rate_pct,
       ROUND((new_cases - LAG(new_cases) OVER (ORDER BY month)) * 100.0
             / NULLIF(LAG(new_cases) OVER (ORDER BY month), 0), 1)           AS cases_mom_change_pct
FROM monthly
ORDER BY month;

-- Q4b. Worst single month for cases and for deaths
WITH monthly AS (
    SELECT DATE_TRUNC('month', date) AS month, SUM(new_cases) AS c, SUM(new_deaths) AS d
    FROM covid_clean GROUP BY 1
)
(SELECT 'Peak cases month'  AS metric, CAST(month AS DATE) AS month, c AS value FROM monthly ORDER BY c DESC LIMIT 1)
UNION ALL
(SELECT 'Peak deaths month' AS metric, CAST(month AS DATE) AS month, d AS value FROM monthly ORDER BY d DESC LIMIT 1);

-- Q4c. Overall global totals
SELECT SUM(new_cases) AS total_cases, SUM(new_deaths) AS total_deaths,
       ROUND(SUM(new_deaths) * 100.0 / NULLIF(SUM(new_cases), 0), 2) AS global_death_rate_pct
FROM covid_clean;

-- =====================================================================
-- Q5. Rolling vaccination count (Window function + CTE)
-- =====================================================================
WITH rolling AS (
    SELECT country, continent, date, population, new_vaccinations,
           SUM(new_vaccinations) OVER (PARTITION BY country ORDER BY date
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS rolling_doses
    FROM covid_clean
)
SELECT r.country, r.date, r.population, r.new_vaccinations, r.rolling_doses,
       -- sum of REPORTED daily doses per 100 people: a lower bound, see Q5d
       ROUND(r.rolling_doses * 100.0 / NULLIF(r.population, 0), 2) AS daily_sum_doses_per_100,
       -- official cumulative figure on that date (NULL if not reported that day)
       ROUND(c.total_vaccinations * 100.0 / NULLIF(r.population, 0), 2) AS reported_total_doses_per_100
FROM rolling r JOIN covid_clean c USING (country, date)
WHERE r.country = 'Vietnam'
  AND r.date IN (DATE '2021-06-30', DATE '2021-12-31', DATE '2022-06-30', DATE '2022-12-31', DATE '2023-06-30')
ORDER BY r.date;

-- Q5b. Share of population vaccinated, latest value per country
--      (people_* columns are capped at 100% -> the honest coverage metric)
WITH latest AS (
    SELECT country, continent, population,
           MAX(people_vaccinated)       AS at_least_one_dose,
           MAX(people_fully_vaccinated) AS fully_vaccinated
    FROM covid_clean GROUP BY country, continent, population
)
SELECT country, continent,
       ROUND(at_least_one_dose * 100.0 / NULLIF(population, 0), 1) AS pct_one_dose,
       ROUND(fully_vaccinated  * 100.0 / NULLIF(population, 0), 1) AS pct_fully_vaccinated
FROM latest
WHERE fully_vaccinated IS NOT NULL AND population >= 1000000
ORDER BY pct_fully_vaccinated DESC
LIMIT 15;

-- Q5c. Days from first reported vaccination to 50% of population with >= 1 dose (JOIN)
WITH first_dose AS (
    SELECT country, MIN(date) AS start_date FROM covid_clean WHERE total_vaccinations > 0 GROUP BY country
), half AS (
    SELECT country, MIN(date) AS half_date
    FROM covid_clean
    WHERE people_vaccinated * 100.0 / NULLIF(population, 0) >= 50
    GROUP BY country
)
SELECT f.country, f.start_date, h.half_date, DATE_DIFF('day', f.start_date, h.half_date) AS days_to_50pct
FROM first_dose f JOIN half h USING (country)
JOIN (SELECT country, MAX(population) AS pop FROM covid_clean GROUP BY country) p USING (country)
WHERE p.pop >= 1000000                          -- micro-states distort the ranking
ORDER BY days_to_50pct
LIMIT 10;

-- Q5d. Data-quality reconciliation: does the rolling sum of new_vaccinations match the
--      reported cumulative total_vaccinations? Gaps in daily reporting make it UNDER-count.
WITH rolled AS (
    SELECT country, SUM(new_vaccinations) AS sum_new_vacc, MAX(total_vaccinations) AS reported_total
    FROM covid_clean GROUP BY country
)
SELECT country, sum_new_vacc, reported_total,
       ROUND(sum_new_vacc * 100.0 / NULLIF(reported_total, 0), 1) AS rolling_as_pct_of_reported
FROM rolled
WHERE country IN ('Vietnam', 'United States', 'India', 'Brazil', 'Germany')
ORDER BY country;

-- =====================================================================
-- Q6. Views for BI tools -> see 03_tableau_views.sql
-- =====================================================================
