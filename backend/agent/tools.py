"""The tools the fleet analyst agent may call.

Plain Python functions over the deterministic tools, so the model plans and explains while code does every figure
(CLAUDE.md principle 1). Names match the underlying tools, because the eval cases and recorded runs use those names.
Read-only; operators are deliberately not a parameter anywhere, so the agent cannot filter, rank or compare people.
A bad argument comes back as {"error": ...} so the model can correct itself.
"""
from __future__ import annotations

import json
from functools import wraps

from backend.tools import (benchmark_peers as _peers, check_delivery_notes as _notes, client_statement as _statement,
                           data_quality as _quality, diagnose_anomaly as _diagnose,
                           detect_anomalies as _anomalies, emissions_per_client as _clients, fleet_jobs as _jobs,
                           fleet_opportunities as _ideas, fleet_report as _report, fleet_summary as _summary, reconcile_fuel as _recon, what_if as _what_if,
                           weekly_briefing as _briefing)

MAX_JOBS = 10
MAX_ROWS = 15
FORMULA_FIGURES = {"co2e_kg", "cost_gbp", "co2e_avoided_kg"}  # their `how` is the same fixed formula on every row
KEEP_HOW = {"diagnose_anomaly", "benchmark_peers"}  # why each cause is supported; why a machine is above its peers
SCREENS = {"#/control": "Fuel control", "#/opportunities": "Opportunities", "#/sites": "Sites"}  # app links, by screen name


def _plain(value):
    """Tuples, numpy numbers and the like become plain JSON, which is what the model and the run log both need."""
    return json.loads(json.dumps(value, default=str))


def _compact(node, in_list: bool = False, key: str | None = None, keep_how: bool = False):
    """Fewer tokens for the model, same facts: rounded floats, no empty fields, no link bookkeeping, and inside lists
    no `how` text (F8 6c). Labels and sources stay on every figure; top-level figures keep `how`, and a tool in
    KEEP_HOW keeps it in lists too (except the fixed formula), because there the explanation is the answer.

    The auditor checks answers against this compact output, so a number the model quotes still traces to it.
    """
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if (v is None and k != "value") or k == "link_status" or (k == "is_manufacturer" and v is False):
                continue
            if k == "how" and in_list and (key in FORMULA_FIGURES or not keep_how):
                continue
            out[k] = _compact(v, in_list, k, keep_how)
        return out
    if isinstance(node, list):
        return [_compact(v, True, key, keep_how) for v in node]
    if isinstance(node, float) and node == node:
        return round(node, 2) if abs(node) >= 1 else float(f"{node:.3g}")
    return node


def _safe(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        try:
            return _compact(_plain(fn(*args, **kwargs)), keep_how=fn.__name__ in KEEP_HOW)
        except (ValueError, KeyError) as e:
            return {"error": f"{type(e).__name__}: {e}"}
    return run


@_safe
def fleet_summary(group_by: str = "site", site_id: str | None = None, machine_id: str | None = None,
                  client_id: str | None = None, operation_code: str | None = None, month: str | None = None) -> dict:
    """Fuel burned, CO2e and fuel cost for the fleet, grouped by site, machine, operation, month, client or field.

    group_by is one of: site, machine, operation, month, client, field. Optional filters: site_id (S1 arable site in
    Bavaria, S2 vineyard in Tuscany, S3 tillage site in Konya), machine_id (like S1-T4), client_id (like C09),
    operation_code, month (YYYY-MM, company year May 2025 to April 2026). Every figure has a confidence label.
    At most 15 rows, largest first (months in date order); the totals cover every row.
    """
    r = _summary.fleet_summary(group_by, site_id, machine_id, client_id, operation_code, None, month)
    if len(r["rows"]) > MAX_ROWS:
        r["rows_not_shown"] = len(r["rows"]) - MAX_ROWS
        r["rows"] = r["rows"][:MAX_ROWS]
    return r


@_safe
def emissions_per_client(client_id: str | None = None) -> dict:
    """Fuel, CO2e and cost for each client farm. Fuel burned outside jobs is returned separately as company overhead.

    Give client_id (like C09) to also get that client's months.
    """
    return _clients.emissions_per_client(client_id)


@_safe
def data_quality() -> dict:
    """How far to trust the data: share of fuel read from machines, fuel charged to no client, hours of frozen recorder
    data left out, and jobs without an area."""
    return _quality.data_quality()


@_safe
def reconcile_fuel() -> dict:
    """Checks fuel handed out against fuel burned, each depot's book stock against its measured stock, delivery notes
    entered twice, and night-time dispenses. Returns the findings and only the table rows that need a look. Each finding
    has an id; where diagnosable is true, pass that id to diagnose_anomaly to test its possible causes."""
    r = _recon.reconcile_fuel()
    tol = r["settings"]["stock_tolerance_l"]
    r["machine_months"] = {**r["machine_months"], "rows": [m for m in r["machine_months"]["rows"] if m["flagged"]]}
    r["depots"] = {**r["depots"], "rows": [d for d in r["depots"]["rows"] if abs(d["gap_l"]) >= tol]}
    return r


@_safe
def check_delivery_notes() -> dict:
    """Each delivery note (read by Gemini from a photo) against the fuel log: matches, differences in litres, date or
    price, notes missing from the log, and log rows with no note."""
    return _notes.check_delivery_notes()


@_safe
def detect_anomalies() -> dict:
    """Things in the machines' own data that are worth a look: recorders that froze, jobs that burned far more or less
    fuel per hour than usual, and tractors with a large share of fuel spent on idling and travel. Not proof of a fault.
    Each finding has an id (diagnose_anomaly takes the ids marked diagnosable)."""
    return _anomalies.detect_anomalies()


@_safe
def diagnose_anomaly(finding_id: str) -> dict:
    """Possible causes of one finding, each tested against the data by code: supported by the data, not supported by
    the data, or cannot be tested with our data, in that order, with the evidence and what record would settle it.
    finding_id is a finding's id from reconcile_fuel or detect_anomalies (like machine_over_dispense:S1:S1-T4:2025-10).
    Say "supported by the data", never "proven" or "confirmed"; a person decides."""
    return _diagnose.diagnose_anomaly(finding_id)


@_safe
def benchmark_peers(site_id: str | None = None, operation_code: str | None = None) -> dict:
    """Compares machines doing the same job at the same site in litres per hectare. Flags machines that burn more than
    the typical machine and gives the litres at stake as a range. A difference is to investigate, not waste."""
    r = _peers.benchmark_peers(site_id, operation_code)
    for group in r["groups"]:
        for peer in group["peers"]:
            if not peer["above_peers"]:  # value and label stay; the explanation matters only for the flagged ones
                peer["l_per_ha"] = {k: v for k, v in peer["l_per_ha"].items() if k != "how"}
    r["skipped"] = [{"operation": s["operation"], "site_id": s["site_id"], "reason": s["reason"]} for s in r["skipped"]]
    return r


@_safe
def fleet_opportunities(site_id: str | None = None, tyre_pressure_checked: bool | None = None,
                        has_ctis: bool | None = None, ballast_type: str | None = None) -> dict:
    """Ideas from published research for the arable sites (S1, S3), ranked by strength of evidence, with fuel, CO2e and
    money ranges, the research sources behind each, and what applies. The vineyard returns no ideas, with the reason.

    Answers the user has given: tyre_pressure_checked (true/false), has_ctis (true/false), ballast_type (liquid or none).
    """
    known = {"tyre_pressure_checked": tyre_pressure_checked, "has_ctis": has_ctis, "ballast_type": ballast_type}
    out = _ideas.fleet_opportunities(site_id, {k: v for k, v in known.items() if v is not None})
    for idea in out["ideas"]:
        sources = {e["source_id"]: e for e in idea["evidence"]}  # one row per source, not per coefficient
        idea["evidence"] = [{"title": e["title"], "region": e["region"], "year": e["year"], "source_id": e["source_id"],
                            "link_status": e["link_status"], "is_manufacturer": e["is_manufacturer"]} for e in sources.values()]
        if idea.get("how") == ((idea.get("figures") or {}).get("litres_saved") or {}).get("how"):
            idea.pop("how", None)  # the same text is in figures.litres_saved.how
    return out


@_safe
def what_if(change: str, amount_pct: float, site_id: str | None = None) -> dict:
    """A scenario with an assumption the user sets: arithmetic on the fuel really burned, not a forecast.

    change is one of: implement_not_working (cut fuel burned with a tool attached but not working), peer_outliers (bring
    machines above their peers toward the typical machine), hvo (switch part of the fuel to HVO). amount_pct is 1 to 100.
    """
    return _what_if.what_if(change, amount_pct, site_id)


@_safe
def fleet_jobs(site_id: str | None = None, machine_id: str | None = None, client_id: str | None = None,
               operation_code: str | None = None, month: str | None = None, sort: str = "date", limit: int = 5) -> dict:
    """A list of jobs with fuel, hours, client and field. sort is date, litres (most fuel first) or hours. At most 10 jobs
    per call; the totals cover every job that matches the filters."""
    return _jobs.fleet_jobs(site_id, machine_id, client_id, operation_code, None, month, None, sort, max(1, min(limit, MAX_JOBS)), 0)


@_safe
def fleet_report(client_id: str | None = None) -> dict:
    """Prepares the traceable report for the whole company, or one client farm's statement (give client_id, like C09).
    Returns its headline figures, limits and how to open the full printable report in the Reports screen."""
    r = _report.fleet_report(client_id)
    return {"meta": r["meta"], "totals": r["totals"], "limits": r["limits"], "labels": r["labels"],
            "open_in_app": "Reports screen: choose the company or the client farm, then print or save as PDF."}


@_safe
def client_statement(client_id: str) -> dict:
    """One client farm's carbon statement (client_id like C09): fuel, CO2e and cost, CO2e per hectare and per job, the
    largest operations with their share, the months covered and what the statement does not cover. The written summary
    in the client's language is on the Reports screen."""
    r = _statement.client_statement(client_id)
    r["open_in_app"] = "Reports screen: choose the client farm and a language (English, German, Spanish or Hindi)."
    return r


@_safe
def weekly_briefing() -> dict:
    """The three things to look at first, chosen by fixed rules in code from fuel control, delivery notes, recorder data,
    peer comparisons and ideas: most severe first, then the largest, at most one per topic. Each item has its figure, why
    it matters, the next step, the screen to open and what would improve it. Covers the company year to date, not one week."""
    b = _briefing.weekly_briefing()
    items = [{**{k: v for k, v in i.items() if k != "link"}, "screen": SCREENS.get(i["link"], "Overview")} for i in b["items"]]
    return {"period": b["period"], "rules": b["rules"], "items": items, "chosen_from": b["candidates"]}


AGENT_TOOLS = [fleet_summary, emissions_per_client, data_quality, reconcile_fuel, check_delivery_notes, detect_anomalies,
               diagnose_anomaly, benchmark_peers, fleet_opportunities, what_if, fleet_jobs, fleet_report, client_statement,
               weekly_briefing]
BY_NAME = {t.__name__: t for t in AGENT_TOOLS}
