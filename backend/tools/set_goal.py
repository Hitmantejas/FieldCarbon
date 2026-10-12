from dataclasses import asdict

from backend.emissions.farm_summary import farm_a_rows, summarise
from backend.emissions.pain_points import above_range, farm_a_ratings
from backend.emissions.text import bullets
from backend.ranking.goal import MAX_GOAL_PCT, MIN_GOAL_PCT, suggested_goal_pct, verdict
from backend.tools.contracts import Figure
from backend.tools.rank_interventions import rank_interventions


def _warning(figures: dict) -> str | None:
    litres, running = figures["litres_saved"], figures["running_cost_change_gbp"]
    parts = []
    if litres and litres["high"] < 0:
        parts.append("burns more fuel")
    if running and running["low"] > 0:
        parts.append("costs more to run")
    return f"It {' and '.join(parts)}. The Plan has the numbers." if parts else None


def set_goal(target_pct: float | None = None, farm_id: str = "a", known: dict | None = None) -> dict:
    """A cut-my-emissions goal in real numbers, and which ideas could reach it on their own."""
    if farm_id != "a":
        raise KeyError(f"unknown farm {farm_id}")
    totals = summarise(farm_a_rows())
    total_litres, total_co2e = totals.litres.value, totals.co2e_kg.value
    stake = above_range(farm_a_ratings()[0])
    suggested = suggested_goal_pct(stake.litres_high, total_litres)
    pct = suggested if target_pct is None else target_pct
    if not MIN_GOAL_PCT <= pct <= MAX_GOAL_PCT:
        raise ValueError(f"goal must be between {MIN_GOAL_PCT}% and {MAX_GOAL_PCT}%")

    ideas = []
    for item in rank_interventions(farm_id, known):
        saving = item["figures"]["co2e_avoided_kg"]
        reach, outcome = None, "not_applicable"
        if saving:
            low, high = saving["low"] / total_co2e * 100, saving["high"] / total_co2e * 100
            outcome = verdict(low, high, pct)
            size = (f"{saving['low'] / 1000:.1f} tonnes" if saving["low"] == saving["high"]
                    else f"{saving['low'] / 1000:.1f} to {saving['high'] / 1000:.1f} tonnes")
            reach = asdict(Figure(
                low if low == high else None, "% of your emissions", "estimated",
                bullets(f"This idea saves **{size} of CO2** a year.",
                        f"You release **{total_co2e / 1000:.1f} tonnes** now, so that is **{low:.1f}% to {high:.1f}%** of your emissions."
                        if low != high else
                        f"You release **{total_co2e / 1000:.1f} tonnes** now, so that is **about {low:.1f}%** of your emissions."),
                source_ids=tuple(saving["source_ids"]), low=low, high=high))
        ideas.append({k: item[k] for k in ("intervention_id", "name", "state", "robustness", "n_sources", "missing_inputs")}
                     | {"verdict": outcome, "reach": reach, "warning": _warning(item["figures"])})

    return {
        "target_pct": pct,
        "suggested_pct": suggested,
        "suggested_how": (f"Your pain points add up to about {stake.litres_low / total_litres * 100:.0f} to "
                          f"{stake.litres_high / total_litres * 100:.0f}% of your fuel, so we suggest {suggested}%."),
        "target_co2e": asdict(Figure(total_co2e * pct / 100, "kg CO2e per year", "measured",
                                     bullets(f"**{pct:g}%** of your yearly emissions of **{total_co2e / 1000:.1f} tonnes** of CO2."),
                                     source_ids=totals.co2e_kg.source_ids)),
        "target_litres": asdict(Figure(total_litres * pct / 100, "L per year", "measured",
                                       bullets(f"**{pct:g}%** of the **{total_litres:,.0f} litres** of fuel you used."),
                                       source_ids=totals.litres.source_ids)),
        "counts": {v: sum(i["verdict"] == v for i in ideas)
                   for v in ("reaches", "might_reach", "falls_short", "not_applicable")},
        "ideas": ideas,
    }
