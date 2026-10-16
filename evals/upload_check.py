"""Upload check (F7): does each of the four demo notes get its expected verdict and finding?

Scored twice per note: on the ground truth (what the note says, a perfect reading) and, once stored, on Gemini's own
reading of the image with the upload prompt (python -m backend.tools.upload_note). The check never sees the expected
verdicts; only this eval does.
Run: python -m evals.upload_check
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backend.receipts.ground_truth import ground_truth_extractions
from backend.tools.extract_receipt import FARM_RECEIPTS
from backend.tools.upload_note import check_uploaded_note
from evals.receipt_accuracy import load_extractions

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results" / "upload_check.json"


def _outcome(extracted: dict | None) -> dict | None:
    if extracted is None:
        return None
    r = check_uploaded_note(extracted)
    return {"verdict": r["verdict"], "findings": [f["kind"] for f in r["findings"]]}


def _met(outcome: dict | None, verdict: str, kind: str) -> bool | None:
    if outcome is None:
        return None
    return outcome["verdict"] == verdict and outcome["findings"] == ([kind] if kind else [])


def score() -> dict:
    expected = pd.read_csv(FARM_RECEIPTS["fleet_demo"] / "expected_verdicts.csv", keep_default_na=False)
    truth, read = ground_truth_extractions("fleet_demo"), load_extractions("fleet_demo")
    rows = []
    for e in expected.itertuples():
        on_truth, on_read = _outcome(truth[e.note]), _outcome(read.get(e.note))
        rows.append({"note": e.note, "change": e.change, "expected_verdict": e.expected_verdict,
                     "expected_finding": e.expected_finding or None,
                     "ground_truth": on_truth, "met_on_ground_truth": _met(on_truth, e.expected_verdict, e.expected_finding),
                     "gemini_reading": on_read, "met_on_gemini_reading": _met(on_read, e.expected_verdict, e.expected_finding)})
    read_rows = [r for r in rows if r["gemini_reading"] is not None]
    return {"notes": len(rows), "expected_met": sum(bool(r["met_on_ground_truth"]) for r in rows),
            "gemini_read": len(read_rows), "expected_met_on_gemini_reading": sum(bool(r["met_on_gemini_reading"]) for r in read_rows),
            "results": rows,
            "note": "check_uploaded_note works from the note and the fuel log; it never reads the expected verdicts. "
                    "Synthetic demo documents."}


if __name__ == "__main__":
    result = score()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
