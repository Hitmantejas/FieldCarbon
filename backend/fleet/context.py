"""The evidence engine's FarmContext, built from the fleet's measured jobs instead of one farm's aggregates."""
from __future__ import annotations

from dataclasses import replace

from backend.fleet import data
from backend.ranking.context import FarmContext

# The research behind the interventions covers arable field work. Vineyard operations have no applicable evidence yet.
ARABLE_SITES = ("S1", "S3")


def fleet_context(site_ids: tuple[str, ...] = ARABLE_SITES, known: dict | None = None) -> FarmContext:
    ledger = data.ledger()
    scope = ledger[ledger.site_id.isin(site_ids)]
    jobs = data.jobs()
    jobs = jobs[jobs.site_id.isin(site_ids)]
    loaded = jobs[jobs.mean_load_pct.notna()]
    per_op = loaded.assign(load_hours=loaded.mean_load_pct * loaded.hours).groupby("operation_code")[["hours", "load_hours"]].sum()
    ploughed_fields = set(jobs[(jobs.operation_code == "ploughing") & jobs.field_id.notna()].field_id)
    machines = data.machines()
    return replace(FarmContext(
        litres_by_op=jobs.groupby("operation_code").litres.sum().to_dict(),
        hectares_by_op=jobs.groupby("operation_code").area_ha.sum().to_dict(),
        mean_load_by_op=(per_op.load_hours / per_op.hours).to_dict(),
        tractor_kw={m: int(machines.rated_kw[m]) for m in machines.index if machines.site_id[m] in site_ids},
        litres_by_tractor=scope.groupby("machine_id").litres.sum().to_dict(),
        total_litres=float(scope.litres.sum()),
        ploughed_litres_by_op=jobs[jobs.field_id.isin(ploughed_fields)].groupby("operation_code").litres.sum().to_dict(),
        litres_source_ids=tuple(data.sites().source_id[s] for s in site_ids),
    ), known=known or {})
