from evals import proof_recovery


def test_the_planted_effect_is_recovered_and_the_null_stays_unclear():
    s = proof_recovery.score()
    assert s["changes"] == 2 and s["recovered"] == 2
    assert {r["action_id"]: r["status"] for r in s["rows"]} == {"ACT-01": "reduction_shown", "ACT-02": "cant_tell_yet"}


def test_a_missed_or_invented_effect_is_not_counted():
    saw = {"status": "reduction_shown", "change_pct": {"low": -36.0, "high": -6.0}}
    assert proof_recovery._recovered(-15.0, saw)
    assert not proof_recovery._recovered(-5.0, saw)  # planted effect outside the range
    assert not proof_recovery._recovered(0.0, saw)  # a saving shown where none was planted
    assert not proof_recovery._recovered(-15.0, {"status": "not_enough_jobs", "change_pct": None})
