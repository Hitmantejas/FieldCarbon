from dataclasses import asdict
from datetime import datetime, timezone

from backend.emissions.farm_summary import EF_YEAR, EXCLUDED_CLASS, TELEMETRY_SOURCE, breakdown, farm_a_rows, fuel_price_range, summarise
from backend.emissions.pain_points import farm_a_ratings
from backend.emissions import tier3
from backend.emissions.provenance import FARM_B_PROVENANCE, PROVENANCE
from backend.emissions.sources import all_sources
from backend.emissions.text import bullets, month_name
from backend.ranking.context import FARMS
from backend.tools.contracts import Figure
from backend.tools.rank_interventions import rank_interventions
from backend.tools.set_goal import set_goal
from backend.tools.what_would_improve import still_uncertain

STATEMENT = ("This report is traceable: every figure lists its sources and how it was worked out. "
             "It has not been checked by an outside auditor.")

LABELS = [
    {"label": "measured", "meaning": "Recorded directly by a sensor on the tractor."},
    {"label": "allocated", "meaning": "Measured litres that we assign to a job or field by rule. Less certain than the total."},
    {"label": "estimated", "meaning": "Worked out from research results and your own fuel use. The real number can be different."},
]
FARM_B_LABELS = [
    {"label": "measured", "meaning": "Read from your fuel receipts: litres and what you paid."},
    LABELS[2],
]


def _cited(node) -> set[str]:
    """Every source id cited by a figure anywhere in the report."""
    if isinstance(node, dict):
        found = set(node.get("source_ids", ())) if "label" in node and "how" in node else set()
        for value in node.values():
            found |= _cited(value)
        return found
    if isinstance(node, list):
        return set().union(*(_cited(v) for v in node)) if node else set()
    return set()


def _method() -> str:
    price = fuel_price_range()
    return bullets(
        "**Fuel** is recorded by each tractor's own sensor over one season.",
        f"**Emissions** are the litres times the UK government emission factors for {EF_YEAR}, including the CO2 from "
        "making and moving the fuel.",
        f"**Cost** is a range, because the recording has no dates. It uses red diesel prices from {month_name(price.from_month)} "
        f"to {month_name(price.to_month)}.",
        "**Splits** by job and by field are allocated by rule, not measured.",
        "**Savings** are estimates: research results applied to your own litres.",
    )


def _method_b() -> str:
    return bullets(
        "**Fuel** is added up from your fuel receipts, read and checked by fixed rules.",
        f"**Emissions** are the litres times the UK government emission factors for {EF_YEAR}, including the CO2 from "
        "making and moving the fuel.",
        "**Cost** is what you paid, from the receipts, before VAT.",
        "**Splits** by job are estimates: the area you worked times published fuel use per hectare "
        "(Iowa State A3-27). Receipts do not say which job used the fuel.",
        "**Savings** are estimates: research results applied to both ends of your estimated split.",
    )


def _farm_b_parts() -> dict:
    t = tier3.receipt_totals()
    s = tier3.summarise(t)
    return {
        "farm": "Farm B",
        "totals": {"litres": asdict(s.litres), "co2e_kg": asdict(s.co2e_kg), "cost_gbp": asdict(s.cost_gbp),
                   "engine_hours": None, "excluded_hours": None},
        "where_it_went": [{"name": r.name, "share_pct": r.share_pct, "litres": asdict(r.litres)}
                          for r in tier3.breakdown_by_operation(t)[:8]],
        "pain_points": [],
        "pain_points_note": "Not available: receipts do not show fuel per job, and comparing an estimate made "
                            "from published rates with those same rates would prove nothing.",
        "limits": ["We assume the fuel bought this season was used this season (tank level the same at start and end).",
                   "Savings are estimates from research. Your real result can be different."],
        "labels": FARM_B_LABELS, "method": _method_b(), "attribution": FARM_B_PROVENANCE,
    }


def _farm_a_parts() -> dict:
    rows = farm_a_rows()
    totals = summarise(rows)
    excluded = float(rows[rows.activity_class == EXCLUDED_CLASS].hours.sum())
    pain = []
    for r in farm_a_ratings()[0]:
        if r.band not in ("above_typical", "well_above"):
            continue
        ids = (TELEMETRY_SOURCE, *r.reference.source_ids, *(r.second_opinion.source_ids if r.second_opinion else ()))
        pain.append({
            "name": r.display_name, "band": r.band, "you_l_per_ha": r.l_per_ha, "typical_low": r.reference.low,
            "typical_high": r.reference.high, "hectares": r.hectares, "sources_agree": r.sources_agree,
            "at_stake": asdict(Figure(None, "L per year", r.litres_at_stake_label, r.how, source_ids=tuple(dict.fromkeys(ids)),
                                      low=r.litres_at_stake_low, high=r.litres_at_stake_high)),
        })
    return {
        "farm": "Farm A",
        "totals": {"litres": asdict(totals.litres), "co2e_kg": asdict(totals.co2e_kg), "cost_gbp": asdict(totals.cost_gbp),
                   "engine_hours": totals.hours, "excluded_hours": excluded},
        "where_it_went": [{"name": r.name, "share_pct": r.share_pct, "litres": asdict(r.litres)}
                          for r in breakdown(rows, "operation")[:8]],
        "pain_points": pain,
        "limits": [f"{excluded:.0f} hours where the recorder froze are left out, so fuel used in them is not counted.",
                   "Savings are estimates from research. Your real result can be different."],
        "labels": LABELS, "method": _method(), "attribution": PROVENANCE,
    }


def generate_report(target_pct: float | None = None, farm_id: str = "a", known: dict | None = None) -> dict:
    """A shareable, traceable summary: the numbers, the plan, the answers given, and every source."""
    if farm_id not in FARMS:
        raise KeyError(f"unknown farm {farm_id}")
    known = known or {}
    parts = _farm_a_parts() if farm_id == "a" else _farm_b_parts()
    goal = set_goal(target_pct, farm_id, known)
    verdicts = {i["intervention_id"]: i for i in goal["ideas"]}
    ideas = rank_interventions(farm_id, known)

    report = {
        "meta": {"title": "FieldCarbon report", "farm": parts["farm"], "demo_data": PROVENANCE["demo_data"],
                 "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "statement": STATEMENT},
        "totals": parts["totals"],
        "where_it_went": parts["where_it_went"],
        "pain_points": parts["pain_points"],
        **({"pain_points_note": parts["pain_points_note"]} if "pain_points_note" in parts else {}),
        "plan": {
            "goal": {"target_pct": goal["target_pct"], "target_co2e": goal["target_co2e"], "target_litres": goal["target_litres"]},
            "ideas": [{
                "intervention_id": i["intervention_id"], "name": i["name"], "robustness": i["robustness"],
                "n_sources": i["n_sources"], "verdict": verdicts[i["intervention_id"]]["verdict"],
                "reach": verdicts[i["intervention_id"]]["reach"], "figures": i["figures"], "how": i["how"],
                "cost_kind": i["cost_kind"], "overlaps": i["overlaps"],
            } for i in ideas if i["state"] == "feasible"],
            "waiting": sum(i["state"] == "needs_info" for i in ideas),
        },
        "answers": known,
        "limits": still_uncertain(farm_id, known) + parts["limits"],
        "labels": parts["labels"],
        "method": parts["method"],
        "attribution": parts["attribution"],
    }
    cited = _cited(report)
    report["sources"] = [s for s in all_sources() if s["source_id"] in cited]
    return report
