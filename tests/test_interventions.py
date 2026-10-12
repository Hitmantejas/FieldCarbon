"""Applicability, savings ranges and robustness ranking (CLAUDE.md sections 4, 5, 7)."""
from dataclasses import replace

import pytest

from backend.emissions.factors import emissions_kg
from backend.ranking.context import FarmContext, farm_a_context
from backend.ranking.interventions import evaluate, rank_interventions

# A small farm whose numbers can be checked by hand.
BASE = FarmContext(
    litres_by_op={"ploughing": 1000.0, "cultivating_deep": 500.0, "seed_drill_combination": 800.0,
                  "power_harrowing": 100.0, "transport": 50.0, "mulching": 200.0},
    hectares_by_op={"ploughing": 50.0, "cultivating_deep": 100.0, "seed_drill_combination": 80.0,
                    "power_harrowing": 10.0},
    mean_load_by_op={"ploughing": 70.0, "cultivating_deep": 45.0, "seed_drill_combination": 60.0,
                     "power_harrowing": 20.0, "mulching": 50.0},
    tractor_kw={"t1": 100, "t2": 150},
    litres_by_tractor={"t1": 1000.0, "t2": 2000.0},
    total_litres=3000.0,
)
KNOWN = {"tyre_pressure_checked": False, "has_ctis": False, "ballast_type": "liquid"}


def get(ctx: FarmContext, intervention_id: str):
    return next(r for r in evaluate(ctx) if r.intervention_id == intervention_id)


def with_known(**kw) -> FarmContext:
    return replace(BASE, known=kw)


def test_reduced_tillage_applies_to_tillage_litres_only():
    r = get(BASE, "reduced_tillage")
    base = 1000 + 500 + 100  # primary + secondary tillage; seeding, residue, transport are not tillage
    assert r.state == "feasible"
    assert r.litres_saved_low == pytest.approx(0.12 * base)    # smallest published low
    assert r.litres_saved_high == pytest.approx(0.594 * base)  # largest published high


def test_no_till_base_includes_seeding():
    r = get(BASE, "no_till")
    base = 1000 + 500 + 100 + 800
    assert (r.litres_saved_low, r.litres_saved_high) == pytest.approx((0.667 * base, 0.867 * base))


def test_tillage_changes_are_not_feasible_on_a_farm_that_does_not_plough():
    ctx = replace(BASE, litres_by_op={k: v for k, v in BASE.litres_by_op.items() if k != "ploughing"})
    r = get(ctx, "reduced_tillage")
    assert r.state == "not_feasible" and "ploughing" in r.reason
    assert r.litres_saved_low is None


def test_tyre_pressure_needs_info_when_unknown_and_names_the_input():
    r = get(BASE, "correct_tyre_pressure")
    assert r.state == "needs_info" and r.missing_inputs == ("tyre_pressure_checked",)
    assert r.litres_saved_high is not None  # potential saving is still shown, labelled as conditional


def test_tyre_pressure_feasible_when_unchecked_and_not_feasible_when_already_checked():
    assert get(with_known(tyre_pressure_checked=False), "correct_tyre_pressure").state == "feasible"
    done = get(with_known(tyre_pressure_checked=True), "correct_tyre_pressure")
    assert done.state == "not_feasible" and "already" in done.reason


def test_manufacturer_claims_are_context_not_part_of_the_range():
    r = get(with_known(tyre_pressure_checked=False), "correct_tyre_pressure")
    base = 1000 + 500 + 100 + 800
    assert r.litres_saved_low == pytest.approx(0.035 * base)   # Damanauskas, not Valtra's 1 L/ha
    assert r.litres_saved_high == pytest.approx(0.20 * base)
    valtra = [e for e in r.evidence if e.source_id == "valtra2023"][0]
    assert valtra.is_manufacturer and not valtra.used_in_range


def test_ctis_states():
    assert get(BASE, "central_tyre_inflation").missing_inputs == ("has_ctis",)
    assert get(with_known(has_ctis=True), "central_tyre_inflation").state == "not_feasible"
    r = get(with_known(has_ctis=False), "central_tyre_inflation")
    assert r.state == "feasible"
    assert r.litres_saved_low == pytest.approx(0.089 * (1000 + 500 + 100 + 800 + 50))  # includes transport


def test_ballast_needs_a_known_liquid_ballast():
    assert get(BASE, "avoid_liquid_ballast").missing_inputs == ("ballast_type",)
    assert get(with_known(ballast_type="none"), "avoid_liquid_ballast").state == "not_feasible"
    r = get(with_known(ballast_type="liquid"), "avoid_liquid_ballast")
    base = 1000 + 500 + 100 + 800
    assert (r.litres_saved_low, r.litres_saved_high) == pytest.approx((0.048 * base, 0.091 * base))


def test_shift_up_uses_only_drawbar_jobs_under_each_load_limit():
    r = get(BASE, "shift_up_throttle_down")
    # Drawbar jobs: ploughing (70% load) and deep cultivating (45%). PTO jobs never count.
    # Rows at a 75% limit see both (1500 L); rows at a 50% limit see deep cultivating only (500 L).
    assert r.state == "feasible"
    assert r.litres_saved_low == pytest.approx(0.149 * 500)    # KPI at 50% load
    assert r.litres_saved_high == pytest.approx(0.50 * 1500)   # JARQ upper bound at 75%


def test_shift_up_not_feasible_when_no_drawbar_job_is_light_enough():
    ctx = replace(BASE, mean_load_by_op={**BASE.mean_load_by_op, "ploughing": 90.0, "cultivating_deep": 85.0})
    r = get(ctx, "shift_up_throttle_down")
    assert r.state == "not_feasible" and "towed" in r.reason


def test_hvo_is_computed_from_the_emission_factor_table_not_a_source_percentage():
    r = get(BASE, "hvo_switch")
    old = emissions_kg(3000, "gas_oil", 2025, "estimated").kg_co2e
    new = emissions_kg(3000 * 1.041, "hvo", 2025, "estimated").kg_co2e
    assert r.state == "feasible"
    assert r.litres_saved_low == r.litres_saved_high == pytest.approx(-0.041 * 3000)  # more litres, not fewer
    assert r.co2e_avoided_low == r.co2e_avoided_high == pytest.approx(old - new)


def test_hvo_not_feasible_for_a_fuel_it_does_not_replace():
    assert get(replace(BASE, fuel_type="electricity_uk"), "hvo_switch").state == "not_feasible"


def test_electric_tractor_not_feasible_when_every_tractor_is_too_big():
    r = get(BASE, "electric_tractor")
    assert r.state == "not_feasible" and "22.4" in r.reason and "100" in r.reason


def test_electric_tractor_feasible_for_a_small_tractor():
    ctx = replace(BASE, tractor_kw={"t1": 20, "t2": 150}, litres_by_tractor={"t1": 100.0, "t2": 2900.0})
    r = get(ctx, "electric_tractor")
    assert r.state == "feasible"
    assert r.litres_saved_low is None  # the source states a GHG change, not litres
    assert r.co2e_avoided_low == pytest.approx(0.678 * emissions_kg(100, "gas_oil", 2025, "estimated").kg_co2e)


def test_robustness_counts_independent_non_manufacturer_sources():
    got = {r.intervention_id: r.robustness for r in evaluate(BASE)}
    assert got == {
        "reduced_tillage": "strong", "shift_up_throttle_down": "strong",
        "no_till": "moderate", "correct_tyre_pressure": "moderate",
        "central_tyre_inflation": "limited", "avoid_liquid_ballast": "limited",
        "hvo_switch": "limited", "electric_tractor": "limited",
    }


def test_every_recommendation_names_its_sources_and_how_far_to_trust_each_link():
    for r in evaluate(BASE):
        assert r.evidence and all(e.source_id and e.title and e.link_status for e in r.evidence)


def test_a_source_without_a_link_is_passed_through_as_such_not_hidden():
    gutd = get(BASE, "shift_up_throttle_down")
    assert any(e.url == "" and e.link_status.startswith("missing-link") for e in gutd.evidence)


def test_every_figure_is_labelled_estimated_and_explains_itself():
    for r in evaluate(BASE):
        assert r.label == "estimated" and r.how


def test_ranking_puts_feasible_before_needs_info_before_not_feasible():
    order = {"feasible": 0, "needs_info": 1, "not_feasible": 2}
    states = [order[r.state] for r in rank_interventions(BASE)]
    assert states == sorted(states)


def test_ranking_within_feasible_goes_by_robustness_then_narrower_range():
    ranked = [r for r in rank_interventions(with_known(**KNOWN)) if r.state == "feasible"]
    tiers = {"strong": 0, "moderate": 1, "limited": 2}
    keys = [(tiers[r.robustness], r.relative_width) for r in ranked]
    assert keys == sorted(keys)


def test_overlapping_interventions_are_flagged_never_summed():
    assert "no_till" in get(BASE, "reduced_tillage").overlaps
    assert "central_tyre_inflation" in get(BASE, "correct_tyre_pressure").overlaps


def test_farm_a_context_from_the_real_aggregates():
    ctx = farm_a_context()
    assert ctx.total_litres == pytest.approx(10813.7, abs=1)
    assert "ploughing" in ctx.litres_by_op and ctx.hectares_by_op["ploughing"] == pytest.approx(69.5, abs=0.1)
    assert min(ctx.tractor_kw.values()) == 77
    states = {r.intervention_id: r.state for r in rank_interventions(ctx)}
    assert states["electric_tractor"] == "not_feasible"
    assert states["reduced_tillage"] == "feasible"
    assert states["correct_tyre_pressure"] == "needs_info"
