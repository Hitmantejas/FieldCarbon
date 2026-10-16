"""Eval harness: one command for every FieldCarbon evaluation, with a summary for the README.

  python -m evals.run_all        -> evals/results/summary.json and evals/results/summary.md

Tool-level evals run today. Agent-level evals score recorded runs (backend/agent/runs.py): tool selection,
numerical faithfulness (the auditor), citation and label coverage. Hand-written sample runs test the
harness itself and are reported separately, never as agent results.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.agent.coverage import citation_coverage, label_coverage
from backend.agent.faithfulness import audit
from backend.agent.runs import load_runs
from backend.tools.contracts import LABELS
from evals.checks import CASES, TOOLS, figures, run_case

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"


def tool_cases() -> dict:
    results, outputs = [], []
    for case in CASES:
        try:
            outputs.append(run_case(case))
            results.append({"id": case["id"], "passed": True})
        except Exception as e:  # noqa: BLE001 - a failing case is a result, not a crash
            results.append({"id": case["id"], "passed": False, "error": f"{type(e).__name__}: {e}"[:200]})
    figs = [f for out in outputs for f in figures(out)]
    labelled = [f for f in figs if f["label"] in LABELS + ("excluded",) and f["source_ids"]]
    return {"cases": len(results), "passed": sum(r["passed"] for r in results),
            "label_and_source_coverage": round(len(labelled) / len(figs), 4) if figs else None,
            "figures_checked": len(figs), "failures": [r for r in results if not r["passed"]]}


def _outputs(run: dict) -> list:
    """Recorded outputs; a run without them (hand-written samples) re-runs the deterministic tools."""
    return [c["output"] if c.get("output") is not None else TOOLS[c["name"]](**c.get("args", {}))
            for c in run["tool_calls"]]


def score_run(run: dict) -> dict:
    case = next((c for c in CASES if c["id"] == run.get("case_id")), None)
    outputs = _outputs(run)
    called = {c["name"] for c in run["tool_calls"]}
    a = audit(run["answer"], outputs, run.get("question", ""))
    lab, figs = label_coverage(run["answer"])
    cit, named = citation_coverage(run["answer"], outputs)
    return {"case_id": run.get("case_id"), "sample": bool(run.get("sample")),
            "tool_selection": None if case is None else set(case["expected_tools"]) <= called,
            "faithful": a.faithful, "numbers": a.checked, "unmatched": [n.text for n in a.unmatched],
            "labelled_figures": lab, "figures": figs, "cited": cit, "recommendations_named": named}


def _rate(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r[key] is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _share(rows: list[dict], part: str, whole: str) -> float | None:
    total = sum(r[whole] for r in rows)
    return round(sum(r[part] for r in rows) / total, 3) if total else None


def agent_tokens(runs: list[dict]) -> dict | None:
    """Tokens Vertex AI reported, over the agent runs that recorded them (runs recorded before 2026-10-14 did not)."""
    counted = [r["tokens"] for r in runs if not r.get("sample") and r.get("tokens")]
    if not counted:
        return None
    total = {k: sum(t.get(k, 0) for t in counted) for k in ("input", "output", "thinking")}
    return {"runs": len(counted), **total, "per_question": round(sum(total.values()) / len(counted))}


def agent_runs() -> dict:
    runs = load_runs()
    scored = [score_run(r) for r in runs]
    out = {}
    for name, rows in (("agent", [r for r in scored if not r["sample"]]), ("self_test", [r for r in scored if r["sample"]])):
        out[name] = {"runs": len(rows), "tool_selection": _rate(rows, "tool_selection"),
                     "faithfulness": _rate(rows, "faithful"), "label_coverage": _share(rows, "labelled_figures", "figures"),
                     "citation_coverage": _share(rows, "cited", "recommendations_named"), "details": rows}
    out["agent"]["tokens"] = agent_tokens(runs)
    return out


def other_evals() -> dict:
    from evals import fleet_detection, fleet_diagnosis, range_coverage, receipt_accuracy, upload_check

    out = {"fleet_detection": fleet_detection.score()}
    fdx = fleet_diagnosis.score()
    out["fleet_diagnosis"] = {k: v for k, v in fdx.items() if k != "results"}
    uc = upload_check.score()
    out["upload_check"] = {k: v for k, v in uc.items() if k != "results"}
    rc = range_coverage.coverage()
    out["range_coverage"] = {k: v for k, v in rc.items() if k != "rows"}
    out["receipt_accuracy"] = {}
    for farm in ("b", "fleet", "fleet_demo"):
        readings = receipt_accuracy.load_extractions(farm)
        out["receipt_accuracy"][farm] = ({k: v for k, v in receipt_accuracy.score(readings, farm).items()
                                          if k != "per_document"} if readings else "not run yet")
        if readings:
            out["receipt_accuracy"][farm]["tokens"] = receipt_accuracy.token_usage(farm)
    return out


def markdown(s: dict) -> str:
    t, a, st, o = s["tool_cases"], s["agent_runs"]["agent"], s["agent_runs"]["self_test"], s["other"]
    fd, rc, uc = o["fleet_detection"], o["range_coverage"], o["upload_check"]
    pct = lambda v: "n/a" if v is None else f"{100 * v:.0f}%"  # noqa: E731
    reading = lambda r: r if isinstance(r, str) else pct(r["field_accuracy"].get("litres"))  # noqa: E731
    rows = [
        ("Tool eval cases", f"{t['passed']} of {t['cases']} pass"),
        ("Figures with a confidence label and sources", f"{pct(t['label_and_source_coverage'])} of {t['figures_checked']}"),
        ("Planted fuel problems found", f"{fd.get('found', fd.get('detected', '?'))} of {fd.get('planted', fd.get('total', '?'))}"),
        ("Planted problems whose top supported cause is the planted one",
         f"{o['fleet_diagnosis']['correct']} of {o['fleet_diagnosis']['planted']}"),
        ("Receipts-only ranges containing the telemetry truth",
         f"{rc['operations_inside']} of {rc['operations']} jobs ({pct(rc['coverage_by_litres'])} of litres)"),
        ("Gemini reading accuracy, Farm B receipts (litres)", reading(o["receipt_accuracy"]["b"])),
        ("Gemini reading accuracy, fleet delivery notes (litres)", reading(o["receipt_accuracy"]["fleet"])),
        ("Gemini reading accuracy, upload demo notes (litres)", reading(o["receipt_accuracy"]["fleet_demo"])),
        ("Uploaded-note check: expected verdict, perfect reading", f"{uc['expected_met']} of {uc['notes']} demo notes"),
        ("Uploaded-note check: expected verdict, Gemini's reading",
         f"{uc['expected_met_on_gemini_reading']} of {uc['gemini_read']} demo notes" if uc["gemini_read"] else "not run yet"),
        ("Agent runs scored", str(a["runs"])),
        ("Agent tool selection", pct(a["tool_selection"])),
        ("Agent numerical faithfulness", pct(a["faithfulness"])),
        ("Agent label coverage", pct(a["label_coverage"])),
        ("Agent citation coverage (ideas that name their research source)", pct(a["citation_coverage"])),
        ("Agent tokens per question (input + output + thinking)",
         f"{a['tokens']['per_question']:,} over {a['tokens']['runs']} runs" if a["tokens"] else "not recorded yet"),
        ("Harness self-test (hand-written samples)",
         f"{st['runs']} runs; auditor flags {sum(1 for r in st['details'] if not r['faithful'])} unfaithful"),
    ]
    return "| Evaluation | Result |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows) + "\n"


def run_all() -> dict:
    summary = {"tool_cases": tool_cases(), "agent_runs": agent_runs(), "other": other_evals()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    (RESULTS / "summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(markdown(run_all()))
