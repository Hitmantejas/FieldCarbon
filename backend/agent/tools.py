"""The tools the fleet analyst agent may call.

Plain Python functions over the deterministic tools, so the model plans and explains while code does every figure
(CLAUDE.md principle 1). Names match the underlying tools, because the eval cases and recorded runs use those names.
Read-only; operators are deliberately not a parameter anywhere, so the agent cannot filter, rank or compare people.
A bad argument comes back as {"error": ...} so the model can correct itself.
"""
from __future__ import annotations

import json
from functools import wraps

from backend.tools import (benchmark_peers as _peers, check_delivery_notes as _notes, data_quality as _quality,
                           detect_anomalies as _anomalies, emissions_per_client as _clients, fleet_jobs as _jobs,
                           fleet_opportunities as _ideas, fleet_report as _report, fleet_summary as _summary, reconcile_fuel as _recon, what_if as _what_if)

MAX_JOBS = 10


def _plain(value):
    """Tuples, numpy numbers and the like become plain JSON, which is what the model and the run log both need."""
    return json.loads(json.dumps(value, default=str))


def _safe(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        try:
            return _plain(fn(*args, **kwargs))
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
    """
    return _summary.fleet_summary(group_by, site_id, machine_id, client_id, operation_code, None, month)


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
    entered twice, and night-time dispenses. Returns the findings and only the table rows that need a look."""
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
    fuel per hour than usual, and tractors with a large share of fuel spent on idling and travel. Not proof of a fault."""
    return _anomalies.detect_anomalies()


@_safe
def benchmark_peers(site_id: str | None = None, operation_code: str | None = None) -> dict:
    """Compares machines doing the same job at the same site in litres per hectare. Flags machines that burn more than
    the typical machine and gives the litres at stake as a range. A difference is to investigate, not waste."""
    return _peers.benchmark_peers(site_id, operation_code)


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
        idea["evidence"] = [{"title": e["title"], "region": e["region"], "year": e["year"], "source_id": e["source_id"],
                            "link_status": e["link_status"], "is_manufacturer": e["is_manufacturer"]} for e in idea["evidence"]]
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


AGENT_TOOLS = [fleet_summary, emissions_per_client, data_quality, reconcile_fuel, check_delivery_notes, detect_anomalies,
               benchmark_peers, fleet_opportunities, what_if, fleet_jobs, fleet_report]
BY_NAME = {t.__name__: t for t in AGENT_TOOLS}
