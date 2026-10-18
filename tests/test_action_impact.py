"""Before-and-after proof: a logged change counts only when its range clears zero, judged against the other machines."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.fleet.data import FLEET, action_overlay, jobs, ledger
from backend.tools import action_impact as mod
from backend.tools.action_impact import action_impact

client = TestClient(app)


def _by_id():
    return {a["action"]["action_id"]: a for a in action_impact()["actions"]}


def test_the_planted_effect_is_inside_the_range_and_the_change_is_shown():
    truth = pd.read_csv(FLEET / "ground_truth_actions.csv").set_index("action_id").planted_effect_pct
    a = _by_id()["ACT-01"]
    c = a["change_pct"]
    assert a["status"] == "reduction_shown"
    assert c["low"] <= truth["ACT-01"] <= c["high"] < 0


def test_a_change_with_no_effect_returns_cant_tell_yet_and_claims_nothing():
    a = _by_id()["ACT-02"]
    assert a["status"] == "cant_tell_yet" and "Can't tell yet" in a["headline"]
    assert a["change_pct"]["low"] < 0 < a["change_pct"]["high"]
    assert a["co2e_avoided_t"] is None and a["litres_avoided"] is None


def test_avoided_tonnes_are_litres_times_the_factor_with_a_matching_range():
    a = _by_id()["ACT-01"]
    litres, tonnes = a["litres_avoided"], a["co2e_avoided_t"]
    assert 0 < tonnes["low"] <= tonnes["value"] <= tonnes["high"]
    ratio = tonnes["value"] / litres["value"]
    assert ratio == pytest.approx(tonnes["high"] / litres["high"]) and 2.5 < ratio * 1000 < 3.5  # kg CO2e per litre, well to wheel


def test_the_proven_total_adds_only_changes_that_cleared_zero():
    result = action_impact()
    assert result["proven_co2e_t"]["value"] == pytest.approx(_by_id()["ACT-01"]["co2e_avoided_t"]["value"])
    only_null = action_impact("ACT-02")["proven_co2e_t"]
    assert only_null["value"] == 0 and only_null["label"] == "measured" and only_null["source_ids"]


def test_every_figure_has_a_label_sources_and_a_well_formed_range():
    for a in action_impact()["actions"]:
        for key in ("change_pct", "changed_change_pct", "others_change_pct", "litres_avoided", "co2e_avoided_t"):
            f = a[key]
            if f:
                assert f["label"] in {"measured", "allocated", "estimated"} and f["source_ids"] and f["how"].startswith("- ")
                assert f["low"] <= f["value"] <= f["high"]


def test_real_litres_are_untouched_and_the_overlay_covers_only_the_planted_change():
    assert round(ledger()[ledger().site_id == "S1"].litres.sum(), 1) == 10813.7
    overlay = action_overlay()
    assert set(overlay.action_id) == {"ACT-01"}
    real = jobs().set_index("job_id").litres
    assert (overlay.litres_with_action.values == pytest.approx(0.85 * real[overlay.job_id].values))


def test_each_change_is_judged_on_real_litres_for_the_other_machines():
    # ACT-02's comparison machines include ACT-01's changed tractors; their overlay must not leak in.
    log = mod.actions()
    d = mod._job_table(log.loc["ACT-02"], action_overlay())
    real = jobs().set_index("job_id").litres
    assert (d.litres.values == pytest.approx(real[d.job_id].values))


def test_too_few_jobs_says_too_early_and_gives_no_number(monkeypatch):
    monkeypatch.setattr(mod, "MIN_JOBS", 10_000)
    a = action_impact("ACT-01")["actions"][0]
    assert a["status"] == "not_enough_jobs" and a["change_pct"] is None and "Too early" in a["headline"]


def test_the_result_is_repeatable():
    assert action_impact() == action_impact()


def test_an_unknown_action_is_refused_with_the_known_ids():
    with pytest.raises(ValueError, match="ACT-01"):
        action_impact("ACT-99")


def test_the_action_names_machines_not_operators():
    text = str(action_impact())
    assert "OP-" not in text and "operator" not in text.lower()


def test_the_api_lists_every_action_and_filters_to_one():
    assert [a['action']['action_id'] for a in client.get('/api/fleet/actions').json()['actions']] == ['ACT-01', 'ACT-02']
    one = client.get('/api/fleet/actions', params={'action_id': 'ACT-02'}).json()
    assert len(one['actions']) == 1 and one['actions'][0]['status'] == 'cant_tell_yet'
    assert client.get('/api/fleet/actions', params={'action_id': 'ACT-99'}).status_code == 404


def test_the_answer_does_not_depend_on_the_order_the_source_returns_jobs(monkeypatch):
    from backend.fleet import data
    from backend.tools import action_impact as ai
    expected = ai.action_impact("ACT-01")
    shuffled = data.jobs().sample(frac=1, random_state=7).reset_index(drop=True)
    monkeypatch.setattr(ai, "jobs", lambda: shuffled)
    assert ai.action_impact("ACT-01") == expected
