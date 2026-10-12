from dataclasses import asdict

from backend.emissions.text import bullets
from backend.tools.contracts import Figure
from backend.tools.rank_interventions import rank_interventions
from backend.tools.set_goal import set_goal

# Each open question belongs to one idea, and has two possible answers.
FIELD_IDEA = {
    "tyre_pressure_checked": "correct_tyre_pressure",
    "has_ctis": "central_tyre_inflation",
    "ballast_type": "avoid_liquid_ballast",
}
OPTIONS = {"tyre_pressure_checked": (True, False), "has_ctis": (True, False), "ballast_type": ("liquid", "none")}

REACH_TEXT = {
    "reaches": "On its own it **could reach your {pct:g}% goal**.",
    "might_reach": "On its own it **might reach your {pct:g}% goal**.",
    "falls_short": "On its own it **cannot reach your {pct:g}% goal**, but it would still save you fuel.",
}


def _answer_plan(field: str, option, target_pct, known: dict, farm_id: str):
    answers = {**known, field: option}
    idea_id = FIELD_IDEA[field]
    item = next(i for i in rank_interventions(farm_id, answers) if i["intervention_id"] == idea_id)
    verdict = next(i for i in set_goal(target_pct, farm_id, answers)["ideas"] if i["intervention_id"] == idea_id)["verdict"]
    applies = item["state"] == "feasible"
    return item, {"answer": option, "applies": applies, "verdict": verdict,
                  "litres_saved": item["figures"]["litres_saved"] if applies else None}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def still_uncertain(farm_id: str = "a", known: dict | None = None) -> list[str]:
    """What stays uncertain however the questions are answered, worked out from the plan itself."""
    ideas = [i for i in rank_interventions(farm_id, known) if i["state"] != "not_feasible"]
    out = ["We do not know what you pay for diesel, so every money figure is a range."]
    thin = sum(i["robustness"] == "limited" for i in ideas)
    if thin:
        out.append(f"{_plural(thin, 'of your ideas rests', 'of your ideas rest')} on a single source.")
    unpriced = sum(i["figures"]["cost"] is None for i in ideas)
    if unpriced:
        out.append(f"We have no price for {_plural(unpriced, 'of your ideas', 'of your ideas')}.")
    if any(i["intervention_id"] in {"reduced_tillage", "no_till"} for i in ideas):
        out.append("We have no figures on how reduced tillage or no-till would change your crop yield.")
    return out


def what_would_improve(target_pct: float | None = None, farm_id: str = "a", known: dict | None = None) -> dict:
    """Which unanswered question would change your plan most, and what each answer would do."""
    known = known or {}
    goal = set_goal(target_pct, farm_id, known)  # validates the goal and resolves the default
    pct = goal["target_pct"]
    questions = []
    for field in (f for f in FIELD_IDEA if f not in known):
        results = [_answer_plan(field, option, pct, known, farm_id) for option in OPTIONS[field]]
        applies = next((item, out) for item, out in results if out["applies"])
        item, outcome = applies
        saved = outcome["litres_saved"]
        questions.append({
            "field": field,
            "intervention_id": FIELD_IDEA[field],
            "name": item["name"],
            "outcomes": [out for _, out in results],
            "matters_for_goal": outcome["verdict"] in ("reaches", "might_reach"),
            "swing": asdict(Figure(
                None, "L per year", "estimated",
                bullets(f"If this idea applies to you, it could save **{saved['low']:,.0f} to {saved['high']:,.0f} litres** a year.",
                        "If it does not apply, it drops out of your plan.",
                        REACH_TEXT[outcome["verdict"]].format(pct=pct)),
                source_ids=tuple(saved["source_ids"]), low=saved["low"], high=saved["high"])),
        })
    # A question whose idea could reach the goal comes first; then the bigger possible swing in fuel.
    questions.sort(key=lambda q: (not q["matters_for_goal"], -q["swing"]["high"]))
    return {"target_pct": pct, "top": questions[0]["field"] if questions else None, "questions": questions,
            "still_uncertain": still_uncertain(farm_id, known)}
