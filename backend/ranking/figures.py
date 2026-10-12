from datetime import datetime

from backend.emissions.factors import wtw_factor
from backend.emissions.farm_summary import EF_YEAR, TELEMETRY_SOURCE, fuel_price_range
from backend.ranking.context import FarmContext
from backend.ranking.interventions import InterventionResult
from backend.ranking.roi import Roi
from backend.tools.contracts import Figure

NAMES = ("litres_saved", "co2e_avoided_kg", "fuel_gbp_saved", "cost", "payback_years", "running_cost_change_gbp")

FUEL_NAMES = {"gas_oil": "red diesel", "diesel_blend": "diesel"}

COST_HOW = {
    "capex_one_off": "The lowest and highest prices we found. They may leave out fitting and VAT.",
    "operating_cost_per_area_change": "The lowest and highest cost difference per hectare that we found.",
    "running_cost_extra_per_litre": "The lowest and highest extra price per litre that we found, compared with ordinary diesel.",
}


def _range(unit: str, low: float, high: float, how: str, sources: tuple[str, ...]) -> Figure:
    # A single value (HVO) is a point; everything else is a range.
    return Figure(low if low == high else None, unit, "estimated", how, source_ids=sources, low=low, high=high)


def _month(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m").strftime("%B %Y")


def _running_cost_how(roi: Roi, cost) -> str:
    if cost.kind == "operating_cost_per_area_change":
        per_ha = sorted((abs(cost.low), abs(cost.high)))
        return (f"{roi.hectares:.0f} hectares of ploughing, times £{per_ha[0]:.0f} to £{per_ha[1]:.0f} saved on each "
                "hectare. The diesel you save is already counted in this figure. The cost figures are old, so use them "
                "as a rough guide.")
    extra = -roi.litres_saved_low
    return (f"You would burn about {extra:,.0f} litres more fuel a year, paid at the diesel price. Every litre of HVO "
            f"also costs {cost.low * 100:.0f}p to {cost.high * 100:.0f}p more than ordinary diesel. Duty changes and "
            "fuel credits can move the price, so ask a fuel supplier for a quote.")


def plan_figures(result: InterventionResult, roi: Roi, ctx: FarmContext) -> dict[str, Figure | None]:
    """The intervention's numbers as contract figures. Manufacturer sources never back a figure."""
    out: dict[str, Figure | None] = dict.fromkeys(NAMES)
    if result.state == "not_feasible":
        return out

    price = fuel_price_range()
    evidence = tuple(dict.fromkeys(e.source_id for e in result.evidence if e.used_in_range))
    farm_litres = evidence + (TELEMETRY_SOURCE,)
    factor = wtw_factor(ctx.fuel_type, EF_YEAR)
    fuel = FUEL_NAMES.get(ctx.fuel_type, ctx.fuel_type.replace("_", " "))

    if roi.litres_saved_low is not None:
        out["litres_saved"] = _range("L per year", roi.litres_saved_low, roi.litres_saved_high, result.how, farm_litres)
        out["fuel_gbp_saved"] = _range(
            "GBP per year", roi.fuel_gbp_saved_low, roi.fuel_gbp_saved_high,
            f"Litres saved, times the price of {fuel}: £{price.low:.2f} to £{price.high:.2f} a litre between "
            f"{_month(price.from_month)} and {_month(price.to_month)}. Your recording has no dates, so we use the "
            "whole price range.",
            farm_litres + (price.source_id,))
    if roi.co2e_avoided_kg_low is not None:
        if roi.litres_saved_high is not None and roi.litres_saved_high < 0:
            more = -roi.litres_saved_low / ctx.total_litres * 100
            how = (f"We worked out the CO2 from the {fuel} you burn now and from the HVO you would burn instead "
                   f"(about {more:.1f}% more litres), using UK government figures for {EF_YEAR}. The difference is the saving.")
        else:
            how = (f"Litres saved, times {factor.kg_per_unit:.2f} kg of CO2 for each litre of {fuel}. UK government "
                   f"figures for {EF_YEAR}; they include the CO2 from making and moving the fuel.")
        out["co2e_avoided_kg"] = _range("kg CO2e per year", roi.co2e_avoided_kg_low, roi.co2e_avoided_kg_high, how,
                                        farm_litres + (factor.source_id,))

    cost = roi.cost
    if cost:
        out["cost"] = _range(f"{cost.currency} {cost.unit}", cost.low, cost.high, COST_HOW[cost.kind], cost.source_ids)
        if roi.payback_years_low is not None and roi.payback_years_high is not None:
            out["payback_years"] = _range(
                "years", roi.payback_years_low, roi.payback_years_high,
                "The cost divided by the money saved on fuel each year. The lowest cost with the biggest saving gives the "
                "shortest time; the highest cost with the smallest saving gives the longest. We treat your one recorded "
                "season as a year.",
                cost.source_ids + farm_litres + (price.source_id,))
        if roi.running_cost_change_gbp_low is not None:
            sources = cost.source_ids + (TELEMETRY_SOURCE,) + ((price.source_id,) if cost.kind == "running_cost_extra_per_litre" else ())
            out["running_cost_change_gbp"] = _range("GBP per year", roi.running_cost_change_gbp_low,
                                                     roi.running_cost_change_gbp_high, _running_cost_how(roi, cost), sources)
    return out
