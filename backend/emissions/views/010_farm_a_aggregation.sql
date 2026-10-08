-- Farm A aggregation from telemetry_raw (run after loading data/raw/clean/*.parquet).
-- Status: written, not yet run — needs the hackathon GCP project.

-- 1. Field hull per (tractor, work type folder, field file) from in-field GPS points.
CREATE OR REPLACE TABLE `${dataset}.farm_a_field_hulls` AS
SELECT tractor_id, work_type, field_file,
       ST_CONVEXHULL(ST_UNION_AGG(ST_GEOGPOINT(lon, lat))) AS hull
FROM `${dataset}.telemetry_field_points`
WHERE status IN ('working', 'turning') AND lat IS NOT NULL AND lon IS NOT NULL
GROUP BY tractor_id, work_type, field_file;

-- 2. Physical fields: Field_N IDs restart per folder, so merge hulls that overlap (transitively).
CREATE OR REPLACE TABLE `${dataset}.farm_a_fields_geo` AS
WITH clustered AS (
  SELECT *, ST_CLUSTERDBSCAN(hull, 0, 1) OVER () AS cluster_id
  FROM `${dataset}.farm_a_field_hulls`
)
SELECT FORMAT('field_%03d', DENSE_RANK() OVER (ORDER BY MIN(ST_Y(ST_CENTROID(hull))), cluster_id)) AS field_id,
       ST_UNION_AGG(hull) AS geog,
       ROUND(ST_AREA(ST_UNION_AGG(hull)) / 10000, 3) AS hull_area_ha,
       ARRAY_AGG(STRUCT(tractor_id, work_type, field_file)) AS source_files
FROM clustered
GROUP BY cluster_id;

-- 3. Operations at tractor x session x activity x operation x field grain (field_id NULL = outside fields).
CREATE OR REPLACE TABLE `${dataset}.farm_a_operations` AS
SELECT t.tractor_id, t.session_id, t.activity_class, t.operation_code, t.attribution_label, f.field_id,
       COUNT(*) AS n_rows,
       SUM(t.dt_s) / 3600 AS hours,
       SUM(t.fuel_l) AS litres,
       SUM(t.speed_mps * t.dt_s) / 1000 AS distance_km,
       AVG(t.eng_load_pct) AS mean_load_pct,
       APPROX_QUANTILES(t.eng_load_pct, 10) AS load_deciles,
       ANY_VALUE(t.implement_class) AS implement_class,
       ANY_VALUE(t.implement_width_m) AS implement_width_m
FROM `${dataset}.telemetry_raw` t
LEFT JOIN `${dataset}.farm_a_fields_geo` f
  ON t.lat IS NOT NULL AND ST_CONTAINS(f.geog, ST_GEOGPOINT(t.lon, t.lat))
GROUP BY 1, 2, 3, 4, 5, 6;

-- 4. Reconciliation: aggregated litres must equal raw litres per tractor (checked by the loader).
CREATE OR REPLACE VIEW `${dataset}.v_farm_a_reconciliation` AS
SELECT r.tractor_id, r.litres_raw, a.litres_aggregated,
       ABS(r.litres_raw - a.litres_aggregated) < 1e-6 * GREATEST(r.litres_raw, 1) AS reconciles
FROM (SELECT tractor_id, SUM(fuel_l) AS litres_raw FROM `${dataset}.telemetry_raw` GROUP BY 1) r
JOIN (SELECT tractor_id, SUM(litres) AS litres_aggregated FROM `${dataset}.farm_a_operations` GROUP BY 1) a
USING (tractor_id);
