from __future__ import annotations

from datetime import datetime, timezone

from backend.emissions.farm_summary import EF_YEAR
from backend.emissions.sources import all_sources
from backend.emissions.text import bullets
from backend.fleet import data
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.fleet_summary import fleet_summary
from backend.tools.generate_report import _cited
from backend.tools.reconcile_fuel import reconcile_fuel

PERIOD = "1 May 2025 to 30 April 2026"
STATEMENT = ("This report is traceable: every figure lists its sources and how it was worked out. "
             "It has not been checked by an outside auditor.")
LABELS = [
    {"label": "measured", "meaning": "Recorded directly by a sensor on the tractor."},
    {"label": "allocated", "meaning": "Measured litres that we assign to a job, field or month by rule. Less certain than the total."},
    {"label": "estimated", "meaning": "Worked out from research results applied to the fleet's fuel. The real number can be different."},
]
ATTRIBUTION = ("Real telemetry: TUM Agricultural Load Cycles (Zenodo 14619787), vineyard tractor operations (Mendeley Data, "
               "DOI 10.17632/y3h5xzkjc6.1) and Tümosan tillage CAN bus (DOI 10.17632/bbjtjrsxvx.2), all CC BY 4.0, aggregated by us. "
               f"Emission factors: UK Government GHG Conversion Factors {EF_YEAR} (OGL). Operators, clients, fuel deliveries and "
               "maintenance are synthetic.")


def _method() -> str:
    return bullets(
        "**Fuel** is recorded by each machine's own sensor, or read from its tank level at the vineyard.",
        f"**Emissions** are the litres times the UK government emission factors for {EF_YEAR}, including the CO2 from making and moving the fuel.",
        "**Cost** is the litres times the price paid in each month's fuel deliveries.",
        "**Splits** by site, client, field and month are allocated by rule, not measured.",
        "**Savings** are ranges from published research, applied to the fleet's own fuel. They overlap, so they are never added together.")


def _finish(report: dict) -> dict:
    cited = _cited(report)
    report["sources"] = [s for s in all_sources() if s["source_id"] in cited]
    return report


def fleet_report(client_id: str | None = None) -> dict:
    """A shareable, traceable document: for the whole company, or one client's statement."""
    meta = {"title": "FieldCarbon fleet report", "period": PERIOD, "demo_data": True, "statement": STATEMENT,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "client": None}
    common = {"labels": LABELS, "method": _method(), "attribution": ATTRIBUTION}

    if client_id:
        r = emissions_per_client(client_id)
        meta.update(title="FieldCarbon client statement", client=data.client_name(client_id))
        row = r["rows"][0]
        return _finish({
            "meta": meta,
            "totals": {"litres": row["litres"], "co2e_kg": row["co2e_kg"], "cost_gbp": row["cost_gbp"], "jobs": row["jobs"],
                       "hours": row["hours"], "area_ha": row["area_ha"]},
            "months": r["months"],
            "limits": ["Dates, clients and operators in this demo are synthetic.",
                       "Fuel burned between jobs (travel, idling) is company overhead and is not in this statement."],
            **common})

    sites, clients = fleet_summary("site"), emissions_per_client()
    frozen = float(data.other_activity().query("activity_class == 'data_gap'").hours.sum())
    order = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(reconcile_fuel()["findings"] + detect_anomalies()["findings"],
                      key=lambda f: (order[f["severity"]], -f["litres"]["value"]))
    t = sites["totals"]
    return _finish({
        "meta": meta,
        "totals": {"litres": t["litres"], "co2e_kg": t["co2e_kg"], "cost_gbp": t["cost_gbp"], "jobs": sum(s["jobs"] for s in sites["rows"]),
                   "hours": sum(s["hours"] for s in sites["rows"]), "area_ha": sum(s["area_ha"] for s in sites["rows"])},
        "by_site": [{"key": s["key"], "name": s["name"], "litres": s["litres"], "co2e_kg": s["co2e_kg"], "share_pct": s["share_pct"]}
                    for s in sites["rows"]],
        "by_client": [{"client_id": c["client_id"], "name": c["name"], "litres": c["litres"], "co2e_kg": c["co2e_kg"]} for c in clients["rows"]],
        "overhead": clients["overhead"], "unmatched_jobs": clients["unmatched_jobs"],
        "findings": [{"title": f["title"], "severity": f["severity"], "litres": f["litres"]} for f in findings[:8]],
        "ideas": [{"intervention_id": i["intervention_id"], "name": i["name"], "robustness": i["robustness"], "n_sources": i["n_sources"],
                   "litres_saved": i["figures"]["litres_saved"], "co2e_avoided_kg": i["figures"]["co2e_avoided_kg"]}
                  for i in fleet_opportunities()["ideas"] if i["state"] == "feasible"],
        "limits": [f"{frozen:.0f} hours where a recorder was frozen, repeating the same values, are left out, so fuel used in them is not counted.",
                   "Savings are estimates from research. The real result can be different.",
                   "Dates, clients, operators, fuel deliveries and maintenance in this demo are synthetic.",
                   "Differences between machines and the findings above are reasons to look, not proof of a fault or a loss."],
        **common})
