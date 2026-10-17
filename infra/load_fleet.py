"""Load the fleet tables into BigQuery: data/fleet/*.csv -> fleet_<name> tables, then the fleet views.

Dry run by default: prints every command and touches nothing. Pass --apply to execute.
Re-runnable: each table is emptied and reloaded, so running it twice gives the same result.
Needs the ref_* tables and views from infra/load_gcp.py (v_farm_a_settings) to exist already.

  python infra/load_fleet.py                 # dry run
  python infra/load_fleet.py --apply         # load, create views, check row counts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infra.load_gcp import DATASET, PROJECT, REGION, Runner, render  # noqa: E402

FLEET = ROOT / "data" / "fleet"
DDL = ROOT / "backend" / "emissions" / "ddl" / "002_fleet_tables.sql"
VIEWS = ROOT / "backend" / "emissions" / "views" / "030_fleet_views.sql"
# ground_truth_*.csv are for evals only and are never loaded.
TABLES = ["sites", "machines", "operations", "clients", "fields", "operators", "jobs", "other_activity", "depots",
          "fuel_deliveries", "fuel_dispenses", "depot_stock_readings", "maintenance_events", "actions", "action_overlay"]


def load(r: Runner) -> None:
    r.sql(render(DDL))
    for name in TABLES:
        r.sql(f"TRUNCATE TABLE `{PROJECT}.{DATASET}.fleet_{name}`")
        r.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "load", "--source_format=CSV",
               "--skip_leading_rows=1", "--allow_quoted_newlines", f"{DATASET}.fleet_{name}", str(FLEET / f"{name}.csv")])


def views(r: Runner) -> None:
    r.sql(render(VIEWS))


def verify(r: Runner) -> None:
    counts = " UNION ALL ".join(f"SELECT 'fleet_{n}' AS t, COUNT(*) AS n FROM `{PROJECT}.{DATASET}.fleet_{n}`" for n in TABLES)
    out = r.sql(counts, fmt="json")
    if not r.apply:
        return
    loaded = {row["t"]: int(row["n"]) for row in json.loads(out)}
    wrong = {f"fleet_{n}": (loaded.get(f"fleet_{n}"), len(pd.read_csv(FLEET / f"{n}.csv"))) for n in TABLES
             if loaded.get(f"fleet_{n}") != len(pd.read_csv(FLEET / f"{n}.csv"))}
    if wrong:
        sys.exit(f"row counts differ (table: loaded, csv): {wrong}")
    print(f"  all {len(TABLES)} tables have the same row count as their CSV")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="execute (default: print the commands only)")
    args = ap.parse_args()
    r = Runner(args.apply)
    print(f"{'APPLY' if args.apply else 'DRY RUN'}: {PROJECT}.{DATASET}")
    for step in (load, views, verify):
        print(f"[{step.__name__}]")
        step(r)


if __name__ == "__main__":
    main()
