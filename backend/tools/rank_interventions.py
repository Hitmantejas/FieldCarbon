from dataclasses import asdict

from backend.ranking import interventions, roi
from backend.ranking.context import farm_contexts
from backend.ranking.figures import plan_figures

RAW_NUMBERS = ("litres_saved_low", "litres_saved_high", "co2e_avoided_low", "co2e_avoided_high")


def ideas_for(ctx, ctx_high=None) -> list[dict]:
    """Ranked interventions with contract figures for any context (one farm, or the fleet's arable sites)."""
    items = []
    for result in interventions.rank_interventions(ctx, ctx_high):
        r = roi.calculate_roi(result, ctx)
        item = {k: v for k, v in asdict(result).items() if k not in RAW_NUMBERS}  # figures carry the numbers
        item["figures"] = {k: asdict(f) if f else None for k, f in plan_figures(result, r, ctx).items()}
        item.update(cost_kind=r.cost.kind if r.cost else None, cost_note=r.cost_note, notes=r.notes)
        items.append(item)
    return items


def rank_interventions(farm_id: str = "a", known: dict | None = None) -> list[dict]:
    """Interventions ranked by robustness of evidence, each with contract figures, feasibility and sources.

    `known` holds the farmer's answers (tyre_pressure_checked, has_ctis, ballast_type).
    Farm B's job split is an estimated range, so its savings cover both ends of it."""
    ctx, ctx_high = farm_contexts(farm_id, known)
    return ideas_for(ctx, ctx_high)
