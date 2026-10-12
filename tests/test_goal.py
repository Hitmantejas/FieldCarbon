"""Goal setting: a suggested start from the pain points, and whether each idea can reach the goal alone."""
import pytest

from backend.ranking.goal import suggested_goal_pct, verdict
from backend.tools.set_goal import set_goal

JARGON = ("Establishment", "establishment", "GBP", "published", "RTFC", "derivation")


@pytest.mark.parametrize("low, high, target, expected", [
    (10, 30, 5, "reaches"),        # even the lowest estimate gets there
    (10, 30, 10, "reaches"),       # exactly on the goal counts
    (10, 30, 20, "might_reach"),   # only the optimistic end gets there
    (10, 30, 30, "might_reach"),
    (10, 30, 31, "falls_short"),   # even the best estimate is not enough
])
def test_verdict_depends_on_which_end_of_the_range_reaches_the_goal(low, high, target, expected):
    assert verdict(low, high, target) == expected


def test_suggested_goal_rounds_the_pain_points_up_to_the_next_5_percent():
    assert suggested_goal_pct(963.6, 10813.7) == 10   # 8.9% of fuel
    assert suggested_goal_pct(1000, 10000) == 10      # exactly 10% stays 10
    assert suggested_goal_pct(1500, 10000) == 15
    assert suggested_goal_pct(10, 10000) == 5         # never below 5%


def test_default_goal_is_the_suggested_one_and_says_why():
    g = set_goal()
    assert g["target_pct"] == g["suggested_pct"] == 10
    assert "pain points" in g["suggested_how"] and "10%" in g["suggested_how"]


def test_target_figures_are_the_goal_applied_to_the_farm_totals():
    g = set_goal(20)
    assert g["target_co2e"]["value"] == pytest.approx(0.20 * 36572.6, rel=1e-3)
    assert g["target_litres"]["value"] == pytest.approx(0.20 * 10813.7, rel=1e-3)
    assert {"tum_alc_data", "uk_ghg_2025"} <= set(g["target_co2e"]["source_ids"])
    assert g["target_co2e"]["label"] == "measured"


def test_verdicts_at_a_20_percent_goal_for_farm_a():
    got = {i["intervention_id"]: i["verdict"] for i in set_goal(20)["ideas"]}
    assert got["no_till"] == "reaches"
    assert got["hvo_switch"] == "reaches"
    assert got["reduced_tillage"] == "falls_short"  # counted on ploughed fields only: best case ~5.1 t of ~7.3 t
    assert got["shift_up_throttle_down"] == "falls_short"
    assert got["electric_tractor"] == "not_applicable"


def test_ideas_keep_the_evidence_ranking_order_and_cover_all_eight():
    ideas = set_goal(20)["ideas"]
    assert len(ideas) == 8
    assert [i["state"] for i in ideas] == sorted((i["state"] for i in ideas), key=["feasible", "needs_info", "not_feasible"].index)


def test_reach_is_a_labelled_sourced_range_and_missing_when_not_applicable():
    for idea in set_goal(20)["ideas"]:
        if idea["verdict"] == "not_applicable":
            assert idea["reach"] is None
        else:
            reach = idea["reach"]
            assert reach["label"] == "estimated" and reach["source_ids"] and reach["low"] <= reach["high"]


def test_an_idea_that_burns_more_fuel_or_costs_more_is_flagged_in_plain_words():
    hvo = next(i for i in set_goal(20)["ideas"] if i["intervention_id"] == "hvo_switch")
    assert "more fuel" in hvo["warning"] and "costs more" in hvo["warning"]
    no_till = next(i for i in set_goal(20)["ideas"] if i["intervention_id"] == "no_till")
    assert no_till["warning"] is None


@pytest.mark.parametrize("bad", [0, -5, 91, 200])
def test_goals_outside_1_to_90_percent_are_rejected(bad):
    with pytest.raises(ValueError):
        set_goal(bad)


def test_goal_texts_use_plain_words():
    g = set_goal(20)
    texts = [g["suggested_how"], g["target_co2e"]["how"], g["target_litres"]["how"]]
    texts += [i["reach"]["how"] for i in g["ideas"] if i["reach"]] + [i["warning"] for i in g["ideas"] if i["warning"]]
    assert not [t for t in texts if any(word in t for word in JARGON)]
