/* =====================================================================
   PROJECT 1 - COVID-19 EXPLORATION  |  01_data_cleaning.sql
   Engine : DuckDB (also runs on PostgreSQL with the noted tweaks)
   Source : Our World in Data - compact.csv (long format, 1 row = country x day)
   Run    : python scripts/run_all.py   (from project root)
   ===================================================================== */

-- ---------------------------------------------------------------------
-- 1. Load raw file / Nap du lieu tho
-- PostgreSQL: create covid_raw with matching columns, then use psql \copy covid_raw FROM 'data/compact.csv' CSV HEADER
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE covid_raw AS
SELECT * FROM read_csv_auto('data/compact.csv', sample_size = -1);

-- ---------------------------------------------------------------------
-- 2. Data-quality profile of the raw table
-- ---------------------------------------------------------------------
SELECT COUNT(*)                       AS total_rows,
       COUNT(DISTINCT country)        AS distinct_entities,
       MIN(date)                      AS first_date,
       MAX(date)                      AS last_date,
       COUNT(*) FILTER (WHERE continent IS NULL) AS rows_without_continent
FROM covid_raw;

-- Which "entities" are NOT real countries? (aggregates have continent = NULL)
-- Cac thuc the khong phai quoc gia (World, Asia, High-income countries, ...)
SELECT DISTINCT country
FROM covid_raw
WHERE continent IS NULL
ORDER BY country;

-- Sanity checks: negative daily values (data revisions) and duplicate keys
SELECT COUNT(*) AS negative_new_cases  FROM covid_raw WHERE new_cases  < 0;
SELECT COUNT(*) AS negative_new_deaths FROM covid_raw WHERE new_deaths < 0;
SELECT country, date, COUNT(*) AS dup FROM covid_raw GROUP BY 1, 2 HAVING COUNT(*) > 1;

-- ---------------------------------------------------------------------
-- 3. Clean table: countries only, selected columns, typed, NULL-safe
--    - Drop aggregate rows (continent IS NULL) -> avoids double counting
--    - Drop rows with no population (cannot compute per-capita metrics)
--    - COALESCE daily flow columns to 0 (a missing report = nothing added);
--      cumulative columns stay NULL-able (NULL = never reported)
--    - Count columns cast to BIGINT (exact integers, so ROUND/ratios also work on PostgreSQL)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE covid_clean AS
SELECT
    country,
    code                                   AS iso_code,
    continent,
    CAST(date AS DATE)                     AS date,
    CAST(population AS BIGINT)             AS population,
    CAST(total_cases AS BIGINT) AS total_cases,
    CAST(COALESCE(new_cases, 0) AS BIGINT)  AS new_cases,
    CAST(total_deaths AS BIGINT) AS total_deaths,
    CAST(COALESCE(new_deaths, 0) AS BIGINT) AS new_deaths,
    CAST(total_vaccinations AS BIGINT) AS total_vaccinations,
    CAST(people_vaccinated AS BIGINT) AS people_vaccinated,
    CAST(people_fully_vaccinated AS BIGINT) AS people_fully_vaccinated,
    CAST(COALESCE(new_vaccinations, 0) AS BIGINT) AS new_vaccinations,
    stringency_index,
    gdp_per_capita,
    median_age
FROM covid_raw
WHERE continent IS NOT NULL
  AND population IS NOT NULL
  AND population > 0;

-- ---------------------------------------------------------------------
-- 4. Post-clean validation
-- ---------------------------------------------------------------------
SELECT COUNT(*) AS clean_rows, COUNT(DISTINCT country) AS countries FROM covid_clean;

-- Grain check: exactly one row per country-day
SELECT COUNT(*) AS rows_, COUNT(DISTINCT (country, date)) AS unique_keys FROM covid_clean;

-- Safe-division pattern used in every ratio below:
--   numerator * 100.0 / NULLIF(denominator, 0)
