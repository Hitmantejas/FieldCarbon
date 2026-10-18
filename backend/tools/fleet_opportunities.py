from __future__ import annotations

from dataclasses import asdict

from backend.emissions.text import bullets
from backend.fleet.context import ARABLE_SITES, fleet_context
from backend.tools.contracts import Figure
from backend.tools.rank_interventions import ideas_for

NO_EVIDENCE = ("The research behind our ideas covers arable field work. Nothing in our evidence table applies to "
               "vineyard operations yet, so none is suggested for this site.")
ONE_OFF_NOTE = "One-off cost: see the payback instead."


def _cost_per_tonne(idea: dict) -> tuple[dict | None, str]:
    """Net yearly cost of an idea divided by the tonnes of CO2e it avoids. Needs a sourced running-cost change."""
    figs = idea["figures"]
    co2e, running = figs["co2e_avoided_kg"], figs["running_cost_change_gbp"]
    if co2e is None:
        return None, ""
    if running is None:
        return None, ONE_OFF_NOTE if idea["cost_kind"] == "capex_one_off" else idea["cost_note"]
    tonnes = (co2e["low"] / 1000, co2e["high"] / 1000)
    per_tonne = [c / t for c in (running["low"], running["high"]) for t in tonnes]
    low, high = min(per_tonne), max(per_tonne)
    how = bullets(
        f"**Net yearly cost** (**£{running['low']:,.0f} to £{running['high']:,.0f}**) divided by the **tonnes of CO2e avoided** "
        f"(**{tonnes[0]:,.1f} to {tonnes[1]:,.1f}**).",
        "The lowest and highest results are shown, so the range is wide.",
        "A **negative** figure means the change saves money as well as CO2e.")
    fig = Figure(low if low == high else None, "GBP per tonne CO2e", "estimated", how,
                 source_ids=tuple(dict.fromkeys(running["source_ids"] + co2e["source_ids"])), low=low, high=high)
    return asdict(fig), ""


def fleet_opportunities(site_id: str | None = None, known: dict | None = None) -> dict:
    """Evidence-based ideas for the fleet's arable sites, with research ranges applied to their measured jobs."""
    if site_id and site_id not in ARABLE_SITES:
        return {"scope": {"site_ids": [site_id]}, "ideas": [], "reason": NO_EVIDENCE}
    sites = ARABLE_SITES if site_id is None else (site_id,)
    ctx = fleet_context(sites, known)
    ideas = ideas_for(ctx)
    for idea in ideas:
        idea["figures"]["gbp_per_tco2e"], idea["gbp_per_tco2e_note"] = _cost_per_tonne(idea)
    return {"scope": {"site_ids": list(sites), "litres": ctx.total_litres}, "ideas": ideas, "reason": None}
