from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from backend.emissions.farm_summary import fuel_price_range
from backend.ranking.context import FarmContext
from backend.ranking.interventions import REF, InterventionResult, required_operation


@dataclass(frozen=True)
class Cost:
    kind: str  # capex_one_off | running_cost_extra_per_litre | operating_cost_per_area_change
    low: float
    high: float
    currency: str
    unit: str
    source_ids: tuple[str, ...]
    derivation: str
    value_status: str  # needs_primary_check if any contributing row still does


@dataclass(frozen=True)
class Roi:
    intervention_id: str
    state: str
    litres_saved_low: float | None
    litres_saved_high: float | None
    co2e_avoided_kg_low: float | None
    co2e_avoided_kg_high: float | None
    fuel_gbp_saved_low: float | None
    fuel_gbp_saved_high: float | None
    cost: Cost | None
    cost_note: str
    payback_years_low: float | None
    payback_years_high: float | None
    running_cost_change_gbp_low: float | None  # positive = costs more, negative = saves
    running_cost_change_gbp_high: float | None
    hectares: float | None  # ploughed area a per-hectare cost change is applied to
    notes: str


@lru_cache(maxsize=1)
def _costs() -> pd.DataFrame:
    return pd.read_csv(REF / "ref_intervention_costs.csv")


def _cost_for(intervention_id: str) -> Cost | None:
    rows = _costs()
    rows = rows[rows.intervention_id == intervention_id]
    if rows.empty:
        return None
    rows = rows[rows.cost_type == rows.cost_type.iloc[0]]
    status = "needs_primary_check" if (rows.value_status == "needs_primary_check").any() else "checked"
    return Cost(rows.cost_type.iloc[0], float(rows.low.min()), float(rows.high.max()), rows.currency.iloc[0],
                rows.unit.iloc[0], tuple(rows.source_id), " | ".join(rows.derivation), status)


def _bounds(values: list[float]) -> tuple[float, float]:
    return min(values), max(values)


def calculate_roi(result: InterventionResult, ctx: FarmContext) -> Roi:
    empty = dict(litres_saved_low=None, litres_saved_high=None, co2e_avoided_kg_low=None, co2e_avoided_kg_high=None,
                 fuel_gbp_saved_low=None, fuel_gbp_saved_high=None, cost=None, payback_years_low=None,
                 payback_years_high=None, running_cost_change_gbp_low=None, running_cost_change_gbp_high=None,
                 hectares=None)
    if result.state == "not_feasible":
        return Roi(result.intervention_id, result.state, cost_note="Not applicable to this farm.", notes=result.reason, **empty)

    price = fuel_price_range()
    fuel = (None, None)
    if result.litres_saved_low is not None:
        fuel = _bounds([l * p for l in (result.litres_saved_low, result.litres_saved_high) for p in (price.low, price.high)])

    cost = _cost_for(result.intervention_id)
    notes = ["We treat the fuel recorded as a full year of use."]
    hectares = None
    payback = (None, None)
    running = (None, None)
    if cost is None:
        note = "Cost not yet sourced"
    else:
        note = ""
        if cost.kind == "capex_one_off" and cost.currency == "GBP" and fuel[1] is not None and fuel[1] > 0:
            payback = (cost.low / fuel[1], cost.high / fuel[0] if fuel[0] > 0 else None)
        elif cost.kind == "operating_cost_per_area_change":
            hectares = ctx.hectares_by_op.get(required_operation(result.intervention_id), 0.0)
            running = (cost.low * hectares, cost.high * hectares)
            notes.append("The diesel you save is already counted in this figure.")
        elif cost.kind == "running_cost_extra_per_litre":
            extra, new = -result.litres_saved_low, ctx.total_litres - result.litres_saved_low
            running = _bounds([extra * p + new * prem for p in (price.low, price.high) for prem in (cost.low, cost.high)])
            notes.append("Duty changes and fuel credits can move the price, so ask a supplier for a quote.")

    return Roi(
        result.intervention_id, result.state, result.litres_saved_low, result.litres_saved_high,
        result.co2e_avoided_low, result.co2e_avoided_high, fuel[0], fuel[1], cost, note, payback[0], payback[1],
        running[0], running[1], hectares, " ".join(notes),
    )
