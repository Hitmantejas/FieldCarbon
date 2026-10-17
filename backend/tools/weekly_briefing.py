"""F6 weekly briefing: the three things a fleet manager should look at first, chosen by fixed rules.

Candidates come from the other tools (fuel control, delivery notes, recorder data, peer benchmarks, ideas). They are
ordered by severity, then size (the figure, or the low end of a range), then id, and the briefing takes up to three with
at most one per family while other families are left. Every item carries its tool's figure (label, sources, how) and
fixed texts: why it matters, the next step and what would improve it. No model is involved here; Gemini may only write
the short intro (backend/agent/briefing_text.py). The data covers the company year, so the period says so.
"""
from __future__ import annotations

import importlib
import json

from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.check_delivery_notes import check_delivery_notes
from backend.tools.data_quality import data_quality
from backend.tools.detect_anomalies import _severity, detect_anomalies
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.reconcile_fuel import reconcile_fuel

HEADING = "Week summary"
PERIOD = "company year to date (May 2025 to April 2026)"
RULES = ("Up to three items: most severe first, then the largest figure; at most one per topic while other topics are "
         "left. Chosen by code, not by Gemini.")
MAX_ITEMS = 3
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
# Tools added later (carbon ledger, proof of impact) join by exposing briefing_candidates(); missing ones are skipped.
OPTIONAL_TOOLS = ("backend.tools.carbon_ledger", "backend.tools.action_impact")

NOTE_KINDS = ("entered_twice", "price_differs", "litres_differ", "note_not_in_log", "log_row_without_note", "note_needs_review")
INVOICE = "The supplier's invoice for that note number."
PEERS = "Soil and tool details for the jobs that stand out."
FRESH_EXPORT = "A fresh export from the machine that stopped reporting."
NIGHT = "A key-fob or job record for the night dispenses."
CHECK_NOTE = "Check the note against the supplier's invoice and correct the fuel log."

WOULD_IMPROVE = {
    "stock_gap": "A tank dip reading before the next delivery would show whether the gap is still growing.",
    "stock_surplus": "A tank dip reading before the next delivery would show whether the gap is still growing.",
    "machine_over_dispense": NIGHT, "night_dispense": NIGHT,
    "machine_under_dispense": "A record of fill-ups away from the depot.",
    "duplicate_delivery_note": INVOICE, **dict.fromkeys(NOTE_KINDS, INVOICE),
    "note_needs_review": "A clearer photo of the note.",
    "job_outlier": PEERS, "high_non_work_share": PEERS, "benchmark": PEERS,
    "opportunity": "Answers to the open questions on the Opportunities screen (for example tyre pressure checked).",
    "data_gap": FRESH_EXPORT, "data_quality": FRESH_EXPORT,
}

WHY = {
    "duplicate_delivery_note": "Counting a delivery twice makes the books show fuel that never arrived.",
    "entered_twice": "Counting a delivery twice makes the books show fuel that never arrived.",
    "stock_gap": "Fuel that is paid for but not in the tank is lost money, and nothing in the logs explains it yet.",
    "stock_surplus": "More fuel than the books show usually means a delivery is missing from the log.",
    "machine_over_dispense": "Fuel handed to a machine that it did not burn has gone somewhere else.",
    "night_dispense": "Fuel taken when no job was running is hard to account for.",
    "machine_under_dispense": "Fuel burned that was never handed out means a fill-up is missing from the log.",
    "price_differs": "A wrong price changes the fuel cost charged to clients.",
    "litres_differ": "Wrong litres change the stock and the fuel charged to clients.",
    "note_not_in_log": "A delivery missing from the log makes the depot's stock look short.",
    "log_row_without_note": "A log entry with no paperwork cannot be traced to a delivery.",
    "note_needs_review": "A note that cannot be read with confidence cannot be checked against the log.",
    "data_gap": "Hours with no real data hide fuel that was burned, so the fleet's total may be too low.",
    "data_quality": "Hours with no real data hide fuel that was burned, so the fleet's total may be too low.",
    "job_outlier": "A job that burned far more or less than usual may point to the ground, the tool or a fault.",
    "high_non_work_share": "Fuel burned while idling, on the road or with a tool not working does no field work.",
    "benchmark": "A machine that burns more than its peers for the same job may be set up or driven differently.",
    "opportunity": "This is the idea with the strongest evidence that suits the fleet; the saving is a range from research.",
}

NEXT = {
    "duplicate_delivery_note": "Check the supplier's invoice, then remove the second entry from the fuel log.",
    "entered_twice": "Check the supplier's invoice, then remove the second entry from the fuel log.",
    "stock_gap": "Open Diagnose on this finding in Fuel control, then take a tank reading.",
    "stock_surplus": "Look for a delivery note that is missing from the fuel log.",
    "machine_over_dispense": "Open Diagnose on this finding in Fuel control and check the pump records for those days.",
    "night_dispense": "Check the pump records for the night dispenses.",
    "machine_under_dispense": "Find where the extra fuel came from: a field tank or a fill-up that was not logged.",
    **dict.fromkeys(NOTE_KINDS[1:], CHECK_NOTE),
    "data_gap": "Check this tractor's recorder and its connection, then export its data again.",
    "data_quality": "Check the recorders that froze and export their data again.",
    "job_outlier": "Open Diagnose on this job in Fuel control, then compare it with its job notes.",
    "high_non_work_share": "Open Diagnose on this tractor in Fuel control and look at how it is used between jobs.",
    "benchmark": "Compare these jobs with the others: the tool, the field and the way it was driven.",
    "opportunity": "Answer the open questions on the Opportunities screen, then try the idea on one machine.",
}

LINKS = {"control": "#/control", "data": "#/control", "benchmark": "#/control", "opportunity": "#/opportunities"}
KIND_LINKS = {"benchmark": "#/sites"}

# Family defaults, so a candidate from a later tool still gets every text.
FAMILY_TEXT = {
    "control": (WHY["stock_gap"], "Open the finding in Fuel control.", "A tank dip reading before the next delivery."),
    "data": (WHY["data_gap"], NEXT["data_quality"], FRESH_EXPORT),
    "benchmark": (WHY["benchmark"], NEXT["benchmark"], PEERS),
    "opportunity": (WHY["opportunity"], NEXT["opportunity"], WOULD_IMPROVE["opportunity"]),
}
DEFAULT_TEXT = ("It is one of the largest figures in the data.", "Open the screen it links to.",
                "More measured data for the figure.")


def _plain(value):
    """Tuples and numpy numbers become plain JSON."""
    return json.loads(json.dumps(value, default=float))


def _cand(cid: str, family: str, kind: str, severity: str, title: str, figure: dict, link: str | None = None) -> dict:
    return {"id": cid, "family": family, "kind": kind, "severity": severity, "title": title, "figure": _plain(figure),
            "link": link or KIND_LINKS.get(kind) or LINKS.get(family, "#/overview")}


def size(c: dict) -> float:
    """The figure, or the low end of a range."""
    f = c["figure"]
    v = f["value"] if f["value"] is not None else f.get("low")
    return float(v or 0)


def _severity_of(figure: dict) -> str:
    return _severity(size({"figure": figure}), "h" if figure["unit"] == "h" else "L")


def candidates() -> list[dict]:
    """Every possible item from the other tools, unordered."""
    out = []
    recon = reconcile_fuel()["findings"]
    out += [_cand(f["id"], "control", f["kind"], f["severity"], f["title"], f["litres"]) for f in recon]
    duplicates = {f.get("doc_no") for f in recon if f["kind"] == "duplicate_delivery_note"}
    out += [_cand(f"note:{f['kind']}:{f['doc_no']}", "control", f["kind"], f["severity"], f["title"], f["figure"])
            for f in check_delivery_notes()["findings"] if f["figure"] is not None and f["doc_no"] not in duplicates]

    anomalies = detect_anomalies()["findings"]
    gaps = [f for f in anomalies if f["kind"] == "data_gap"]
    out += [_cand(f["id"], "data", "data_gap", f["severity"], f["title"], f["litres"]) for f in gaps]
    frozen = data_quality()["frozen_hours"]
    if not gaps and frozen["value"]:
        out.append(_cand("data_quality:frozen_hours", "data", "data_quality", _severity_of(frozen),
                         f"Recorders froze for {frozen['value']:,.0f} hours in total", frozen))
    out += [_cand(f["id"], "benchmark", f["kind"], f["severity"], f["title"], f["litres"]) for f in anomalies
            if f["kind"] in ("job_outlier", "high_non_work_share")]

    for g in benchmark_peers()["groups"]:
        stake = g["litres_at_stake"]
        if stake is None:
            continue
        n = sum(p["above_peers"] for p in g["peers"])
        title = (f"{n} {'machine burns' if n == 1 else 'machines burn'} more per hectare than their peers for "
                 f"{g['operation'].lower()} at {g['site']}")
        out.append(_cand(f"benchmark:{g['site_id']}:{g['operation_code']}", "benchmark", "benchmark", _severity_of(stake), title, stake))

    feasible = [i for i in fleet_opportunities()["ideas"] if i["state"] == "feasible" and i["figures"].get("litres_saved")]
    if feasible:
        top = feasible[0]
        saved = top["figures"]["litres_saved"]
        out.append(_cand(f"opportunity:{top['intervention_id']}", "opportunity", "opportunity", _severity_of(saved),
                         f"Idea: {top['name']} ({top['robustness']} evidence from research)", saved))

    for name in OPTIONAL_TOOLS:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        out += [_plain(c) for c in module.briefing_candidates()]
    return out


def ordered(cands: list[dict]) -> list[dict]:
    """Severity, then size (largest first), then id, so the order never depends on the input order."""
    return sorted(cands, key=lambda c: (SEVERITY_ORDER[c["severity"]], -size(c), c["id"]))


def choose(cands: list[dict], n: int = MAX_ITEMS) -> list[dict]:
    """Up to n, at most one per family while other families are left; then filled from the ordered list."""
    ranked = ordered(cands)
    chosen, families = [], set()
    for c in ranked:
        if len(chosen) < n and c["family"] not in families:
            chosen.append(c)
            families.add(c["family"])
    for c in ranked:
        if len(chosen) < n and c not in chosen:
            chosen.append(c)
    return ordered(chosen)


def item(c: dict) -> dict:
    """The candidate with its fixed texts."""
    why, step, improve = FAMILY_TEXT.get(c["family"], DEFAULT_TEXT)
    k = c["kind"]
    return {**c, "why_it_matters": WHY.get(k, why), "next_step": NEXT.get(k, step), "would_improve": WOULD_IMPROVE.get(k, improve)}


def weekly_briefing() -> dict:
    """{heading, period, rules, items: [{id, family, kind, severity, title, figure, why_it_matters, next_step,
    would_improve, link}], candidates}. Same data, same items."""
    cands = candidates()
    return {"heading": HEADING, "period": PERIOD, "rules": RULES, "items": [item(c) for c in choose(cands)],
            "candidates": len(cands)}
