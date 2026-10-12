"""Answers from the farmer change which ideas apply, through the tools and the API."""
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools.rank_interventions import rank_interventions
from backend.tools.set_goal import set_goal

client = TestClient(app)


def state(items, intervention_id):
    return next(i for i in items if i["intervention_id"] == intervention_id)["state"]


def test_no_answer_means_the_idea_waits_for_one():
    assert state(rank_interventions(), "correct_tyre_pressure") == "needs_info"


def test_tyre_pressure_answers_decide_whether_the_idea_applies():
    assert state(rank_interventions(known={"tyre_pressure_checked": False}), "correct_tyre_pressure") == "feasible"
    done = rank_interventions(known={"tyre_pressure_checked": True})
    assert state(done, "correct_tyre_pressure") == "not_feasible"


def test_ballast_and_ctis_answers():
    assert state(rank_interventions(known={"ballast_type": "liquid"}), "avoid_liquid_ballast") == "feasible"
    assert state(rank_interventions(known={"ballast_type": "none"}), "avoid_liquid_ballast") == "not_feasible"
    assert state(rank_interventions(known={"has_ctis": False}), "central_tyre_inflation") == "feasible"
    assert state(rank_interventions(known={"has_ctis": True}), "central_tyre_inflation") == "not_feasible"


def test_a_feasible_idea_moves_up_the_ranking_after_an_answer():
    before = [i["intervention_id"] for i in rank_interventions()]
    after = [i["intervention_id"] for i in rank_interventions(known={"tyre_pressure_checked": False})]
    assert after.index("correct_tyre_pressure") < before.index("correct_tyre_pressure")


def test_goal_uses_the_same_answers():
    idea = next(i for i in set_goal(20, known={"has_ctis": True})["ideas"] if i["intervention_id"] == "central_tyre_inflation")
    assert idea["verdict"] == "not_applicable"


def test_goal_counts_each_verdict_for_farm_a_at_20_percent():
    assert set_goal(20)["counts"] == {"reaches": 2, "might_reach": 1, "falls_short": 4, "not_applicable": 1}


def test_api_accepts_answers_and_rejects_nonsense():
    body = client.get("/api/farms/a/interventions?tyre_pressure_checked=false&ballast_type=none").json()
    assert state(body, "correct_tyre_pressure") == "feasible" and state(body, "avoid_liquid_ballast") == "not_feasible"
    assert client.get("/api/farms/a/interventions?ballast_type=bogus").status_code == 422
    goal = client.get("/api/farms/a/goal?target_pct=20&has_ctis=true").json()
    assert next(i for i in goal["ideas"] if i["intervention_id"] == "central_tyre_inflation")["verdict"] == "not_applicable"


def test_an_answer_that_rules_an_idea_out_explains_the_consequence():
    items = rank_interventions(known={"tyre_pressure_checked": True, "has_ctis": True, "ballast_type": "none"})
    reasons = {i["intervention_id"]: i["reason"] for i in items if i["state"] == "not_feasible"}
    assert "little left" in reasons["correct_tyre_pressure"]
    assert "nothing new to gain" in reasons["central_tyre_inflation"]
    assert "nothing to take out" in reasons["avoid_liquid_ballast"]


def test_the_suggestion_is_worded_as_a_suggestion():
    assert "we suggest 10%" in set_goal()["suggested_how"]
