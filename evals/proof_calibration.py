"""Before-and-after calibration: does action_impact claim savings that are not there, and does its range hold the truth?

The proof-recovery eval has two planted changes. This one uses the real vineyard fuel records (real tractors, real dates,
real seasons) and invents changes at random: a random half of the tractors, a random start date, and an effect of known size
applied to the changed tractors' later jobs. With no effect (a placebo) the tool should rarely call a saving or a rise.
With an effect it should find it, and the 90% range should hold the true value about 9 times in 10.

Run: python -m evals.proof_calibration
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.fleet import data
from backend.tools import action_impact as ai

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results" / "proof_calibration.json"
SEED = 2026
TRIALS = 150
SITE = "S2"  # the vineyard: real dates and real seasonality
EFFECTS_PCT = (0, -5, -10, -20, -30, 10)  # change in litres on the changed tractors after the start date
NO_OVERLAY = pd.DataFrame(columns=["job_id", "action_id", "litres_with_action"])


def _one_trial(jobs: pd.DataFrame, rng: np.random.Generator, effect_pct: float) -> dict:
    machines = sorted(jobs.machine_id.unique())
    changed = rng.choice(machines, size=len(machines) // 2, replace=False)
    dates = jobs.start_ts.sort_values()
    start = dates.iloc[int(rng.integers(len(dates) // 5, 4 * len(dates) // 5))].normalize()
    after = jobs.machine_id.isin(changed) & (jobs.start_ts >= start)
    shifted = jobs.assign(litres=np.where(after, jobs.litres * (1 + effect_pct / 100), jobs.litres))
    action = pd.Series({"site_id": SITE, "machine_ids": ";".join(changed), "start_date": start, "name": "placebo",
                        "intervention_id": "none", "what_changed": "", "is_synthetic": True}, name="PLACEBO")
    original, ai.jobs = ai.jobs, lambda: shifted
    try:
        result = ai._one(action, NO_OVERLAY)
    finally:
        ai.jobs = original
    return result


def _row(effect_pct: float, results: list[dict]) -> dict:
    judged = [r for r in results if r["change_pct"]]
    status = lambda s: sum(r["status"] == s for r in judged)  # noqa: E731
    # the truth for a litres change of e% on every changed job is exactly e% in litres per hectare
    inside = sum(r["change_pct"]["low"] <= effect_pct <= r["change_pct"]["high"] for r in judged)
    return {"effect_pct": effect_pct, "trials": len(results), "judged": len(judged),
            "not_enough_jobs": len(results) - len(judged),
            "reduction_shown": status("reduction_shown"), "increase_shown": status("increase_shown"),
            "cant_tell_yet": status("cant_tell_yet"),
            "range_holds_truth": inside, "coverage": round(inside / len(judged), 3) if judged else None,
            "median_width_pts": round(float(np.median([r["change_pct"]["high"] - r["change_pct"]["low"] for r in judged])), 1) if judged else None}


def score(trials: int | None = None) -> dict:
    jobs = data.jobs()
    jobs = jobs[jobs.site_id == SITE]
    rng = np.random.default_rng(SEED)
    rows = [_row(e, [_one_trial(jobs, rng, e) for _ in range(trials or TRIALS)]) for e in EFFECTS_PCT]
    placebo = rows[0]
    return {"seed": SEED, "site": SITE, "trials_per_effect": trials or TRIALS, "rows": rows,
            "placebo_false_claim_rate": round((placebo["reduction_shown"] + placebo["increase_shown"]) / placebo["judged"], 3),
            "reading_it": "effect_pct is the planted change in litres per hectare on the changed tractors. For the placebo row "
                          "a claim of a saving or a rise is a false alarm; with a 90% range about 1 in 10 is expected by chance "
                          "(5% each way). coverage is the share of trials whose range holds the planted value."}


if __name__ == "__main__":
    result = score()
    RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{'effect':>7} {'judged':>6} {'saving':>7} {'rise':>5} {'unclear':>8} {'covers':>7} {'width':>6}")
    for r in result["rows"]:
        print(f"{r['effect_pct']:>6}% {r['judged']:>6} {r['reduction_shown']:>7} {r['increase_shown']:>5} {r['cant_tell_yet']:>8} "
              f"{r['coverage']!s:>7} {r['median_width_pts']!s:>6}   (too few jobs: {r['not_enough_jobs']})")
    print("placebo false-claim rate:", result["placebo_false_claim_rate"])
