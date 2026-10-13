from __future__ import annotations

from backend.fleet.context import ARABLE_SITES, fleet_context
from backend.tools.rank_interventions import ideas_for

NO_EVIDENCE = ("The research behind our ideas covers arable field work. Nothing in our evidence table applies to "
               "vineyard operations yet, so none is suggested for this site.")


def fleet_opportunities(site_id: str | None = None, known: dict | None = None) -> dict:
    """Evidence-based ideas for the fleet's arable sites, with research ranges applied to their measured jobs."""
    if site_id and site_id not in ARABLE_SITES:
        return {"scope": {"site_ids": [site_id]}, "ideas": [], "reason": NO_EVIDENCE}
    sites = ARABLE_SITES if site_id is None else (site_id,)
    ctx = fleet_context(sites, known)
    return {"scope": {"site_ids": list(sites), "litres": ctx.total_litres}, "ideas": ideas_for(ctx), "reason": None}
