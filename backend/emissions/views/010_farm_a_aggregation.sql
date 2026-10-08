-- Farm A aggregation from telemetry_raw (run by infra/load_gcp.py after the Parquet loads).

-- 1. Field hull per (tractor, work type folder, field file) from in-field GPS points.
CREATE OR REPLACE TABLE `${dataset}.farm_a_field_hulls` AS
SELECT ROW_NUMBER() OVER (ORDER BY tractor_id, work_type, field_file) AS hull_id,
       tractor_id, work_type, field_file,
       ST_CONVEXHULL(ST_UNION_AGG(ST_GEOGPOINT(lon, lat))) AS hull
FROM `${dataset}.telemetry_field_points`
WHERE status IN ('working', 'turning') AND lat IS NOT NULL AND lon IS NOT NULL
GROUP BY tractor_id, work_type, field_file;

-- 2. Physical fields. Field_N IDs restart per folder, so hulls of the same field must be merged -
--    but only when (a) they overlap by >= 50% of the smaller hull's area, so neighbouring plots that
--    merely touch stay separate, and (b) their areas are within 3x of each other, so one oversized
--    hull (a file spanning several plots) cannot absorb the small plots inside it. Overlapping pairs
--    are grouped transitively (connected components).
CREATE TEMP TABLE edges AS
SELECT a.hull_id AS x, b.hull_id AS y
FROM `${dataset}.farm_a_field_hulls` a
JOIN `${dataset}.farm_a_field_hulls` b
  ON a.hull_id < b.hull_id AND ST_INTERSECTS(a.hull, b.hull)
WHERE ST_AREA(ST_INTERSECTION(a.hull, b.hull)) >= 0.5 * LEAST(ST_AREA(a.hull), ST_AREA(b.hull))
  AND GREATEST(ST_AREA(a.hull), ST_AREA(b.hull)) <= 3 * LEAST(ST_AREA(a.hull), ST_AREA(b.hull));

CREATE TEMP TABLE labels AS
SELECT hull_id, hull_id AS comp FROM `${dataset}.farm_a_field_hulls`;

LOOP
  CREATE OR REPLACE TEMP TABLE next_labels AS
  SELECT l.hull_id, LEAST(l.comp, IFNULL(MIN(n.comp), l.comp)) AS comp
  FROM labels l
  LEFT JOIN (SELECT x, y FROM edges UNION ALL SELECT y, x FROM edges) e ON e.x = l.hull_id
  LEFT JOIN labels n ON n.hull_id = e.y
  GROUP BY l.hull_id, l.comp;
  IF (SELECT COUNT(*) FROM next_labels JOIN labels USING (hull_id) WHERE next_labels.comp != labels.comp) = 0 THEN
    LEAVE;
  END IF;
  CREATE OR REPLACE TEMP TABLE labels AS SELECT * FROM next_labels;
END LOOP;

CREATE OR REPLACE TABLE `${dataset}.farm_a_fields_geo` AS
SELECT FORMAT('field_%03d', DENSE_RANK() OVER (ORDER BY MIN(ST_Y(ST_CENTROID(h.hull))), l.comp)) AS field_id,
       ST_UNION_AGG(h.hull) AS geog,
       ROUND(ST_AREA(ST_UNION_AGG(h.hull)) / 10000, 3) AS hull_area_ha,
       ARRAY_AGG(STRUCT(h.tractor_id, h.work_type, h.field_file)) AS source_files
FROM `${dataset}.farm_a_field_hulls` h
JOIN labels l USING (hull_id)
GROUP BY l.comp;

-- 3. Operations at tractor x session x activity x operation x field grain (field_id NULL = outside fields).
--    Fields may partly overlap after step 2, so each row is assigned to at most one field: the
--    smallest containing one (most specific). The reconciliation view proves nothing is double counted.
CREATE OR REPLACE TABLE `${dataset}.farm_a_operations` AS
WITH assigned AS (
  SELECT t.tractor_id, t.row_idx, f.field_id
  FROM `${dataset}.telemetry_raw` t
  JOIN `${dataset}.farm_a_fields_geo` f
    ON t.lat IS NOT NULL AND ST_CONTAINS(f.geog, ST_GEOGPOINT(t.lon, t.lat))
  QUALIFY ROW_NUMBER() OVER (PARTITION BY t.tractor_id, t.row_idx ORDER BY f.hull_area_ha, f.field_id) = 1
)
SELECT t.tractor_id, t.session_id, t.activity_class, t.operation_code, t.attribution_label, a.field_id,
       COUNT(*) AS n_rows,
       SUM(t.dt_s) / 3600 AS hours,
       SUM(t.fuel_l) AS litres,
       SUM(t.speed_mps * t.dt_s) / 1000 AS distance_km,
       AVG(t.eng_load_pct) AS mean_load_pct,
       APPROX_QUANTILES(t.eng_load_pct, 10) AS load_deciles,
       ANY_VALUE(t.implement_class) AS implement_class,
       ANY_VALUE(t.implement_width_m) AS implement_width_m
FROM `${dataset}.telemetry_raw` t
LEFT JOIN assigned a USING (tractor_id, row_idx)
GROUP BY 1, 2, 3, 4, 5, 6;

-- 4. Reconciliation: aggregated litres must equal raw litres per tractor (checked by the loader).
CREATE OR REPLACE VIEW `${dataset}.v_farm_a_reconciliation` AS
SELECT r.tractor_id, r.litres_raw, a.litres_aggregated,
       ABS(r.litres_raw - a.litres_aggregated) < 1e-6 * GREATEST(r.litres_raw, 1) AS reconciles
FROM (SELECT tractor_id, SUM(fuel_l) AS litres_raw FROM `${dataset}.telemetry_raw` GROUP BY 1) r
JOIN (SELECT tractor_id, SUM(litres) AS litres_aggregated FROM `${dataset}.farm_a_operations` GROUP BY 1) a
USING (tractor_id);
