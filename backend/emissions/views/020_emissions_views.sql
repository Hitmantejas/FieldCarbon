-- Calculated views: emissions = litres x documented emission factor, computed in BigQuery.
-- Read-only over farm_a_operations and the reference tables; views store no data.
-- Label rules match backend/emissions/farm_summary.py and backend/tools/contracts.py:
--   farm and tractor totals: measured | operations: weakest input label | fields: allocated
--   cost: estimated (price range) | data_gap rows: excluded from litres and engine hours.

-- 1. Well-to-wheel factor per fuel and year: every component except biogenic CO2 (outside of scopes).
CREATE OR REPLACE VIEW `${dataset}.v_wtw_factors` AS
SELECT fuel_type, year, unit,
       SUM(kgco2e_per_unit) AS kgco2e_per_unit,
       ARRAY_AGG(ef_id ORDER BY ef_id) AS ef_ids,
       ANY_VALUE(source_id) AS source_id
FROM `${dataset}.ref_emission_factors`
WHERE component != 'outside_scopes_biogenic_co2'
GROUP BY fuel_type, year, unit;

-- 2. Farm A settings in one place: red diesel = gas oil, 2025 factor set; price range over all months.
CREATE OR REPLACE VIEW `${dataset}.v_farm_a_settings` AS
SELECT f.fuel_type, f.year AS ef_year, f.kgco2e_per_unit AS kgco2e_per_l, f.ef_ids, f.source_id AS ef_source_id,
       p.price_low, p.price_high, p.from_month, p.to_month, p.price_source_id
FROM `${dataset}.v_wtw_factors` f
CROSS JOIN (
  SELECT MIN(price_per_litre) AS price_low, MAX(price_per_litre) AS price_high,
         FORMAT_DATE('%Y-%m', MIN(price_month)) AS from_month, FORMAT_DATE('%Y-%m', MAX(price_month)) AS to_month,
         ANY_VALUE(source_id) AS price_source_id
  FROM `${dataset}.ref_fuel_prices`
  WHERE fuel_type = 'gas_oil'
) p
WHERE f.fuel_type = 'gas_oil' AND f.year = 2025;

-- 3. Rows that carry fuel: frozen logger stretches and zero-litre rows are left out.
CREATE OR REPLACE VIEW `${dataset}.v_farm_a_fuel_rows` AS
SELECT tractor_id, activity_class, operation_code, attribution_label, field_id, hours, litres,
       IF(activity_class = 'field_work' AND operation_code IS NOT NULL, operation_code, activity_class) AS operation_key
FROM `${dataset}.farm_a_operations`
WHERE activity_class != 'data_gap' AND litres > 0;

-- 4. Farm summary.
CREATE OR REPLACE VIEW `${dataset}.v_farm_a_summary` AS
SELECT
  'a' AS farm_id,
  t.litres,
  t.litres * s.kgco2e_per_l AS co2e_kg,
  t.litres * s.price_low AS cost_gbp_low,
  t.litres * s.price_high AS cost_gbp_high,
  h.hours, h.excluded_hours,
  'measured' AS label, 'estimated' AS cost_label,
  s.ef_year, s.kgco2e_per_l, s.ef_ids,
  ['tum_alc_data', s.ef_source_id] AS co2e_source_ids,
  ['tum_alc_data', s.price_source_id] AS cost_source_ids,
  s.from_month AS price_from_month, s.to_month AS price_to_month
FROM (SELECT SUM(litres) AS litres FROM `${dataset}.farm_a_operations`) t
CROSS JOIN (
  SELECT SUM(IF(activity_class != 'data_gap', hours, 0)) AS hours,
         SUM(IF(activity_class = 'data_gap', hours, 0)) AS excluded_hours
  FROM `${dataset}.farm_a_operations`
) h
CROSS JOIN `${dataset}.v_farm_a_settings` s;

-- 5. Breakdowns. share_pct is of fuel-carrying litres; the three views each sum to the farm total.
CREATE OR REPLACE VIEW `${dataset}.v_farm_a_emissions_by_tractor` AS
SELECT r.tractor_id AS key, SUM(r.litres) AS litres, SUM(r.litres) * ANY_VALUE(s.kgco2e_per_l) AS co2e_kg,
       SUM(r.litres) * ANY_VALUE(s.price_low) AS cost_gbp_low, SUM(r.litres) * ANY_VALUE(s.price_high) AS cost_gbp_high,
       SUM(r.hours) AS hours, 100 * SUM(r.litres) / SUM(SUM(r.litres)) OVER () AS share_pct,
       'measured' AS label, ANY_VALUE(s.ef_year) AS ef_year, ANY_VALUE(s.ef_ids) AS ef_ids
FROM `${dataset}.v_farm_a_fuel_rows` r CROSS JOIN `${dataset}.v_farm_a_settings` s
GROUP BY r.tractor_id;

CREATE OR REPLACE VIEW `${dataset}.v_farm_a_emissions_by_operation` AS
SELECT r.operation_key AS key, SUM(r.litres) AS litres, SUM(r.litres) * ANY_VALUE(s.kgco2e_per_l) AS co2e_kg,
       SUM(r.litres) * ANY_VALUE(s.price_low) AS cost_gbp_low, SUM(r.litres) * ANY_VALUE(s.price_high) AS cost_gbp_high,
       SUM(r.hours) AS hours, 100 * SUM(r.litres) / SUM(SUM(r.litres)) OVER () AS share_pct,
       -- weakest input label wins
       CASE WHEN LOGICAL_OR(r.attribution_label = 'estimated') THEN 'estimated'
            WHEN LOGICAL_OR(r.attribution_label = 'allocated') THEN 'allocated'
            ELSE 'measured' END AS label,
       ANY_VALUE(s.ef_year) AS ef_year, ANY_VALUE(s.ef_ids) AS ef_ids
FROM `${dataset}.v_farm_a_fuel_rows` r CROSS JOIN `${dataset}.v_farm_a_settings` s
GROUP BY r.operation_key;

CREATE OR REPLACE VIEW `${dataset}.v_farm_a_emissions_by_field` AS
SELECT IFNULL(r.field_id, 'unassigned') AS key, SUM(r.litres) AS litres,
       SUM(r.litres) * ANY_VALUE(s.kgco2e_per_l) AS co2e_kg,
       SUM(r.litres) * ANY_VALUE(s.price_low) AS cost_gbp_low, SUM(r.litres) * ANY_VALUE(s.price_high) AS cost_gbp_high,
       SUM(r.hours) AS hours, 100 * SUM(r.litres) / SUM(SUM(r.litres)) OVER () AS share_pct,
       'allocated' AS label,  -- field boundaries have no ground truth
       ANY_VALUE(s.ef_year) AS ef_year, ANY_VALUE(s.ef_ids) AS ef_ids
FROM `${dataset}.v_farm_a_fuel_rows` r CROSS JOIN `${dataset}.v_farm_a_settings` s
GROUP BY IFNULL(r.field_id, 'unassigned');
