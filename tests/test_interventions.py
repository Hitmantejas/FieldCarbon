"""rank_interventions: applicability, saving ranges and robustness ranking (offline)."""
import pytest

from backend.emissions.factors import wtw_factor
from backend.ranking.interventions import FarmProfile, Tractor, farm_a_profile, rank_interventions

GAS_OIL = wtw_factor("gas_oil", 2025).kg_per_unit
HVO = wtw_factor("hvo", 2025).kg_per_unit


def profile(load=40.0, plough=True, kw=(77.0,), facts=None, fuel="gas_oil") -> FarmProfile:
    jobs = {"ploughing": 1000.0 if plough else 0.0, "disc_harrowing": 200.0, "mulching": 100.0, "transport": 50.0}
    return FarmProfile(
        farm_id="t", fuel_type=fuel, total_litres=2000.0, job_litres=jobs,
        working_load_pct={"ploughing": load, "disc_harrowing": load, "mulching": load},
        ploughed_field_litres={"ploughing": 1000.0, "disc_harrowing": 100.0} if plough else {},
        ploughed_fields=3 if plough else 0,
        tractors=tuple(Tractor(f"T{i}", k, 2000.0 / len(kw)) for i, k in enumerate(kw)),
        facts=facts or {},
    )


def by_id(farm: FarmProfile) -> dict:
    return {r.intervention_id: r for r in rank_interventions(farm)}


def test_electric_tractor_only_for_small_tractors():
    assert by_id(profile(kw=(77.0,)))["electric_tractor"].status == "not_applicable"
    small = by_id(profile(kw=(20.0, 77.0)))["electric_tractor"]
    assert small.status == "applies"
    assert small.litres_saved.low == pytest.approx(1000.0)  # only the 20 kW tractor's diesel
    assert small.co2e_avoided_kg.low == pytest.approx(1000.0 * GAS_OIL * 0.678)
    assert small.cost_saved_gbp is None  # electricity price not sourced


@pytest.mark.parametrize("checked,status,needs", [(None, "conditional", "tyre_pressure_checked"),
                                                  (False, "applies", None), (True, "not_applicable", None)])
def test_unknown_facts_make_an_intervention_conditional(checked, status, needs):
    r = by_id(profile(facts={"tyre_pressure_checked": checked}))["correct_tyre_pressure"]
    assert (r.status, r.needs) == (status, needs)


def test_conditional_still_shows_the_range_it_would_save():
    r = by_id(profile())["avoid_liquid_ballast"]
    assert r.status == "conditional" and r.needs == "ballast_type"
    # Tillage and seeding jobs only: ploughing + disc harrowing (mulching is outside its categories).
    assert r.litres_saved.low == pytest.approx(1200.0 * 0.048)
    assert r.litres_saved.high == pytest.approx(1200.0 * 0.091)


def test_manufacturer_claim_is_context_not_counted():
    r = by_id(profile())["correct_tyre_pressure"]
    assert r.context_source_ids == ("valtra2023",)
    assert "valtra2023" not in r.source_ids and r.n_sources == 2
    assert r.litres_saved.low == pytest.approx(1200.0 * 0.035)
    assert r.litres_saved.high == pytest.approx(1200.0 * 0.20)


def test_tillage_needs_ploughing_and_uses_only_ploughed_fields():
    assert by_id(profile(plough=False))["reduced_tillage"].status == "not_applicable"
    r = by_id(profile())["reduced_tillage"]
    assert r.status == "applies" and r.n_sources == 3
    assert r.litres_saved.low == pytest.approx(1100.0 * 0.12)  # 1000 ploughing + 100 disc on ploughed fields
    assert r.litres_saved.high == pytest.approx(1100.0 * 0.594)
    assert r.overlaps_with == ("no_till",)


@pytest.mark.parametrize("load,low,high", [(40.0, 0.149, 0.21), (60.0, 0.107, 0.50)])
def test_shift_up_uses_the_evidence_for_the_load_level_and_drawbar_jobs_only(load, low, high):
    r = by_id(profile(load=load))["shift_up_throttle_down"]
    drawbar = 1200.0  # ploughing + disc harrowing; mulching is PTO-driven
    assert r.litres_saved.low == pytest.approx(drawbar * low)
    assert r.litres_saved.high == pytest.approx(drawbar * high)


def test_shift_up_not_applicable_at_high_load():
    r = by_id(profile(load=80.0))["shift_up_throttle_down"]
    assert r.status == "not_applicable" and r.litres_saved is None


def test_hvo_adds_litres_and_cuts_co2e_through_the_factor():
    r = by_id(profile())["hvo_switch"]
    assert r.litres_saved.value == pytest.approx(-2000.0 * 0.041)
    assert r.co2e_avoided_kg.value == pytest.approx(2000.0 * GAS_OIL - 2000.0 * 1.041 * HVO)
    assert r.cost_saved_gbp is None
    assert by_id(profile(fuel="electricity_uk"))["hvo_switch"].status == "not_applicable"


def test_every_figure_is_estimated_and_cites_its_evidence():
    for r in rank_interventions(profile()):
        for fig in (r.litres_saved, r.co2e_avoided_kg, r.cost_saved_gbp):
            if fig is not None:
                assert fig.label == "estimated"
                assert set(r.source_ids) <= set(fig.source_ids)
                assert fig.low <= fig.high


def test_ranking_is_by_status_then_most_certain_co2e_saving():
    ranked = rank_interventions(profile())
    assert [r.rank for r in ranked] == list(range(1, len(ranked) + 1))
    order = ["applies", "conditional", "not_applicable"]
    assert [order.index(r.status) for r in ranked] == sorted(order.index(r.status) for r in ranked)
    applies = [r.co2e_avoided_kg.low for r in ranked if r.status == "applies"]
    assert applies == sorted(applies, reverse=True)


def test_farm_a():
    farm = farm_a_profile()
    r = by_id(farm)
    assert r["electric_tractor"].status == "not_applicable"
    assert {r[i].status for i in ("correct_tyre_pressure", "central_tyre_inflation", "avoid_liquid_ballast")} == {
        "conditional"}
    assert farm.ploughed_fields > 0
    # Deep cultivating on fields that were never ploughed is already conservation tillage: not counted.
    assert farm.ploughed_field_litres["cultivating_deep"] < farm.job_litres["cultivating_deep"]
    assert r["shift_up_throttle_down"].status == "applies"
    assert farm.working_load_pct["ploughing"] > 75
    assert "ploughing " not in r["shift_up_throttle_down"].how
