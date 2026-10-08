"""Clean each TUM zip in data/raw/ into Parquet files ready for BigQuery load.

Outputs (data/raw/clean/, gitignored: contains GPS):
  telemetry_<tractor_id>.parquet     -> telemetry_raw
  field_points_<tractor_id>.parquet  -> telemetry_field_points (~1 Hz, for field hulls)
  provenance_<tractor_id>.json       -> dataset_provenance
Committed (no coordinates):
  data/aggregated/farm_a_field_files.csv   per-field-file hours, litres, worked area

Reads CSVs straight from the zip; never extracts or loads the .pkl files.
Usage: python data/prep/prepare_tum.py ["data/raw/Fendt 211.zip" ...]
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from tum_clean import (COLUMN_MAP, FIELD_POINTS_SCHEMA, OUTPUT_SCHEMA, Params, clean_stream, field_file_summary,
                       field_points, load_worktype_map, tractor_from_model)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = RAW_DIR / "clean"
AGG_DIR = ROOT / "data" / "aggregated"
CHUNK_ROWS = 500_000


def split_members(z: zipfile.ZipFile) -> tuple[str, list[str]]:
    csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
    main = [n for n in csvs if len(PurePosixPath(n).parts) == 2]
    if len(main) != 1:
        raise SystemExit(f"expected one top-level CSV, found {main}")
    return main[0], [n for n in csvs if len(PurePosixPath(n).parts) == 3]


def read_csv(z: zipfile.ZipFile, name: str, **kw) -> pd.DataFrame | pd.io.parsers.TextFileReader:
    return pd.read_csv(z.open(name), usecols=lambda c: c in COLUMN_MAP, low_memory=False, **kw)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "uncommitted"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def process_zip(zpath: Path, params: Params, worktype_map: dict[str, str]) -> tuple[str, list[dict]]:
    z = zipfile.ZipFile(zpath)
    main_csv, field_csvs = split_members(z)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # --- full log -> telemetry_raw ---
    writer, tractor_id, rows_seen = None, None, 0
    excluded_h = excluded_l = 0.0
    schema = pa.schema([(c, pa.string() if t == "string" else pa.from_numpy_dtype(t))
                        for c, t in OUTPUT_SCHEMA.items()])
    summary = []
    for df in clean_stream(read_csv(z, main_csv, chunksize=CHUNK_ROWS), worktype_map, params):
        gap = df["activity_class"] == "data_gap"
        excluded_h += float(df.loc[gap, "dt_s"].sum()) / 3600.0
        excluded_l += float((df.loc[gap, "fuel_rate_lph"].fillna(0) * df.loc[gap, "dt_s"]).sum()) / 3600.0
        rows_seen += len(df)
        tractor_id = df["tractor_id"].iloc[0]
        if writer is None:
            writer = pq.ParquetWriter(CLEAN_DIR / f"telemetry_{tractor_id}.parquet", schema)
        writer.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False))
        summary.append(df.groupby(["activity_class", "operation_code"], dropna=False)
                       .agg(rows=("row_idx", "size"), hours=("dt_s", "sum"), litres=("fuel_l", "sum")))
        print(f"  {main_csv}: {rows_seen:,} rows", end="\r", flush=True)
    writer.close()
    print()
    act = pd.concat(summary).groupby(level=[0, 1], dropna=False).sum()
    act["hours"] /= 3600.0
    act["share_litres"] = act["litres"] / act["litres"].sum()
    print(act.sort_values("litres", ascending=False).round(3).to_string())
    act.to_csv(CLEAN_DIR / f"activity_summary_{tractor_id}.csv")

    # --- per-field files -> field summaries (committed) + ~1 Hz points (not committed) ---
    rows, points = [], []
    for name in field_csvs:
        parts = PurePosixPath(name).parts
        work_type, field_file = parts[1], PurePosixPath(parts[2]).stem
        raw = read_csv(z, name)
        s = field_file_summary(raw, params)
        rows.append({"tractor_id": tractor_id, "work_type": work_type,
                     "operation_code": worktype_map.get(work_type, f"unmapped:{work_type}"),
                     "field_file": field_file, **s})
        points.append(field_points(raw, tractor_id, work_type, field_file, params))
    if points:
        pts = pd.concat(points, ignore_index=True).astype(FIELD_POINTS_SCHEMA)
        pts.to_parquet(CLEAN_DIR / f"field_points_{tractor_id}.parquet", index=False)

    _, rated_kw = tractor_from_model(pd.read_csv(z.open(main_csv), nrows=1)["Tractor_Model_[-]"].iloc[0])
    provenance = {
        "provenance_id": f"tum_alc_{tractor_id}",
        "dataset_name": "TUM Agricultural Load Cycles", "doi": "10.5281/zenodo.14619787",
        "version": "Zenodo revision 8", "licence": "CC-BY-4.0", "file_name": zpath.name, "md5": md5_of(zpath),
        "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script_commit": git_commit(), "params": dataclasses.asdict(params),
        "tractor_id": tractor_id, "rated_kw": rated_kw, "rows": rows_seen,
        "litres_total": float(act["litres"].sum()),
        "excluded_frozen_hours": round(excluded_h, 3),
        "excluded_frozen_litres_if_counted": round(excluded_l, 3),
    }
    (CLEAN_DIR / f"provenance_{tractor_id}.json").write_text(json.dumps(provenance, indent=2))
    return tractor_id, rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zips", nargs="*", type=Path)
    args = ap.parse_args()
    zips = args.zips or sorted(RAW_DIR.glob("*.zip"))
    if not zips:
        sys.exit("no zips in data/raw — run data/prep/download_tum.py first")

    params, worktype_map = Params(), load_worktype_map()
    AGG_DIR.mkdir(parents=True, exist_ok=True)
    out = AGG_DIR / "farm_a_field_files.csv"
    existing = pd.read_csv(out) if out.exists() else pd.DataFrame()
    for zpath in zips:
        print(f"== {zpath.name}")
        tractor_id, rows = process_zip(zpath, params, worktype_map)
        if not existing.empty:
            existing = existing[existing["tractor_id"] != tractor_id]
        existing = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    existing.sort_values(["tractor_id", "work_type", "field_file"]).round(4).to_csv(out, index=False)
    print(f"field summaries -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
