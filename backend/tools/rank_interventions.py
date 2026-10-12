from dataclasses import asdict

from backend.ranking import interventions, roi
from backend.ranking.context import farm_a_context


def rank_interventions(farm_id: str = "a") -> list[dict]:
    """Interventions ranked by robustness of evidence, each with its ROI, feasibility and sources."""
    if farm_id != "a":
        raise KeyError(f"unknown farm {farm_id}")
    ctx = farm_a_context()
    return [{**asdict(r), "roi": asdict(roi.calculate_roi(r, ctx))} for r in interventions.rank_interventions(ctx)]
