"""Read fuel documents (Farm B receipts or the fleet's delivery notes) with Gemini, validate them and load both tables into BigQuery.

Dry run by default: prints every command and touches nothing (Gemini is not called either).
Stored readings in data/synthetic/farm_b/extractions/ are reused; only missing ones call Gemini.

  python infra/run_receipts.py --model gemini-3.5-flash --location <endpoint>            # dry run
  python infra/run_receipts.py --model gemini-3.5-flash --location <endpoint> --apply
  python infra/run_receipts.py --apply --steps validate,score                            # offline steps

Steps: preflight, upload, extract, validate, recreate_validated, load, score
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.tools.extract_receipt import FARM_RECEIPTS, IMAGE_FOLDERS, cache_path, read_receipt, validate_farm  # noqa: E402
from evals.receipt_accuracy import main as score_main  # noqa: E402
from infra.load_gcp import BUCKET, DATASET, DDL, PROJECT, REGION, Runner, preflight, render  # noqa: E402

STEPS = ["preflight", "upload", "extract", "validate", "recreate_validated", "load", "score"]


def receipt_ids(farm: str) -> list[str]:
    return sorted(p.stem for p in (FARM_RECEIPTS[farm] / "receipts").glob("*.jpg"))


def upload(r: Runner, args) -> None:
    r.run(["gcloud", "storage", "rsync", str(FARM_RECEIPTS[args.farm] / "receipts"), f"gs://{BUCKET}/receipts/{args.farm}/",
           "--checksums-only"])


def extract(r: Runner, args) -> None:
    todo = [rid for rid in receipt_ids(args.farm) if args.refresh or not cache_path(args.farm, rid).exists()]
    print(f"  {len(receipt_ids(args.farm)) - len(todo)} stored readings reused; {len(todo)} to read with "
          f"{args.model} on Vertex AI endpoint '{args.location}'")
    for rid in todo:
        if not r.apply:
            print(f"  [dry-run] Gemini {args.model} @ {args.location}: read receipts/{rid}.jpg")
            continue
        raw = read_receipt(rid, args.farm, model=args.model, location=args.location, refresh=args.refresh)
        lines = raw.extracted.get("lines") or []
        print(f"  {rid}: {len(lines)} line(s), litres {[l.get('litres') for l in lines]}")


def validate(r: Runner, args) -> None:
    lines = validate_farm(args.farm)
    counts: dict[str, int] = {}
    for l in lines:
        counts[l.outcome] = counts.get(l.outcome, 0) + 1
    print(f"  {len(lines)} lines: {counts}")
    for l in lines:
        if l.outcome != "accepted":
            print(f"  {l.receipt_id}/{l.line_no} {l.outcome}: {'; '.join(l.reasons)}")


def recreate_validated(r: Runner, args) -> None:
    """receipts_validated changed from one row per document to one per line. Only drop it when empty."""
    table = f"{PROJECT}.{DATASET}.receipts_validated"
    out = r.sql(f"SELECT COUNT(*) AS n FROM `{table}`", fmt="csv")
    if r.apply and out.strip().splitlines()[-1] != "0":
        sys.exit(f"{table} is not empty; refusing to drop it")
    r.sql(f"DROP TABLE IF EXISTS `{table}`")
    r.sql(render(DDL))


def _ndjson(rows: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    f.write("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n")
    f.close()
    return Path(f.name)


def _iso_date(text) -> str | None:
    try:
        return date.fromisoformat(str(text)).isoformat()
    except ValueError:
        return None


def load(r: Runner, args) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raws = [read_receipt(rid, args.farm) for rid in receipt_ids(args.farm) if cache_path(args.farm, rid).exists()]
    raw_rows = [{"receipt_id": x.receipt_id, "farm_id": x.farm_id,
                 "gcs_uri": f"gs://{BUCKET}/receipts/{args.farm}/{Path(x.image).name}", "model_id": x.model_id,
                 "location": x.location, "prompt_version": x.prompt_version, "extracted": x.extracted,
                 "field_confidence": x.extracted.get("confidence") or {}, "extracted_at": x.extracted_at}
                for x in raws]
    # A misread date stays as text in receipts_raw; the DATE column gets null rather than failing the load.
    val_rows = [{**asdict(l), "reasons": list(l.reasons), "delivery_date": _iso_date(l.delivery_date),
                 "validated_at": now} for l in validate_farm(args.farm)]
    print(f"  {len(raw_rows)} raw rows, {len(val_rows)} validated rows (replacing {args.farm}'s rows only)")
    for table, rows in (("receipts_raw", raw_rows), ("receipts_validated", val_rows)):
        # Both document sets share these tables: replace this set's rows only.
        r.sql(f"DELETE FROM `{PROJECT}.{DATASET}.{table}` WHERE farm_id = '{args.farm}'")
        path = _ndjson(rows) if r.apply else Path(f"<{table}.json>")
        r.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "load",
               "--source_format=NEWLINE_DELIMITED_JSON", f"{DATASET}.{table}", str(path)])


def score(r: Runner, args) -> None:
    score_main()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    ap.add_argument("--steps", default=",".join(STEPS), help="comma-separated subset of steps")
    ap.add_argument("--model", help="pinned Gemini model id, e.g. gemini-3.5-flash")
    ap.add_argument("--location", help="Vertex AI endpoint for Gemini, e.g. global or us-central1")
    ap.add_argument("--refresh", action="store_true", help="re-read receipts that already have a stored reading")
    ap.add_argument("--farm", choices=sorted(set(FARM_RECEIPTS) - set(IMAGE_FOLDERS)), default="b",
                    help="which documents: b = Farm B receipts, fleet = the fleet's delivery notes "
                         "(the upload demo notes are read by python -m backend.tools.upload_note)")
    args = ap.parse_args()
    steps = args.steps.split(",")
    if set(steps) - set(STEPS):
        sys.exit(f"unknown steps: {set(steps) - set(STEPS)}")
    if "extract" in steps and not (args.model and args.location):
        sys.exit("extract needs --model and --location (the Gemini endpoint is a team decision)")
    r = Runner(apply=args.apply)
    print(f"{'APPLY' if args.apply else 'DRY RUN'} ({args.farm}): project={PROJECT} bigquery={REGION} bucket=gs://{BUCKET} "
          f"gemini={args.model}@{args.location}")
    for step in STEPS:
        if step in steps:
            print(f"\n== {step}")
            if step == "preflight":
                preflight(r)
            else:
                globals()[step](r, args)
    print("\ndone" if args.apply else "\ndry run complete: nothing was changed in GCP and Gemini was not called")


if __name__ == "__main__":
    main()
