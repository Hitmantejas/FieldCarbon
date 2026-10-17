"""The trust scoreboard: what we test, how it scored, and where we are less sure. Reads the results of `python -m evals.run_all`."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SUMMARY = Path(__file__).resolve().parents[2] / "evals" / "results" / "summary.json"

LIMITS = (
    "The fleet, the operators, clients, fuel deliveries and the two logged changes are made up. The tests show the methods work. They do not show how the app will score on your own fleet.",
    "The receipts and delivery notes we read are images we made, with damage added. Reading every one correctly shows the process works. It does not mean every real receipt will be read right.",
    "Gemini gives different answers on different runs. If you run the analyst's questions again, the score can come out a little lower. An answer with a number that cannot be traced carries a \"Check needed\" note.",
    "An analyst answer that fails a check is rewritten once, and the score is counted after that rewrite.",
    "Savings come from published studies, mostly on arable land in other countries. They are ranges, not promises.",
)


def _pct(v: float | None) -> str:
    return "not run" if v is None else f"{100 * v:.0f}%"


def _status(ok: bool) -> str:
    return "pass" if ok else "partial"


def _check(group: str, question: str, result: str, detail: str, ok: bool) -> dict:
    return {"group": group, "question": question, "result": result, "detail": detail, "status": _status(ok)}


def _documents(group: str, question: str, r, what: str) -> dict:
    if isinstance(r, str):
        return {"group": group, "question": question, "result": "not run yet", "detail": f"Run the {what} reading eval to fill this in.", "status": "not_run"}
    litres = r["field_accuracy"]["litres"]
    kinds = ", ".join(k.replace("_", " ") for k in r["litres_accuracy_by_damage"] if k != "clean")
    return _check(group, question, f"{r['read']} of {r['documents']} read, litres {_pct(litres)} right",
                  f"Images of {what}, including {kinds} ones. Each reading is compared with the true values.",
                  r["read"] == r["documents"] and litres == 1.0)


def trust_scoreboard() -> dict:
    if not SUMMARY.exists():
        return {"available": False, "message": "No results yet. Run python -m evals.run_all to create them.", "checks": [], "limits": [*LIMITS]}
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    t, a, o = s["tool_cases"], s["agent_runs"]["agent"], s["other"]
    fd, pr, rc = o["fleet_detection"], o["proof_recovery"], o["range_coverage"]
    worst = max(rc["misses"], key=lambda m: m["miss_pct"], default=None)
    n = a["runs"]

    checks = [
        _check("The numbers", "Do the tools give the right answers?", f"{t['passed']} of {t['cases']} test questions pass",
               "Each tool is run on a fixed question and its answer is checked against a known result.", t["passed"] == t["cases"]),
        _check("The numbers", "Does every figure say how sure we are?", f"{_pct(t['label_and_source_coverage'])} of {t['figures_checked']} figures",
               "Each figure carries a label (measured, allocated or estimated) and a source.", t["label_and_source_coverage"] == 1.0),
        _check("Finding problems", "Do we find fuel problems hidden in the data?", f"{fd['found']} of {fd['planted']} found, {fd['false_alarms']} false alarms",
               "Three problems were planted: one tractor taking more fuel than it burns, fuel that left a depot without being logged, and a delivery note entered twice.",
               fd["found"] == fd["planted"] and fd["false_alarms"] == 0),
        _check("Finding problems", "Do we tell a real saving from no saving?", f"{pr['recovered']} of {pr['changes']} right",
               "A saving was planted on one logged change and none on the other. A right answer finds the saving, and says \"not clear yet\" for the other.",
               pr["recovered"] == pr["changes"]),
        _check("The analyst", "Does the analyst use the right tools?", f"{_pct(a['tool_selection'])} of {n} questions", "Each question has the tools it should call. We check they were called.", a["tool_selection"] == 1.0),
        _check("The analyst", "Can every number in its answers be traced?", f"{_pct(a['faithfulness'])} of {n} answers",
               "Each number in an answer is matched to a tool result, allowing for rounding and units.", a["faithfulness"] == 1.0),
        _check("The analyst", "Do its answers carry labels and sources?", f"Labels {_pct(a['label_coverage'])}, research sources {_pct(a['citation_coverage'])}",
               "Every figure in an answer names how sure we are. Every idea names the research it comes from.",
               a["label_coverage"] == 1.0 and a["citation_coverage"] == 1.0),
        _documents("Reading documents", "Are farm fuel receipts read correctly?", o["receipt_accuracy"]["b"], "receipts"),
        _documents("Reading documents", "Are fleet delivery notes read correctly?", o["receipt_accuracy"]["fleet"], "delivery notes"),
        _check("Where we are less sure", "Do receipts alone give the right range?", f"{rc['operations_inside']} of {rc['operations']} job types, {_pct(rc['coverage_by_litres'])} of the litres",
               "The same farm was estimated from receipts only, then compared with its telemetry."
               + (f" The worst miss was {worst['key'].replace('_', ' ')}, {worst['miss_pct']:.0f}% {worst['side']} the range." if worst else "")
               + " Receipts give a first picture. Telemetry makes it exact.",
               rc["operations_inside"] == rc["operations"]),
    ]
    updated = datetime.fromtimestamp(SUMMARY.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return {"available": True, "updated": updated, "checks": checks, "limits": [*LIMITS]}
