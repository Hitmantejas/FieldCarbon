"""'What would improve this answer': which open question matters most, decided by deterministic rules."""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools.what_would_improve import what_would_improve

client = TestClient(app)


def order(result):
    return [q["field"] for q in result["questions"]]


def test_with_no_answers_all_three_questions_are_open_and_tyre_pressure_comes_first():
    r = what_would_improve(10)
    assert set(order(r)) == {"tyre_pressure_checked", "has_ctis", "ballast_type"}
    assert r["top"] == "tyre_pressure_checked" == order(r)[0]


def test_a_question_whose_idea_could_reach_the_goal_beats_one_that_cannot():
    qs = {q["field"]: q for q in what_would_improve(10)["questions"]}
    assert qs["tyre_pressure_checked"]["matters_for_goal"] is True   # could reach 10% (up to ~11%)
    assert qs["has_ctis"]["matters_for_goal"] is False               # tops out near 5%


def test_at_a_big_goal_no_question_matters_for_the_goal_and_the_bigger_swing_wins():
    r = what_would_improve(50)
    assert not any(q["matters_for_goal"] for q in r["questions"])
    swings = [q["swing"]["high"] for q in r["questions"]]
    assert swings == sorted(swings, reverse=True)


def test_each_question_shows_what_each_answer_would_do():
    q = what_would_improve(10)["questions"][0]
    applies = [o for o in q["outcomes"] if o["applies"]]
    drops = [o for o in q["outcomes"] if not o["applies"]]
    assert len(applies) == 1 and len(drops) == 1
    assert applies[0]["litres_saved"] is not None and drops[0]["litres_saved"] is None
    assert drops[0]["verdict"] == "not_applicable"


def test_the_swing_is_a_labelled_sourced_range_with_plain_bullets():
    swing = what_would_improve(10)["questions"][0]["swing"]
    assert swing["label"] == "estimated" and swing["source_ids"] and swing["low"] < swing["high"]
    assert all(line.startswith("- ") for line in swing["how"].split("\n")) and "**" in swing["how"]
    assert "reach your" in swing["how"]


def test_answered_questions_are_no_longer_asked_and_the_next_one_moves_up():
    r = what_would_improve(10, known={"tyre_pressure_checked": False})
    assert "tyre_pressure_checked" not in order(r)
    assert r["top"] == order(r)[0]


def test_when_everything_is_answered_there_is_nothing_to_ask():
    r = what_would_improve(10, known={"tyre_pressure_checked": False, "has_ctis": False, "ballast_type": "liquid"})
    assert r["questions"] == [] and r["top"] is None


def test_what_stays_uncertain_is_derived_from_the_plan_in_plain_words():
    items = what_would_improve(10)["still_uncertain"]
    assert any("price" in t for t in items)                      # the diesel price is only known as a range
    assert any("yield" in t for t in items)                      # tillage ideas have no yield figures
    assert not any("_" in t for t in items)                      # no internal names


def test_api_endpoint_takes_the_same_goal_and_answers():
    body = client.get("/api/farms/a/sharpen?target_pct=10&tyre_pressure_checked=false").json()
    assert body["top"] != "tyre_pressure_checked"
    assert client.get("/api/farms/a/sharpen?target_pct=0").status_code == 422
    assert client.get("/api/farms/z/sharpen").status_code == 404


def test_goal_outside_the_allowed_range_is_rejected():
    with pytest.raises(ValueError):
        what_would_improve(95)
