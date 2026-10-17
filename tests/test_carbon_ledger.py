"""The carbon ledger: tonnes emitted, tonnes avoidable as honest ranges, tonnes proven, and cost per tonne."""
import re

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools.carbon_ledger import carbon_ledger
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.fleet_summary import fleet_summary

client = TestClient(app)
INTERNAL_ID = re.compile(r"\b[a-z]{2,}_[a-z0-9]+(?:_[a-z0-9]+)*\b")
OVERLAP_NOTE = "Effects overlap, so these are not added."


def figures(node):
    if isinstance(node, dict):
        if "label" in node and "how" in node and "source_ids" in node:
            yield node
        for value in node.values():
            yield from figures(value)
    elif isinstance(node, list):
        for value in node:
            yield from figures(value)


def feasible_actions(ledger):
    return [a for a in ledger["avoidable"]["actions"] if a["state"] == "feasible"]


def test_emitted_is_the_fleet_total_in_tonnes():
    ledger = carbon_ledger()
    total_kg = fleet_summary("site")["totals"]["co2e_kg"]
    assert ledger["emitted"]["unit"] == "t CO2e"
    assert ledger["emitted"]["value"] == pytest.approx(total_kg["value"] / 1000)
    assert ledger["emitted"]["label"] == total_kg["label"]


def test_sites_add_up_and_show_kg_per_hectare():
    ledger = carbon_ledger()
    assert {s["site_id"] for s in ledger["sites"]} == {"S1", "S2", "S3"}
    assert sum(s["co2e_t"]["value"] for s in ledger["sites"]) == pytest.approx(ledger["emitted"]["value"])
    assert all(s["kg_per_ha"]["value"] > 0 and s["kg_per_ha"]["unit"] == "kg CO2e per ha" for s in ledger["sites"])
    assert {s["site_id"]: s["covered_by_evidence"] for s in ledger["sites"]} == {"S1": True, "S2": False, "S3": True}


def test_top_action_is_the_strongest_feasible_idea_and_matches_its_range():
    ledger = carbon_ledger()
    ideas = fleet_opportunities()["ideas"]
    first = next(i for i in ideas if i["state"] == "feasible")
    top = ledger["avoidable"]["top_action"]
    assert top["intervention_id"] == first["intervention_id"]
    fig = first["figures"]["co2e_avoided_kg"]
    assert top["co2e_avoided_t"]["low"] == pytest.approx(fig["low"] / 1000)
    assert top["co2e_avoided_t"]["high"] == pytest.approx(fig["high"] / 1000)
    assert top["co2e_avoided_t"]["label"] == "estimated"


def test_actions_are_never_summed_into_a_point():
    ledger = carbon_ledger()
    combined = ledger["avoidable"]["combined"]
    actions = feasible_actions(ledger)
    assert combined["value"] is None
    assert combined["low"] == pytest.approx(max(a["co2e_avoided_t"]["low"] for a in actions))
    covered = ledger["avoidable"]["covered_emitted_t"]["value"]
    assert combined["high"] <= covered + 1e-9
    assert combined["high"] <= sum(a["co2e_avoided_t"]["high"] for a in actions) + 1e-9
    assert OVERLAP_NOTE in combined["how"]


def test_ideas_waiting_for_an_answer_are_listed_but_not_counted():
    ledger = carbon_ledger()
    waiting = [a for a in ledger["avoidable"]["actions"] if a["state"] == "needs_info"]
    assert waiting
    top_and_combined = ledger["avoidable"]["combined"]["low"], ledger["avoidable"]["combined"]["high"]
    only_feasible = max(a["co2e_avoided_t"]["low"] for a in feasible_actions(ledger))
    assert top_and_combined[0] == pytest.approx(only_feasible)


def test_the_vineyard_is_outside_what_the_evidence_covers():
    ledger = carbon_ledger()
    covered, emitted = ledger["avoidable"]["covered_emitted_t"]["value"], ledger["emitted"]["value"]
    assert 0 < covered < emitted
    assert ledger["avoidable"]["covered_share_pct"] == pytest.approx(100 * covered / emitted)
    assert "vineyard" in ledger["avoidable"]["not_covered"].lower()


def test_proven_tonnes_come_only_from_changes_whose_range_clears_zero():
    ledger = carbon_ledger()
    proven = ledger["proven"]
    assert proven["unit"] == "t CO2e" and proven["source_ids"] and proven["label"] == "estimated"
    assert 0 < proven["low"] <= proven["value"] <= proven["high"]
    assert [c["action_id"] for c in ledger["proven_changes"]] == ["ACT-01"]


def test_goal_verdicts():
    easy, hard = carbon_ledger(goal_pct=1)["goal"], carbon_ledger(goal_pct=90)["goal"]
    assert easy["top_action_verdict"] == "reaches"
    assert hard["top_action_verdict"] == "falls_short" and hard["combined_verdict"] == "falls_short"
    assert easy["target_co2e"]["value"] == pytest.approx(carbon_ledger()["emitted"]["value"] * 0.01)


@pytest.mark.parametrize("bad", [0, 0.5, 91])
def test_goal_out_of_range_is_refused(bad):
    with pytest.raises(ValueError):
        carbon_ledger(goal_pct=bad)


# ---- cost per tonne on the opportunities --------------------------------------------------------------------
def idea(name):
    return next(i for i in fleet_opportunities()["ideas"] if i["intervention_id"] == name)


def test_hvo_costs_money_per_tonne_avoided():
    fig = idea("hvo_switch")["figures"]["gbp_per_tco2e"]
    assert fig["unit"] == "GBP per tonne CO2e" and 0 < fig["low"] < fig["high"] and fig["label"] == "estimated"
    assert fig["source_ids"]


def test_tillage_saves_money_per_tonne_avoided():
    fig = idea("no_till")["figures"]["gbp_per_tco2e"]
    assert fig["high"] < 0
    assert "saves money" in fig["how"]


def test_cost_per_tonne_is_not_invented_when_the_cost_is_unsourced_or_one_off():
    shift = idea("shift_up_throttle_down")
    assert shift["figures"]["gbp_per_tco2e"] is None and shift["gbp_per_tco2e_note"] == "Cost not yet sourced"
    ctis = idea("central_tyre_inflation")
    assert ctis["figures"]["gbp_per_tco2e"] is None and "payback" in ctis["gbp_per_tco2e_note"]
    assert idea("electric_tractor")["gbp_per_tco2e_note"] == ""


def test_ledger_figures_are_labelled_sourced_and_plain():
    for f in figures(carbon_ledger()):
        assert f["label"] in {"measured", "allocated", "estimated"} and f["source_ids"], f
        assert all(line.startswith("- ") for line in f["how"].split("\n")) and "**" in f["how"], f["how"]
        assert not INTERNAL_ID.search(f["how"]), f["how"]


def test_api_returns_the_ledger_and_refuses_a_bad_goal():
    r = client.get("/api/fleet/ledger", params={"goal_pct": 30})
    assert r.status_code == 200 and r.json()["goal"]["target_pct"] == 30
    assert client.get("/api/fleet/ledger", params={"goal_pct": 0}).status_code == 422
