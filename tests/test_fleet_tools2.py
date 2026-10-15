"""Fleet tools, batch 2: peer benchmarking, anomalies, evidence-based opportunities and what-if scenarios."""
import re

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.rank_interventions import rank_interventions
from backend.tools.what_if import what_if

client = TestClient(app)
INTERNAL_ID = re.compile(r"\b[a-z]{2,}_[a-z0-9]+(?:_[a-z0-9]+)*\b")


def figures(node):
    if isinstance(node, dict):
        if "label" in node and "how" in node and "source_ids" in node:
            yield node
        for value in node.values():
            yield from figures(value)
    elif isinstance(node, list):
        for value in node:
            yield from figures(value)


def plain_and_sourced(result):
    found = list(figures(result))
    assert found
    for f in found:
        assert f["label"] in {"measured", "allocated", "estimated"} and f["source_ids"], f
        assert all(line.startswith("- ") for line in f["how"].split("\n")) and "**" in f["how"], f["how"]
        assert not INTERNAL_ID.search(f["how"]), f["how"]


# ---- benchmark_peers -------------------------------------------------------------------------------------
def test_benchmark_groups_need_enough_machines_and_jobs():
    r = benchmark_peers()
    assert r["groups"]
    for g in r["groups"]:
        assert len(g["peers"]) >= 3 and all(p["jobs"] >= 3 for p in g["peers"])
    assert not [g for g in r["groups"] if g["site_id"] == "S3"]          # one machine has no peers


def test_peer_spread_is_found_in_the_vineyard_and_the_arable_site():
    sites = {g["site_id"] for g in benchmark_peers()["groups"]}
    assert {"S1", "S2"} <= sites


def test_flagged_machines_are_well_above_the_peer_median_and_the_stake_is_a_range():
    flagged = [p for g in benchmark_peers()["groups"] for p in g["peers"] if p["above_peers"]]
    assert flagged
    for p in flagged:
        assert p["difference_pct"] >= 25
        s = p["litres_at_stake"]
        assert 0 <= s["low"] <= s["high"] and s["high"] > 0


def test_stake_never_exceeds_the_fuel_the_machine_burned_on_that_job_type():
    for g in benchmark_peers()["groups"]:
        for p in g["peers"]:
            if p["above_peers"]:
                assert p["litres_at_stake"]["high"] <= p["litres"] + 1e-6


def test_benchmark_says_these_are_differences_to_investigate_not_waste():
    g = benchmark_peers()["groups"][0]
    assert "investigate" in g["caveat"].lower() and "waste" not in g["caveat"].lower()


def test_benchmark_filters_and_figures():
    r = benchmark_peers(site_id="S2", operation_code="vy_mulching")
    assert [g["operation_code"] for g in r["groups"]] == ["vy_mulching"]
    plain_and_sourced(r)


# ---- detect_anomalies --------------------------------------------------------------------------------------
def test_the_frozen_recorder_on_tractor_4_is_reported_as_a_data_gap():
    gaps = [f for f in detect_anomalies()["findings"] if f["kind"] == "data_gap"]
    t4 = next(f for f in gaps if f["machine_id"] == "S1-T4")
    assert t4["litres"]["value"] == pytest.approx(92.9, abs=2) and t4["litres"]["unit"] == "h"
    assert "Tractor 4" in t4["title"]


def test_job_outliers_use_robust_statistics_and_are_a_small_share_of_jobs():
    out = [f for f in detect_anomalies()["findings"] if f["kind"] == "job_outlier"]
    assert 5 <= len(out) <= 40
    assert all(abs(f["robust_z"]) >= 3.5 and abs(f["difference_pct"]) >= 30 for f in out)


def test_anomalies_never_name_or_rank_operators():
    r = detect_anomalies()
    assert "OP-" not in str(r) and "operator" not in " ".join(f["title"].lower() for f in r["findings"])


def test_anomaly_texts_are_plain_and_every_figure_is_sourced():
    plain_and_sourced(detect_anomalies())


# ---- fleet_opportunities -----------------------------------------------------------------------------------
def states(result):
    return {i["intervention_id"]: i["state"] for i in result["ideas"]}


def test_arable_sites_get_the_evidence_engine_on_their_measured_jobs():
    s = states(fleet_opportunities())
    assert s["reduced_tillage"] == "feasible" and s["electric_tractor"] == "not_feasible"
    assert s["correct_tyre_pressure"] == "needs_info"


def test_site_one_matches_the_original_farm_a_figures():
    mine = next(i for i in fleet_opportunities(site_id="S1")["ideas"] if i["intervention_id"] == "reduced_tillage")
    farm = next(i for i in rank_interventions() if i["intervention_id"] == "reduced_tillage")
    a, b = mine["figures"]["litres_saved"], farm["figures"]["litres_saved"]
    assert a["low"] == pytest.approx(b["low"], rel=0.01) and a["high"] == pytest.approx(b["high"], rel=0.01)


def test_the_vineyard_has_no_applicable_evidence_and_says_so():
    r = fleet_opportunities(site_id="S2")
    assert r["ideas"] == [] and "vineyard" in r["reason"].lower()


def test_opportunities_are_labelled_sourced_and_cite_evidence():
    r = fleet_opportunities()
    assert all(i["evidence"] for i in r["ideas"])
    plain_and_sourced(r)


# ---- what_if -----------------------------------------------------------------------------------------------
def test_cutting_the_not_working_fuel_by_a_fifth_is_simple_arithmetic():
    r = what_if("implement_not_working", 20, site_id="S1")
    assert r["is_scenario"] is True and r["available"] is True
    assert r["litres_saved"]["value"] == pytest.approx(0.2 * 2517.3, rel=0.01)
    assert r["co2e_avoided_kg"]["value"] == pytest.approx(r["litres_saved"]["value"] * 3.38206, rel=1e-3)
    assert r["co2e_avoided_kg"]["label"] == "estimated" and "assum" in r["assumption"].lower()
    assert 0.65 < r["cost_saved_gbp"]["value"] / r["litres_saved"]["value"] < 1.2
    plain_and_sourced(r)


def test_not_working_fuel_is_not_available_for_the_vineyard():
    r = what_if("implement_not_working", 20, site_id="S2")
    assert r["available"] is False and r["reason"]


def test_bringing_flagged_machines_to_the_peer_median_uses_the_benchmark_range():
    r = what_if("peer_outliers", 100)
    bench = benchmark_peers()["groups"]
    lo = sum(p["litres_at_stake"]["low"] for g in bench for p in g["peers"] if p["above_peers"])
    hi = sum(p["litres_at_stake"]["high"] for g in bench for p in g["peers"] if p["above_peers"])
    assert r["litres_saved"]["low"] == pytest.approx(lo, rel=1e-6) and r["litres_saved"]["high"] == pytest.approx(hi, rel=1e-6)


def test_switching_half_the_fuel_to_hvo_burns_more_litres_but_cuts_co2e():
    r = what_if("hvo", 50)
    total = 16493.0
    assert r["litres_saved"]["value"] == pytest.approx(-0.5 * total * 0.041, rel=0.01)   # more litres burned
    assert r["co2e_avoided_kg"]["value"] > 0.4 * total * 3.38206 * 0.6
    assert r["cost_saved_gbp"]["high"] < 0                                              # it costs more
    assert "rough" in r["cost_saved_gbp"]["how"].lower() or "quote" in r["cost_saved_gbp"]["how"].lower()
    plain_and_sourced(r)


def test_what_if_rejects_nonsense():
    with pytest.raises(ValueError):
        what_if("colour", 10)
    with pytest.raises(ValueError):
        what_if("hvo", 0)
    with pytest.raises(ValueError):
        what_if("hvo", 101)


# ---- API -----------------------------------------------------------------------------------------------------
def test_batch_two_api_endpoints():
    assert client.get("/api/fleet/benchmark").json()["groups"]
    assert client.get("/api/fleet/anomalies").json()["findings"]
    assert client.get("/api/fleet/opportunities?site_id=S1").json()["ideas"]
    assert client.get("/api/fleet/what-if?change=implement_not_working&amount_pct=20&site_id=S1").json()["available"] is True
    assert client.get("/api/fleet/what-if?change=colour&amount_pct=20").status_code == 422
    assert client.get("/api/fleet/what-if?change=hvo&amount_pct=0").status_code == 422


def test_answers_to_the_open_questions_reach_the_opportunities_endpoint():
    def state(url: str, idea: str) -> str:
        return next(i for i in client.get(url).json()["ideas"] if i["intervention_id"] == idea)["state"]

    assert state("/api/fleet/opportunities", "central_tyre_inflation") == "needs_info"
    assert state("/api/fleet/opportunities?has_ctis=true", "central_tyre_inflation") == "not_feasible"
    assert state("/api/fleet/opportunities?ballast_type=none", "avoid_liquid_ballast") == "not_feasible"
    assert state("/api/fleet/opportunities?ballast_type=liquid", "avoid_liquid_ballast") == "feasible"


def test_fuel_findings_point_at_machines_and_never_at_people():
    """A1 (fuel handed out but not burned) stays a machine-month finding: no operator id, key or name anywhere in it."""
    import json

    from backend.tools.reconcile_fuel import reconcile_fuel

    for result in (reconcile_fuel(), detect_anomalies()):
        text = json.dumps(result).lower()
        assert "operator" not in text and not re.search(r"\bop-\d+", text)
    a1 = [f for f in reconcile_fuel()["findings"] if f["kind"] == "machine_over_dispense"]
    assert a1 and all(f["machine_id"] for f in a1)


def test_a_frozen_recorder_title_names_the_machine_plainly_and_short_gaps_keep_a_decimal():
    titles = [f["title"] for f in detect_anomalies()["findings"] if f["kind"] == "data_gap"]
    assert "The recorder on Tractor 4, 163 kW froze for 92 hours" in titles
    assert "The recorder on Tractor 3, 140 kW froze for 1.4 hours" in titles
