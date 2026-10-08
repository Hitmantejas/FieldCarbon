"""Load FieldCarbon data into GCP: Cloud Storage -> BigQuery -> aggregation -> small local exports.

Dry run by default: prints every command and touches nothing. Pass --apply to execute.
Re-runnable: existing bucket/dataset are reused, objects synced, tables replaced.

  python infra/load_gcp.py                      # dry run, all steps
  python infra/load_gcp.py --apply              # execute all steps
  python infra/load_gcp.py --apply --steps verify,export

Steps: preflight, bucket, upload, dataset, ddl, load_reference, load_telemetry, load_provenance,
       aggregate, verify, export
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = RAW / "clean"
REF = ROOT / "data" / "reference"
AGG = ROOT / "data" / "aggregated"
DDL = ROOT / "backend" / "emissions" / "ddl" / "001_tables.sql"
AGG_SQL = ROOT / "backend" / "emissions" / "views" / "010_farm_a_aggregation.sql"

PROJECT = "ai-hackathon-india"
REGION = "us-central1"
BUCKET = "fieldcarbon-ai-hackathon-india"
DATASET = "fieldcarbon"
ACCOUNT_DOMAIN = "@valtech.com"
TRACTORS = [f"tractor_{i}" for i in range(1, 6)]
LABELS = "app=fieldcarbon"

REF_TABLES = ["ref_sources", "ref_emission_factors", "ref_fuel_use_rates", "ref_operations",
              "ref_interventions", "ref_fuel_prices"]
STEPS = ["preflight", "bucket", "upload", "dataset", "ddl", "load_reference", "load_telemetry",
         "load_provenance", "aggregate", "verify", "export"]


class Runner:
    def __init__(self, apply: bool):
        self.apply = apply
        self.gcloud = shutil.which("gcloud") or "gcloud"
        self.bq = shutil.which("bq") or "bq"

    def run(self, args: list[str], stdin: str | None = None,
            check: bool = True) -> subprocess.CompletedProcess | None:
        """Run a CLI command. In dry-run mode nothing is executed (not even read-only queries)."""
        exe = {"gcloud": self.gcloud, "bq": self.bq}.get(args[0], args[0])
        shown = " ".join(a if " " not in a else f'"{a}"' for a in args)
        if stdin is not None:
            shown += f"   <<< {stdin.splitlines()[0][:70]}... ({len(stdin.splitlines())} lines of SQL)"
        if not self.apply:
            print(f"  [dry-run] {shown}")
            return None
        print(f"  $ {shown}")
        res = subprocess.run([exe, *args[1:]], input=stdin, capture_output=True, text=True, encoding="utf-8")
        if check and res.returncode != 0:
            sys.exit(f"command failed ({res.returncode}):\n{res.stderr.strip()[-2000:]}")
        return res

    def exists(self, args: list[str]) -> bool:
        if not self.apply:
            return False
        exe = {"gcloud": self.gcloud, "bq": self.bq}.get(args[0], args[0])
        return subprocess.run([exe, *args[1:]], capture_output=True, text=True).returncode == 0

    def sql(self, sql: str, fmt: str | None = None) -> str:
        args = ["bq", f"--project_id={PROJECT}", f"--location={REGION}", "query", "--use_legacy_sql=false",
                "--quiet", "--max_rows=100000"]
        if fmt:
            args.append(f"--format={fmt}")
        res = self.run(args, stdin=sql)
        return res.stdout if res else ""


def render(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("${dataset}", f"{PROJECT}.{DATASET}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


# ---------------------------------------------------------------------------------------------- steps

def preflight(r: Runner) -> None:
    account = subprocess.run([r.gcloud, "config", "get-value", "account"], capture_output=True, text=True).stdout.strip()
    project = subprocess.run([r.gcloud, "config", "get-value", "project"], capture_output=True, text=True).stdout.strip()
    print(f"  account={account} project={project}")
    if not account.endswith(ACCOUNT_DOMAIN) or project != PROJECT:
        sys.exit(f"expected a *{ACCOUNT_DOMAIN} account on project {PROJECT}")
    dirty = git("status", "--porcelain", "--", "data/prep", "data/reference", "backend", "infra")
    if dirty:
        msg = ("data/prep, data/reference, backend or infra has uncommitted changes: commit first so "
               f"provenance can cite the exact code:\n{dirty}")
        if r.apply:
            sys.exit(msg)
        print(f"  WARNING (would stop with --apply): {msg}")
    missing = [p for t in TRACTORS for p in (CLEAN / f"telemetry_{t}.parquet", CLEAN / f"field_points_{t}.parquet",
                                             CLEAN / f"provenance_{t}.json") if not p.exists()]
    zips = sorted(RAW.glob("*.zip"))
    if missing or len(zips) != 5:
        sys.exit(f"missing local inputs: {[p.name for p in missing]} zips={len(zips)} (run data/prep first)")
    print(f"  commit={git('rev-parse', '--short', 'HEAD')} zips={len(zips)} clean files OK")


def bucket(r: Runner) -> None:
    if r.exists(["gcloud", "storage", "buckets", "describe", f"gs://{BUCKET}", f"--project={PROJECT}"]):
        print(f"  gs://{BUCKET} exists, reusing")
        return
    r.run(["gcloud", "storage", "buckets", "create", f"gs://{BUCKET}", f"--project={PROJECT}",
           f"--location={REGION}", "--uniform-bucket-level-access", "--public-access-prevention",
           "--default-storage-class=STANDARD"])
    r.run(["gcloud", "storage", "buckets", "update", f"gs://{BUCKET}", f"--update-labels={LABELS}"])


def upload(r: Runner) -> None:
    # Raw zips: provenance archive, never overwritten. Clean outputs: synced (contain GPS; bucket is private).
    r.run(["gcloud", "storage", "cp", "--no-clobber", *[str(z) for z in sorted(RAW.glob("*.zip"))],
           str(RAW / "manifest.json"), f"gs://{BUCKET}/raw/tum/"])
    r.run(["gcloud", "storage", "rsync", str(CLEAN), f"gs://{BUCKET}/clean/", "--recursive", "--checksums-only"])


def dataset(r: Runner) -> None:
    if r.exists(["bq", f"--project_id={PROJECT}", "show", "--format=none", f"{PROJECT}:{DATASET}"]):
        print(f"  dataset {DATASET} exists, reusing")
        return
    r.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "mk", "--dataset",
           "--description=FieldCarbon: machinery emissions engine (Google Cloud AI Builder Cup 2026)",
           "--label=app:fieldcarbon", f"{PROJECT}:{DATASET}"])


def ddl(r: Runner) -> None:
    r.sql(render(DDL))


def load_reference(r: Runner) -> None:
    for table in REF_TABLES:
        r.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "load", "--replace",
               "--source_format=CSV", "--skip_leading_rows=1", "--allow_quoted_newlines",
               f"{DATASET}.{table}", str(REF / f"{table}.csv")])


def load_telemetry(r: Runner) -> None:
    r.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "load", "--replace",
           "--source_format=PARQUET", "--clustering_fields=tractor_id,activity_class",
           f"{DATASET}.telemetry_raw", f"gs://{BUCKET}/clean/telemetry_*.parquet"])
    r.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "load", "--replace",
           "--source_format=PARQUET", "--clustering_fields=tractor_id",
           f"{DATASET}.telemetry_field_points", f"gs://{BUCKET}/clean/field_points_*.parquet"])


def provenance_records() -> list[dict]:
    commit = git("rev-parse", "HEAD")
    records = []
    for t in TRACTORS:
        p = json.loads((CLEAN / f"provenance_{t}.json").read_text())
        records.append({
            "provenance_id": p["provenance_id"], "dataset_name": p["dataset_name"], "doi": p["doi"],
            "version": p["version"], "licence": p["licence"], "file_name": p["file_name"], "md5": p["md5"],
            "processed_at": p["processed_at"], "script_commit": commit, "params": p["params"],
            "details": {
                "tractor_id": p["tractor_id"], "rated_kw": p["rated_kw"], "rows": p["rows"],
                "litres_total": p["litres_total"],
                "excluded_frozen_hours": p.get("excluded_frozen_hours"),
                "excluded_frozen_litres_if_counted": p.get("excluded_frozen_litres_if_counted"),
                "script_commit_at_processing": p["script_commit"],
                "note": "processed before the first commit; data/prep and data/reference are unchanged "
                        "in script_commit (checked by preflight)",
            },
        })
    return records


def load_provenance(r: Runner) -> None:
    out = CLEAN / "dataset_provenance.ndjson"
    out.write_text("\n".join(json.dumps(rec) for rec in provenance_records()) + "\n", encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)} ({len(TRACTORS)} rows)")
    r.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "load", "--replace",
           "--source_format=NEWLINE_DELIMITED_JSON", f"{DATASET}.dataset_provenance", str(out)])


def aggregate(r: Runner) -> None:
    r.sql(render(AGG_SQL))


def verify(r: Runner) -> None:
    out = r.sql(f"SELECT tractor_id, litres_raw, litres_aggregated, reconciles "
                f"FROM `{PROJECT}.{DATASET}.v_farm_a_reconciliation` ORDER BY tractor_id",
                fmt="csv")
    if not r.apply:
        return
    rows = list(csv.DictReader(io.StringIO(out)))
    local = {t: json.loads((CLEAN / f"provenance_{t}.json").read_text())["litres_total"] for t in TRACTORS}
    ok = len(rows) == len(TRACTORS)
    for row in rows:
        bq_l, agg_l = float(row["litres_raw"]), float(row["litres_aggregated"])
        match_local = abs(bq_l - local[row["tractor_id"]]) <= 1e-6 * max(bq_l, 1)
        ok &= row["reconciles"] == "true" and match_local
        print(f"  {row['tractor_id']}: local {local[row['tractor_id']]:.3f} | bq raw {bq_l:.3f} | "
              f"aggregated {agg_l:.3f} | {'OK' if row['reconciles'] == 'true' and match_local else 'MISMATCH'}")
    if not ok:
        sys.exit("reconciliation failed: litres differ between local files, telemetry_raw and farm_a_operations")


EXPORTS = {
    # Small, coordinate-free aggregates committed to the repo.
    "farm_a_operations_summary.csv": f"""
        SELECT tractor_id, activity_class, operation_code, attribution_label, field_id,
               ROUND(SUM(hours), 4) AS hours, ROUND(SUM(litres), 4) AS litres,
               ROUND(SUM(distance_km), 3) AS distance_km,
               ROUND(SUM(mean_load_pct * hours) / NULLIF(SUM(hours), 0), 2) AS mean_load_pct,
               COUNT(DISTINCT session_id) AS sessions
        FROM `{PROJECT}.{DATASET}.farm_a_operations`
        GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 2, 3, 5""",
    "farm_a_fields.csv": f"""
        SELECT field_id, hull_area_ha, ARRAY_LENGTH(source_files) AS n_field_files,
               ARRAY_TO_STRING(ARRAY(SELECT DISTINCT s.tractor_id FROM UNNEST(source_files) s ORDER BY 1), '|') AS tractors,
               ARRAY_TO_STRING(ARRAY(SELECT DISTINCT s.work_type FROM UNNEST(source_files) s ORDER BY 1), '|') AS work_types
        FROM `{PROJECT}.{DATASET}.farm_a_fields_geo` ORDER BY field_id""",
}


def export(r: Runner) -> None:
    for name, sql in EXPORTS.items():
        out = r.sql(sql, fmt="csv")
        if r.apply:
            (AGG / name).write_text(out.replace("\r\n", "\n"), encoding="utf-8")
            print(f"  wrote data/aggregated/{name} ({max(out.count(chr(10)) - 1, 0)} rows)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    ap.add_argument("--steps", default=",".join(STEPS), help="comma-separated subset of steps")
    args = ap.parse_args()
    steps = args.steps.split(",")
    unknown = set(steps) - set(STEPS)
    if unknown:
        sys.exit(f"unknown steps: {unknown}")

    r = Runner(apply=args.apply)
    print(f"{'APPLY' if args.apply else 'DRY RUN'}: project={PROJECT} region={REGION} "
          f"bucket=gs://{BUCKET} dataset={DATASET}")
    for step in STEPS:
        if step in steps:
            print(f"\n== {step}")
            globals()[step](r)
    print("\ndone" if args.apply else "\ndry run complete: nothing was changed in GCP")


if __name__ == "__main__":
    main()
