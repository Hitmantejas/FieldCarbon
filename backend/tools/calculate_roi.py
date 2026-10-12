from backend.tools.rank_interventions import rank_interventions

KEYS = ("intervention_id", "state", "figures", "cost_kind", "cost_note", "notes")


def calculate_roi(intervention_id: str, farm_id: str = "a") -> dict:
    """Savings, cost and payback (only where a cost is sourced) for one intervention on one farm."""
    for item in rank_interventions(farm_id):
        if item["intervention_id"] == intervention_id:
            return {k: item[k] for k in KEYS}
    raise KeyError(f"unknown intervention {intervention_id}")
