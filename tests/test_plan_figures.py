"""Intervention figures follow the shared contract: labelled, sourced, ranges well-formed."""
from dataclasses import replace

import pytest

from backend.ranking.figures import plan_figures
from backend.ranking.interventions import evaluate
from backend.ranking.roi import calculate_roi
from backend.tools.rank_interventions import rank_interventions
from tests.test_interventions import BASE

KNOWN = replace(BASE, known={"tyre_pressure_checked": False, "has_ctis": False, "ballast_type": "liquid"})


def figures(ctx, intervention_id):
    result = next(r for r in evaluate(ctx) if r.intervention_id == intervention_id)
    return plan_figures(result, calculate_roi(result, ctx), ctx)


def test_every_figure_is_estimated_and_sourced():
    for iv in ("reduced_tillage", "central_tyre_inflation", "hvo_switch", "no_till"):
        for name, fig in figures(KNOWN, iv).items():
            if fig is not None:
                assert fig.label == "estimated", (iv, name)
                assert fig.source_ids, (iv, name)


def test_each_figure_cites_the_right_kind_of_source():
    f = figures(KNOWN, "central_tyre_inflation")
    assert "juselius_ctis" in f["litres_saved"].source_ids and "tum_alc_data" in f["litres_saved"].source_ids
    assert "uk_ghg_2025" in f["co2e_avoided_kg"].source_ids
    assert "defra_ukammg" in f["fuel_gbp_saved"].source_ids
    assert f["cost"].source_ids == ("fwi_ctis_prices_2022",)
    assert "fwi_ctis_prices_2022" in f["payback_years"].source_ids


def test_manufacturer_sources_do_not_back_a_figure():
    assert "valtra2023" not in figures(KNOWN, "correct_tyre_pressure")["litres_saved"].source_ids


def test_hvo_burns_more_litres_but_avoids_co2e():
    f = figures(BASE, "hvo_switch")
    assert f["litres_saved"].low == f["litres_saved"].high == pytest.approx(-0.041 * 3000)
    assert f["co2e_avoided_kg"].low > 0
    assert f["payback_years"] is None
    assert f["running_cost_change_gbp"].low > 0  # costs more to run


def test_no_cost_source_means_no_cost_or_payback_figure():
    f = figures(KNOWN, "avoid_liquid_ballast")
    assert f["cost"] is None and f["payback_years"] is None and f["litres_saved"] is not None


def test_not_feasible_has_no_figures_at_all():
    assert all(fig is None for fig in figures(BASE, "electric_tractor").values())


def test_tillage_running_cost_change_cites_its_cost_sources():
    f = figures(BASE, "reduced_tillage")
    # The cost rows, plus the farm's own hectares from telemetry.
    assert set(f["running_cost_change_gbp"].source_ids) == {"fwi_direct_drill_2006", "ahdb_pr311", "tum_alc_data"}


def test_tool_output_carries_figures_as_plain_dicts_and_no_duplicate_raw_numbers():
    item = rank_interventions()[0]
    assert item["figures"]["litres_saved"]["source_ids"]
    assert "litres_saved_low" not in item and "roi" not in item


JARGON = ("Establishment", "establishment", "GBP", "published", "RTFC", "do not add the two", "derivation", "kg CO2e")


def test_every_explanation_uses_plain_words():
    for item in rank_interventions():
        texts = [item["how"], item["notes"], item["reason"] or ""] + [f["how"] for f in item["figures"].values() if f]
        for text in texts:
            assert not any(word in text for word in JARGON), (item["intervention_id"], text)


def test_tillage_cost_explains_the_hectares_and_that_diesel_is_already_counted():
    how = figures(BASE, "no_till")["running_cost_change_gbp"].how
    assert "50 hectares" in how and "diesel you save is already counted" in how


def test_hvo_cost_explains_extra_litres_and_asks_for_a_quote():
    how = figures(BASE, "hvo_switch")["running_cost_change_gbp"].how
    assert "123 litres" in how and "supplier" in how


def test_unfit_reasons_are_in_plain_words():
    reasons = {i["intervention_id"]: i["reason"] for i in rank_interventions() if i["reason"]}
    assert "22.4" in reasons["electric_tractor"] and "small tractors" in reasons["electric_tractor"]
