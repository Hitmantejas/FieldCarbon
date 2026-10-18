import numpy as np

from backend.fleet import data
from backend.tools import action_impact
from evals import proof_calibration as pc


def test_a_planted_effect_is_applied_to_the_changed_machines_only_and_the_tool_is_restored():
    jobs = data.jobs()[lambda d: d.site_id == pc.SITE]
    original = action_impact.jobs
    result = pc._one_trial(jobs, np.random.default_rng(3), -30)
    assert action_impact.jobs is original
    assert result["action"]["site_id"] == pc.SITE and result["status"] in {"reduction_shown", "cant_tell_yet", "not_enough_jobs"}


def test_a_thirty_per_cent_cut_is_usually_found_and_a_placebo_is_usually_unclear():
    s = pc.score(trials=12)
    placebo, big = s["rows"][0], next(r for r in s["rows"] if r["effect_pct"] == -30)
    assert big["reduction_shown"] > placebo["reduction_shown"] + placebo["increase_shown"]
    assert placebo["cant_tell_yet"] >= placebo["judged"] // 2
    assert 0 <= s["placebo_false_claim_rate"] <= 1


def test_the_rise_is_never_called_a_saving():
    rows = pc.score(trials=12)["rows"]
    assert next(r for r in rows if r["effect_pct"] == 10)["reduction_shown"] == 0
