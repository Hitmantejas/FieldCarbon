"""Savings in money and CO2e, cost and payback only where a cost is sourced."""
from dataclasses import replace

import pytest

from backend.emissions.factors import wtw_factor
from backend.ranking.context import FarmContext
from backend.ranking.interventions import evaluate
from backend.ranking.roi import calculate_roi
from tests.test_interventions import BASE

P_LOW, P_HIGH = 0.718, 1.176  # ref_fuel_prices gas oil, lowest and highest month
KNOWN = replace(BASE, known={"tyre_pressure_checked": False, "has_ctis": False, "ballast_type": "liquid"})


def roi(ctx: FarmContext, intervention_id: str):
    result = next(r for r in evaluate(ctx) if r.intervention_id == intervention_id)
    return calculate_roi(result, ctx)


def test_fuel_money_saved_is_a_range_from_the_price_range():
    r = roi(KNOWN, "central_tyre_inflation")
    litres = 0.089 * 2450
    assert r.fuel_gbp_saved_low == pytest.approx(litres * P_LOW)
    assert r.fuel_gbp_saved_high == pytest.approx(litres * P_HIGH)


def test_co2e_avoided_uses_the_well_to_wheel_factor():
    r = roi(KNOWN, "central_tyre_inflation")
    assert r.co2e_avoided_kg_low == pytest.approx(0.089 * 2450 * wtw_factor("gas_oil", 2025).kg_per_unit)


def test_payback_only_when_a_purchase_cost_is_sourced():
    r = roi(KNOWN, "central_tyre_inflation")
    litres = 0.089 * 2450
    assert r.cost.kind == "capex_one_off" and r.cost.currency == "GBP"
    assert r.payback_years_low == pytest.approx(6000 / (litres * P_HIGH))   # cheapest kit, best saving
    assert r.payback_years_high == pytest.approx(16950 / (litres * P_LOW))  # dearest kit, worst saving


def test_no_cost_means_the_roi_says_so_not_zero():
    r = roi(KNOWN, "avoid_liquid_ballast")
    assert r.cost is None and r.cost_note == "Cost not yet sourced"
    assert r.payback_years_low is None and r.payback_years_high is None


def test_tillage_cost_change_is_per_hectare_over_the_ploughed_area_and_includes_fuel():
    r = roi(BASE, "no_till")
    assert (r.running_cost_change_gbp_low, r.running_cost_change_gbp_high) == pytest.approx((-100 * 50, -40 * 50))
    assert r.payback_years_low is None  # a drill purchase is not priced
    assert "diesel you save is already counted" in r.notes  # the fuel saving is inside this figure


def test_reduced_tillage_combines_both_cost_sources():
    r = roi(BASE, "reduced_tillage")
    assert (r.running_cost_change_gbp_low, r.running_cost_change_gbp_high) == pytest.approx((-120 * 50, 0))


def test_hvo_costs_more_and_has_no_payback():
    r = roi(BASE, "hvo_switch")
    extra = 0.041 * 3000
    new_litres = 3000 + extra
    # new bill minus old bill: the extra litres at the diesel price, plus every litre at the HVO premium
    low = extra * P_LOW + new_litres * 0.03
    high = extra * P_HIGH + new_litres * 0.131
    assert r.litres_saved_low == pytest.approx(-extra)
    assert r.running_cost_change_gbp_low == pytest.approx(low)
    assert r.running_cost_change_gbp_high == pytest.approx(high)
    assert r.payback_years_low is None
    assert r.co2e_avoided_kg_low > 0


def test_needs_info_still_gives_a_conditional_roi():
    r = roi(BASE, "correct_tyre_pressure")
    assert r.fuel_gbp_saved_high > 0 and r.cost.kind == "capex_one_off"


def test_not_feasible_has_no_savings():
    r = roi(BASE, "electric_tractor")
    assert r.fuel_gbp_saved_low is None and r.co2e_avoided_kg_low is None
