from __future__ import annotations

from dataclasses import asdict

from backend.emissions.text import bullets
from backend.fleet.context import ARABLE_SITES
from backend.ranking.goal import MAX_GOAL_PCT, MIN_GOAL_PCT, verdict
from backend.tools.action_impact import action_impact
from backend.tools.contracts import Figure, weakest
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.fleet_summary import fleet_summary

OVERLAP_NOTE = "Effects overlap, so these are not added."
NOT_COVERED = ("The vineyard is not covered: our research evidence is for arable field work, so no avoidable "
               "tonnes are claimed for it.")


def _tonnes(fig: dict) -> dict:
    """The same figure with kilograms shown as tonnes."""
    scale = lambda v: None if v is None else v / 1000
    return {**fig, "unit": fig["unit"].replace("kg", "t"), "value": scale(fig["value"]), "low": scale(fig["low"]),
            "high": scale(fig["high"]), "how": fig["how"] + "\n- Shown in **tonnes**: kilograms divided by 1,000."}


def _estimated(unit: str, how: str, sources, low: float, high: float) -> dict:
    return asdict(Figure(None, unit, "estimated", how, source_ids=tuple(dict.fromkeys(sources)), low=low, high=high))


def _site_rows(summary: dict) -> list[dict]:
    rows = []
    for r in summary["rows"]:
        co2e = r["co2e_kg"]
        label = weakest([co2e["label"], "allocated"])  # the area worked is worked out from GPS and implement width
        per_ha = Figure(co2e["value"] / r["area_ha"], "kg CO2e per ha", label, bullets(
            f"**{co2e['value']:,.0f} kg of CO2e** over **{r['area_ha']:,.0f} hectares** worked.",
            "Fuel burned outside jobs is included, so this is higher than the figure for field work alone.",
            "The area is worked out from GPS tracks and implement width, so it is **allocated**."),
            source_ids=tuple(co2e["source_ids"]))
        rows.append({"site_id": r["key"], "name": r["name"], "co2e_t": _tonnes(co2e), "kg_per_ha": asdict(per_ha),
                     "covered_by_evidence": r["key"] in ARABLE_SITES})
    return rows


def _action(idea: dict) -> dict:
    return {"intervention_id": idea["intervention_id"], "name": idea["name"], "state": idea["state"],
            "robustness": idea["robustness"], "co2e_avoided_t": _tonnes(idea["figures"]["co2e_avoided_kg"]),
            "gbp_per_tco2e": idea["figures"]["gbp_per_tco2e"], "gbp_per_tco2e_note": idea["gbp_per_tco2e_note"]}


def _pct_of(total_t: float, low_t: float, high_t: float, sources) -> dict:
    return _estimated("% of fleet emissions", bullets(
        f"**{low_t:,.1f} to {high_t:,.1f} tonnes** of CO2e avoided, out of **{total_t:,.1f} tonnes** burned by the fleet."),
        sources, 100 * low_t / total_t, 100 * high_t / total_t)


def carbon_ledger(goal_pct: float = 20, known: dict | None = None) -> dict:
    """Tonnes of CO2e emitted, tonnes avoidable as a range, and tonnes proven, with a goal check."""
    if not MIN_GOAL_PCT <= goal_pct <= MAX_GOAL_PCT:
        raise ValueError(f"goal must be {MIN_GOAL_PCT} to {MAX_GOAL_PCT} percent")
    summary = fleet_summary("site")
    emitted = _tonnes(summary["totals"]["co2e_kg"])
    emitted_t = emitted["value"]
    sites = _site_rows(summary)
    covered = [r for r in summary["rows"] if r["key"] in ARABLE_SITES]
    covered_t = sum(r["co2e_kg"]["value"] for r in covered) / 1000

    ideas = [i for i in fleet_opportunities(None, known)["ideas"] if i["state"] != "not_feasible"]
    feasible = [_action(i) for i in ideas if i["state"] == "feasible"]
    actions = feasible + [_action(i) for i in ideas if i["state"] != "feasible"]
    top = feasible[0]  # ideas arrive ranked by strength of evidence
    largest = max(feasible, key=lambda a: a["co2e_avoided_t"]["low"])
    highs = [a["co2e_avoided_t"]["high"] for a in feasible]
    sources = [s for a in feasible for s in a["co2e_avoided_t"]["source_ids"]]
    combined_low, combined_high = largest["co2e_avoided_t"]["low"], min(sum(highs), covered_t)
    combined = _estimated("t CO2e per year", bullets(
        f"At least the **largest single idea's low estimate**: **{combined_low:,.1f} tonnes** ({largest['name']}).",
        f"At most the **ideas' high estimates added together**, held to the **{covered_t:,.1f} tonnes** the arable sites burn: "
        f"**{combined_high:,.1f} tonnes**.", OVERLAP_NOTE), sources, combined_low, combined_high)

    top_t = top["co2e_avoided_t"]
    target = Figure(emitted_t * goal_pct / 100, "t CO2e", emitted["label"], bullets(
        f"**{goal_pct:g}%** of the **{emitted_t:,.1f} tonnes** the fleet emitted."), source_ids=tuple(emitted["source_ids"]))
    top_pct = _pct_of(emitted_t, top_t["low"], top_t["high"], top_t["source_ids"])
    combined_pct = _pct_of(emitted_t, combined_low, combined_high, sources)
    proof = action_impact()
    proven_changes = [{"action_id": a["action"]["action_id"], "name": a["action"]["name"]} for a in proof["actions"] if a["co2e_avoided_t"]]

    return {
        "emitted": emitted,
        "sites": sites,
        "avoidable": {
            "top_action": top, "combined": combined, "actions": actions,
            "covered_emitted_t": {**emitted, "value": covered_t, "how": bullets(
                f"Fuel burned at the arable sites: **{covered_t:,.1f} tonnes** of CO2e. Only these sites have research behind an idea.")},
            "covered_share_pct": 100 * covered_t / emitted_t, "not_covered": NOT_COVERED,
        },
        "proven": proof["proven_co2e_t"],
        "proven_changes": proven_changes,
        "goal": {"target_pct": goal_pct, "target_co2e": asdict(target), "top_action_pct": top_pct, "combined_pct": combined_pct,
                 "top_action_verdict": verdict(top_pct["low"], top_pct["high"], goal_pct),
                 "combined_verdict": verdict(combined_pct["low"], combined_pct["high"], goal_pct)},
    }
