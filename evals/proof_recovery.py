"""Proof recovery: does action_impact find the effect planted in the demo, and stay quiet where none was planted?

The tool never reads the answer file; only this eval does.
Run: python -m evals.proof_recovery
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.tools.action_impact import action_impact

ROOT = Path(__file__).resolve().parents[1]


def _recovered(planted: float, result: dict) -> bool:
    change = result["change_pct"]
    if change is None:
        return False
    if planted == 0:
        return result["status"] == "cant_tell_yet" and change["low"] <= 0 <= change["high"]
    return result["status"] == "reduction_shown" and change["low"] <= planted <= change["high"]


def score() -> dict:
    truth = pd.read_csv(ROOT / "data" / "fleet" / "ground_truth_actions.csv").set_index("action_id").planted_effect_pct
    rows = []
    for r in action_impact()["actions"]:
        planted = float(truth[r["action"]["action_id"]])
        c = r["change_pct"]
        rows.append({"action_id": r["action"]["action_id"], "planted_effect_pct": planted, "status": r["status"],
                     "low": None if c is None else round(c["low"], 1), "high": None if c is None else round(c["high"], 1),
                     "recovered": _recovered(planted, r)})
    return {"changes": len(rows), "recovered": sum(r["recovered"] for r in rows), "rows": rows,
            "note": "action_impact works from the job records; it never reads the answer file."}


if __name__ == "__main__":
    print(score())
