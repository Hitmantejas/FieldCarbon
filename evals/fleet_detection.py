"""Fleet detection: does reconcile_fuel find the three planted problems, and how many false alarms does it raise?

The tool never sees the answer file; only this eval does.
Run: python -m evals.fleet_detection
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backend.tools.reconcile_fuel import reconcile_fuel

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results" / "fleet_detection.json"


def _matches(truth, finding: dict) -> bool:
    month = str(truth.when)[:7]
    if truth.kind == "over_dispense":
        return finding["kind"] == "machine_over_dispense" and finding["machine_id"] == truth.machine_id and finding["month"] == month
    if truth.kind == "unlogged_withdrawal":
        return finding["kind"] == "stock_gap" and finding["site_id"] == truth.site_id and finding["month"] == month
    if truth.kind == "duplicate_delivery_note":
        return (finding["kind"] == "duplicate_delivery_note" and finding["site_id"] == truth.site_id
                and truth.description.split()[-1] in finding["title"])
    return False


def score() -> dict:
    truth = pd.read_csv(ROOT / "data" / "fleet" / "ground_truth_anomalies.csv")
    findings = reconcile_fuel()["findings"]
    used, rows = set(), []
    for t in truth.itertuples():
        hit = next((i for i, f in enumerate(findings) if _matches(t, f)), None)
        if hit is not None:
            used.add(hit)
        rows.append({"anomaly_id": t.anomaly_id, "kind": t.kind, "found": hit is not None,
                     "found_litres": None if hit is None else round(findings[hit]["litres"]["value"], 1)})
    found = sum(r["found"] for r in rows)
    return {"planted": len(rows), "found": found, "recall": found / len(rows),
            "false_alarms": len(findings) - len(used), "results": rows,
            "note": "reconcile_fuel works from the logs and the machines' fuel data; it never reads the answer file."}


if __name__ == "__main__":
    result = score()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
