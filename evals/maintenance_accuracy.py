"""P2b workshop-sheet accuracy: Gemini's stored readings of the job sheets vs the ground truth they were drawn from.

Scores each field over the sheets read, how many sheets get the expected code verdict (the planted sheet "differs",
every other one "matches_log"), and whether the planted keying error (MNT-0022 hours) was found.

Run: python -m evals.maintenance_accuracy        (reads data/fleet/maintenance_sheets/extractions/*.json)
"""
from __future__ import annotations

import json

from backend.tools import read_maintenance as rm

FIELDS = ("sheet_number", "date", "machine_id", "service_type", "hours_at_service", "cost_gbp")
TOLERANCE = {"hours_at_service": rm.HOURS_TOLERANCE, "cost_gbp": 0.005}


def _right(field: str, read: dict, truth) -> bool:
    got, want = read.get(field), getattr(truth, field)
    if field in TOLERANCE:
        return isinstance(got, (int, float)) and abs(got - float(want)) <= TOLERANCE[field] + 1e-9
    if field == "service_type":
        return rm._same_text(got, want)
    return got == want


def score(readings: dict[str, dict]) -> dict:
    """`readings` maps sheet id to what Gemini read (the `extracted` part of a stored reading)."""
    t, planted = rm.ground_truth(), rm.planted().set_index("sheet_id")
    read = [s for s in t.index if s in readings]
    per_sheet = {s: {f: _right(f, readings[s], t.loc[s]) for f in FIELDS} for s in read}
    verdicts = {s: rm.check_sheet(readings[s]) for s in read}
    expected = sum(v["verdict"] == ("differs" if s in planted.index else "matches_log") for s, v in verdicts.items())
    found = all(any(d["field"] == planted.field[s] for d in verdicts[s]["differences"]) for s in planted.index
                if s in verdicts) if any(s in verdicts for s in planted.index) else None
    return {"sheets": len(t), "read": len(read),
            "field_accuracy": {f: sum(r[f] for r in per_sheet.values()) / len(read) for f in FIELDS} if read else {},
            "expected_verdict": expected, "planted_found": found, "per_sheet": per_sheet}


def load_readings() -> dict[str, dict]:
    return rm.load_readings()


def token_usage() -> dict | None:
    return rm.token_usage()


if __name__ == "__main__":
    print(json.dumps({**score(load_readings()), "tokens": token_usage()}, indent=2))
