-- Fleet calculated views: CO2e = litres x documented emission factor, computed in BigQuery.
-- They mirror backend/fleet/data.ledger() and the groupings of the fleet_summary tool; tests/test_fleet_bigquery.py
-- checks the two agree. Run after 002_fleet_tables.sql, the fleet load and 020_emissions_views.sql (v_farm_a_settings).

-- All fuel burned: one row per job, plus one per machine-month of fuel burned outside jobs (data gaps carry no fuel).
CREATE OR REPLACE VIEW `${dataset}.v_fleet_ledger` AS
WITH fuel_rows AS (
  SELECT site_id, machine_id, operator_id, client_id, field_id, operation_code,
         FORMAT_TIMESTAMP('%Y-%m', start_ts) AS month, litres, hours, area_ha, litres_label AS label, source_id, TRUE AS is_job
  FROM `${dataset}.fleet_jobs`
  UNION ALL
  SELECT SUBSTR(machine_id, 1, 2), machine_id, NULL, NULL, NULL, CONCAT('other_', activity_class),
         month, litres, hours, NULL, 'allocated', 'tum_alc_data', FALSE
  FROM `${dataset}.fleet_other_activity`
  WHERE activity_class != 'data_gap'
)
SELECT r.*, r.litres * s.kgco2e_per_l AS co2e_kg
FROM fuel_rows r CROSS JOIN `${dataset}.v_farm_a_settings` s;

CREATE OR REPLACE VIEW `${dataset}.v_fleet_by_site` AS
SELECT site_id AS key, SUM(litres) AS litres, SUM(co2e_kg) AS co2e_kg, SUM(hours) AS hours, COUNTIF(is_job) AS jobs
FROM `${dataset}.v_fleet_ledger` GROUP BY site_id;

CREATE OR REPLACE VIEW `${dataset}.v_fleet_by_machine` AS
SELECT machine_id AS key, SUM(litres) AS litres, SUM(co2e_kg) AS co2e_kg, SUM(hours) AS hours, COUNTIF(is_job) AS jobs
FROM `${dataset}.v_fleet_ledger` GROUP BY machine_id;

CREATE OR REPLACE VIEW `${dataset}.v_fleet_by_operation` AS
SELECT operation_code AS key, SUM(litres) AS litres, SUM(co2e_kg) AS co2e_kg, SUM(hours) AS hours, COUNTIF(is_job) AS jobs
FROM `${dataset}.v_fleet_ledger` GROUP BY operation_code;

CREATE OR REPLACE VIEW `${dataset}.v_fleet_by_month` AS
SELECT month AS key, SUM(litres) AS litres, SUM(co2e_kg) AS co2e_kg, SUM(hours) AS hours, COUNTIF(is_job) AS jobs
FROM `${dataset}.v_fleet_ledger` GROUP BY month;

-- Fuel with no client is 'unassigned', as in the tool.
CREATE OR REPLACE VIEW `${dataset}.v_fleet_by_client` AS
SELECT IFNULL(client_id, 'unassigned') AS key, SUM(litres) AS litres, SUM(co2e_kg) AS co2e_kg, SUM(hours) AS hours,
       COUNTIF(is_job) AS jobs
FROM `${dataset}.v_fleet_ledger` GROUP BY client_id;
