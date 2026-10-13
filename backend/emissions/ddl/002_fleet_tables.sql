-- Fleet tables (scope change 2026-10-13). Definitions only: loading to BigQuery needs approval.
-- Source CSVs live in data/fleet/ (python -m backend.fleet.build).

CREATE TABLE IF NOT EXISTS `${dataset}.fleet_sites` (site_id STRING NOT NULL, name STRING, country STRING, data_kind STRING, source_id STRING);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_machines` (machine_id STRING NOT NULL, site_id STRING, display_name STRING, rated_kw FLOAT64, fuel_type STRING);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_operations` (operation_code STRING NOT NULL, display_name STRING, category STRING, site_kind STRING);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_clients` (client_id STRING NOT NULL, name STRING, site_id STRING, is_synthetic BOOL);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_fields` (field_id STRING NOT NULL, site_id STRING, client_id STRING, area_ha FLOAT64, area_method STRING);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_operators` (operator_id STRING NOT NULL, site_id STRING, role STRING, is_synthetic BOOL);  -- pseudonyms only

-- One row per job. litres/hours/area are real; operator_id, client_id and (when listed) start_ts are synthetic.
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_jobs` (
  job_id STRING NOT NULL, site_id STRING, machine_id STRING, operator_id STRING, client_id STRING, field_id STRING,
  operation_code STRING, start_ts TIMESTAMP, hours FLOAT64, litres FLOAT64, area_ha FLOAT64, mean_load_pct FLOAT64,
  idle_ratio FLOAT64, sessions INT64, litres_label STRING, area_label STRING, source_id STRING,
  date_basis STRING, date_real TIMESTAMP, synthetic_columns STRING
) PARTITION BY DATE(start_ts) CLUSTER BY site_id, machine_id;

CREATE TABLE IF NOT EXISTS `${dataset}.fleet_other_activity` (machine_id STRING, month STRING, activity_class STRING, hours FLOAT64, litres FLOAT64);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_depots` (depot_id STRING NOT NULL, site_id STRING, capacity_l FLOAT64, opening_stock_l FLOAT64, opening_date DATE);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_fuel_deliveries` (delivery_id STRING, depot_id STRING, ts TIMESTAMP, supplier STRING, doc_no STRING, litres FLOAT64, unit_price_gbp FLOAT64);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_fuel_dispenses` (dispense_id STRING, depot_id STRING, machine_id STRING, operator_id STRING, ts TIMESTAMP, litres FLOAT64);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_depot_stock_readings` (depot_id STRING, date DATE, dip_litres FLOAT64);
CREATE TABLE IF NOT EXISTS `${dataset}.fleet_maintenance_events` (event_id STRING, machine_id STRING, date DATE, event_type STRING, job_hours_at_event FLOAT64, note STRING);
-- ground_truth_anomalies is for evals only and is deliberately not loaded next to the analytics tables.
