"""Fleet diagnosis: for each planted problem, is the top-ranked supported cause the one that was planted?

The diagnosis never sees the answer file; only this eval does (same rule as evals/fleet_detection.py).
Run: python -m evals.fleet_diagnosis
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backend.tools.diagnose_anomaly import diagnose_anomaly
from backend.tools.reconcile_fuel import reconcile_fuel
from evals.fleet_detection import _matches

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results" / "fleet_diagnosis.json"


def score(write: bool = True) -> dict:
    truth = pd.read_csv(ROOT / "data" / "fleet" / "ground_truth_anomalies.csv")
    findings = reconcile_fuel()["findings"]
    rows = []
    for t in truth.itertuples():
        f = next((f for f in findings if _matches(t, f)), None)
        top = None
        if f is not None:
            supported = [h for h in diagnose_anomaly(f["id"])["hypotheses"] if h["status"] == "supported"]
            top = supported[0]["id"] if supported else None
        rows.append({"anomaly_id": t.anomaly_id, "kind": t.kind, "finding_id": f and f["id"], "true_cause": t.true_cause,
                     "top_supported": top, "correct": top == t.true_cause})
    correct = sum(r["correct"] for r in rows)
    result = {"planted": len(rows), "correct": correct, "accuracy": correct / len(rows), "results": rows,
              "note": "diagnose_anomaly tests causes from the logs and the machines' fuel data; it never reads the answer file."}
    if write:
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(score(), indent=2))
