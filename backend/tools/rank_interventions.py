from dataclasses import asdict

from backend.ranking import interventions, roi
from backend.ranking.context import farm_a_context
from backend.ranking.figures import plan_figures

RAW_NUMBERS = ("litres_saved_low", "litres_saved_high", "co2e_avoided_low", "co2e_avoided_high")


def rank_interventions(farm_id: str = "a") -> list[dict]:
    """Interventions ranked by robustness of evidence, each with contract figures, feasibility and sources."""
    if farm_id != "a":
        raise KeyError(f"unknown farm {farm_id}")
    ctx = farm_a_context()
    items = []
    for result in interventions.rank_interventions(ctx):
        r = roi.calculate_roi(result, ctx)
        item = {k: v for k, v in asdict(result).items() if k not in RAW_NUMBERS}  # figures carry the numbers
        item["figures"] = {k: asdict(f) if f else None for k, f in plan_figures(result, r, ctx).items()}
        item.update(cost_kind=r.cost.kind if r.cost else None, cost_note=r.cost_note, notes=r.notes)
        items.append(item)
    return items
