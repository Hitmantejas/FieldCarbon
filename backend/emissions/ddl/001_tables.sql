-- FieldCarbon BigQuery tables. `${dataset}` is substituted at deploy time (one dataset, no layers).
-- Reference rows carry source_id; input rows carry source, confidence_label, ingested_at.

-- ===== Reference =====
CREATE TABLE IF NOT EXISTS `${dataset}.ref_sources` (
  source_id STRING NOT NULL, title STRING, publisher_or_authors STRING, year INT64, url STRING,
  licence STRING, evidence_type STRING, region STRING, is_manufacturer BOOL, used_for STRING,
  link_status STRING, accessed_at DATE
);

CREATE TABLE IF NOT EXISTS `${dataset}.ref_emission_factors` (
  ef_id STRING NOT NULL, fuel_type STRING NOT NULL, component STRING NOT NULL, unit STRING,
  kgco2e_per_unit FLOAT64 NOT NULL, kgco2_per_unit FLOAT64, kgch4_co2e_per_unit FLOAT64,
  kgn2o_co2e_per_unit FLOAT64, standard STRING, year INT64 NOT NULL, source_row_id STRING,
  source_row_label STRING, source_id STRING NOT NULL, value_status STRING
);

CREATE TABLE IF NOT EXISTS `${dataset}.ref_fuel_use_rates` (
  rate_id STRING NOT NULL, source_id STRING NOT NULL, source_row_label STRING,
  gal_per_acre FLOAT64, l_per_ha FLOAT64 NOT NULL, range_low_l_per_ha FLOAT64,
  range_high_l_per_ha FLOAT64, published_band_pct FLOAT64, excludes STRING, source_id_note STRING
);

CREATE TABLE IF NOT EXISTS `${dataset}.ref_operations` (
  operation_code STRING NOT NULL, display_name STRING, category STRING, tum_worktypes STRING,
  isu_rate_ids STRING, purdue_rate_ids STRING, match_quality STRING, note STRING
);

CREATE TABLE IF NOT EXISTS `${dataset}.ref_interventions` (
  coef_id STRING NOT NULL, intervention_id STRING NOT NULL, intervention_name STRING,
  effect_type STRING NOT NULL, value FLOAT64, low FLOAT64, high FLOAT64, unit STRING, baseline STRING,
  yield_pct_low FLOAT64, yield_pct_high FLOAT64, applicability JSON, region STRING,
  soil_context STRING, source_id STRING NOT NULL, value_status STRING, derivation STRING
);

-- One row per published month; the price range for payback is computed, never hand-entered.
CREATE TABLE IF NOT EXISTS `${dataset}.ref_fuel_prices` (
  fuel_type STRING NOT NULL, price_month DATE NOT NULL, price_per_litre FLOAT64 NOT NULL,
  currency STRING, unit STRING, vat_basis STRING, report_url STRING, source_id STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `${dataset}.dataset_provenance` (
  provenance_id STRING NOT NULL, dataset_name STRING, doi STRING, version STRING, licence STRING,
  file_name STRING, md5 STRING, processed_at TIMESTAMP, script_commit STRING, params JSON,
  details JSON                         -- e.g. tractor, rated kW, rows, litres, excluded frozen data
);

-- ===== Inputs =====
CREATE TABLE IF NOT EXISTS `${dataset}.farms` (
  farm_id STRING NOT NULL, name STRING, tier INT64, region STRING, soil_type STRING,
  soil_source STRING, is_demo BOOL,
  source STRING, confidence_label STRING, ingested_at TIMESTAMP, provenance_id STRING
);

CREATE TABLE IF NOT EXISTS `${dataset}.fields` (
  field_id STRING NOT NULL, farm_id STRING NOT NULL, name STRING, area_ha FLOAT64,
  area_method STRING, soil_type STRING, slope_pct FLOAT64,
  source STRING, confidence_label STRING, ingested_at TIMESTAMP, provenance_id STRING
);

CREATE TABLE IF NOT EXISTS `${dataset}.machines` (
  machine_id STRING NOT NULL, farm_id STRING NOT NULL, display_name STRING, rated_kw FLOAT64,
  fuel_type STRING, has_ctis BOOL, ballast_type STRING, tyre_pressure_checked BOOL,
  source STRING, confidence_label STRING, ingested_at TIMESTAMP, provenance_id STRING
);

-- One row per machine x session x activity x field (Tier 1) or per declared operation (Tier 2/3).
CREATE TABLE IF NOT EXISTS `${dataset}.operations` (
  operation_id STRING NOT NULL, farm_id STRING NOT NULL, machine_id STRING, field_id STRING,
  operation_code STRING, activity_class STRING, session_id STRING, hours FLOAT64, area_ha FLOAT64,
  distance_km FLOAT64, mean_load_pct FLOAT64, implement_class STRING, implement_width_m FLOAT64,
  source STRING, confidence_label STRING, ingested_at TIMESTAMP, provenance_id STRING
);

CREATE TABLE IF NOT EXISTS `${dataset}.fuel_records` (
  fuel_record_id STRING NOT NULL, farm_id STRING NOT NULL, machine_id STRING, operation_id STRING,
  field_id STRING, receipt_id STRING, litres FLOAT64 NOT NULL, fuel_type STRING NOT NULL,
  record_date DATE,
  source STRING, confidence_label STRING, ingested_at TIMESTAMP, provenance_id STRING
);

-- Receipt extraction: raw is append-only (as extracted); validated is what feeds fuel_records.
CREATE TABLE IF NOT EXISTS `${dataset}.receipts_raw` (
  receipt_id STRING NOT NULL, farm_id STRING NOT NULL, gcs_uri STRING, model_id STRING,
  prompt_version STRING, extracted JSON, field_confidence JSON, extracted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `${dataset}.receipts_validated` (
  receipt_id STRING NOT NULL, farm_id STRING NOT NULL, delivery_date DATE, supplier_anon STRING,
  litres FLOAT64, fuel_type STRING, unit_price FLOAT64, total FLOAT64, currency STRING,
  status STRING,                       -- accepted | corrected | rejected
  errors ARRAY<STRING>, validated_by STRING, validated_at TIMESTAMP
);

-- ===== Telemetry (Farm A, all 5 TUM tractors; brand columns dropped at load) =====
CREATE TABLE IF NOT EXISTS `${dataset}.telemetry_raw` (
  tractor_id STRING NOT NULL, row_idx INT64, t_s FLOAT64, dt_s FLOAT64, session_id INT64,
  eng_speed_rpm FLOAT64, eng_load_pct FLOAT64, fuel_rate_lph FLOAT64, fuel_l FLOAT64,
  speed_mps FLOAT64, lat FLOAT64, lon FLOAT64, altitude_m FLOAT64, pto_rpm FLOAT64,
  rear_draft_n FLOAT64, speed_source STRING, work_type STRING, implement_class STRING, implement_width_m FLOAT64,
  status STRING, activity_class STRING, operation_code STRING, attribution_label STRING
)
CLUSTER BY tractor_id, activity_class;

-- GPS points of the per-field files (downsampled), used only to build field hulls with BigQuery GIS.
CREATE TABLE IF NOT EXISTS `${dataset}.telemetry_field_points` (
  tractor_id STRING NOT NULL, work_type STRING, field_file STRING, status STRING,
  lat FLOAT64, lon FLOAT64, speed_mps FLOAT64, dt_s FLOAT64, implement_width_m FLOAT64
)
CLUSTER BY tractor_id;
