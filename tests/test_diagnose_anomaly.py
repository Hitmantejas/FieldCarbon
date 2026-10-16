"""F5 anomaly diagnosis: stable finding ids, the hypothesis tests on small made-up data, the ordering rule, the Gemini
layer (stubbed: never a live call) and the endpoint."""
import json
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.agent import diagnosis_text
from backend.api import fleet as fleet_api
from backend.api.limits import AskLimiter
from backend.api.main import app
from backend.tools import diagnose_anomaly as dx
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.finding_id import DIAGNOSABLE_KINDS, finding_id
from backend.tools.reconcile_fuel import reconcile_fuel

api = TestClient(app)
FORBIDDEN = re.compile(r"\b(proven|confirmed|root cause)\b", re.IGNORECASE)


# --- step 1: finding ids --------------------------------------------------------------------------------------------

def test_finding_id_joins_the_non_empty_parts():
    assert finding_id("machine_over_dispense", "S1", "S1-T4", "2025-10") == "machine_over_dispense:S1:S1-T4:2025-10"
    assert finding_id("data_gap", "S1", "S1-T4", None, "") == "data_gap:S1:S1-T4"


def test_ids_are_the_same_on_every_run_and_unique():
    for tool in (reconcile_fuel, detect_anomalies):
        first, second = [f["id"] for f in tool()["findings"]], [f["id"] for f in tool()["findings"]]
        assert first == second and len(set(first)) == len(first)


def test_the_planted_problems_have_the_documented_ids():
    ids = {f["id"] for f in reconcile_fuel()["findings"]}
    assert {"machine_over_dispense:S1:S1-T4:2025-10", "stock_gap:S1:S1-D1:2026-01",
            "duplicate_delivery_note:S2:S2-D1:2025-09:DN-S2-0004"} <= ids


def test_findings_say_whether_they_can_be_diagnosed():
    findings = reconcile_fuel()["findings"] + detect_anomalies()["findings"]
    assert all(f["diagnosable"] == (f["kind"] in DIAGNOSABLE_KINDS) for f in findings)
    dup = next(f for f in findings if f["kind"] == "duplicate_delivery_note")
    assert dup["doc_no"] == "DN-S2-0004"
    assert all(f["job_id"] for f in findings if f["kind"] == "job_outlier")


def test_the_registry_covers_exactly_the_diagnosable_kinds():
    assert set(dx.REGISTRY) == set(DIAGNOSABLE_KINDS)
    for menu in dx.REGISTRY.values():
        assert len({h.id for h in menu}) == len(menu)
        assert all(h.title and h.description and not FORBIDDEN.search(h.title + h.description) for h in menu)


# --- step 2: hypothesis tests on small frames -------------------------------------------------------------------------

def _ctx(**kw) -> dx.Context:
    base = dict(
        dispenses=pd.DataFrame(columns=["depot_id", "machine_id", "ts", "litres", "month"]),
        burned={},
        night=pd.DataFrame(columns=["machine_id", "ts", "litres", "month"]),
        frozen=pd.DataFrame(columns=["machine_id", "month", "hours"]),
        depot_rows=[], deliveries=pd.DataFrame(columns=["depot_id", "ts", "supplier", "doc_no", "litres"]),
        note_counts=None, site_sources={"S9": "test_source"}, stock_tolerance_l=100.0)
    return dx.Context(**{**base, **kw})


def _fig(value, unit="L"):
    return {"value": value, "unit": unit, "label": "measured", "how": "test", "source_ids": ["fleet_synthetic"], "low": None, "high": None}


OVER = {"id": "machine_over_dispense:S9:M1:2025-10", "kind": "machine_over_dispense", "site_id": "S9", "machine_id": "M1",
        "month": "2025-10", "depot_id": None, "title": "M1 was given more", "litres": _fig(400.0)}


def _disp(rows):
    d = pd.DataFrame(rows, columns=["depot_id", "machine_id", "ts", "litres"])
    d["ts"] = pd.to_datetime(d.ts)
    return d.assign(month=d.ts.dt.to_period("M").astype(str))


def _night(n, each):
    return _disp([("D9", "M1", f"2025-10-{10 + k} 23:00", each) for k in range(n)])


def test_night_fuel_is_supported_with_three_dispenses_and_half_the_excess():
    r = dx.night_fuel_outside_shift(OVER, _ctx(night=_night(3, 70.0)))
    assert r["status"] == "supported" and r["evidence"]["value"] == 210.0 and r["explains_pct"] == pytest.approx(52.5)
    assert r["evidence"]["label"] == "measured" and r["evidence"]["source_ids"]


def test_night_fuel_is_not_supported_with_too_few_or_too_little():
    assert dx.night_fuel_outside_shift(OVER, _ctx(night=_night(2, 150.0)))["status"] == "not_supported"
    assert dx.night_fuel_outside_shift(OVER, _ctx(night=_night(4, 40.0)))["status"] == "not_supported"
    assert dx.night_fuel_outside_shift(OVER, _ctx())["evidence"]["value"] == 0


def test_night_share_is_capped_at_100():
    assert dx.night_fuel_outside_shift(OVER, _ctx(night=_night(5, 100.0)))["explains_pct"] == 100.0


def test_logging_error_is_supported_when_peers_are_short_by_the_same_amount():
    disp = _disp([("D9", "M1", "2025-10-01 08:00", 1400.0), ("D9", "M2", "2025-10-02 08:00", 600.0)])
    burned = {("M1", "2025-10"): 1000.0, ("M2", "2025-10"): 980.0}  # M2 burned 380 more than it was given: within 10% of 400
    r = dx.logging_or_meter_error(OVER, _ctx(dispenses=disp, burned=burned))
    assert r["status"] == "supported" and r["evidence"]["value"] == -380.0 and r["explains_pct"] == pytest.approx(95.0)


def test_logging_error_is_not_supported_when_peers_balance():
    disp = _disp([("D9", "M1", "2025-10-01 08:00", 1400.0), ("D9", "M2", "2025-10-02 08:00", 600.0)])
    r = dx.logging_or_meter_error(OVER, _ctx(dispenses=disp, burned={("M1", "2025-10"): 1000.0, ("M2", "2025-10"): 590.0}))
    assert r["status"] == "not_supported"


def test_logging_error_is_supported_by_repeated_identical_dispense_rows():
    disp = _disp([("D9", "M1", "2025-10-01 08:00", 200.0), ("D9", "M1", "2025-10-01 08:00", 200.0)])
    r = dx.logging_or_meter_error(OVER, _ctx(dispenses=disp, burned={("M1", "2025-10"): 0.0}))
    assert r["status"] == "supported" and r["evidence"]["value"] == 200.0 and r["explains_pct"] == pytest.approx(50.0)


def test_logging_error_cannot_be_tested_without_peers_on_the_depot():
    disp = _disp([("D9", "M1", "2025-10-01 08:00", 1400.0)])
    r = dx.logging_or_meter_error(OVER, _ctx(dispenses=disp, burned={("M1", "2025-10"): 1000.0}))
    assert r["status"] == "cannot_test" and r["would_settle"]


def test_recorder_is_supported_from_one_frozen_hour_and_has_no_share():
    frozen = pd.DataFrame([{"machine_id": "M1", "month": "2025-10", "hours": 1.2}, {"machine_id": "M1", "month": "2025-09", "hours": 50.0}])
    r = dx.recorder_understates_burn(OVER, _ctx(frozen=frozen))
    assert r["status"] == "supported" and r["evidence"]["value"] == 1.2 and r["evidence"]["unit"] == "h" and r["explains_pct"] is None
    assert r["evidence"]["source_ids"] == ["test_source"]
    frozen.loc[0, "hours"] = 0.5
    assert dx.recorder_understates_burn(OVER, _ctx(frozen=frozen))["status"] == "not_supported"


def test_untestable_causes_say_what_record_would_settle_them():
    for test, finding in ((dx.fuel_used_elsewhere, OVER), (dx.leak_or_theft, GAP), (dx.supplier_reissued_note, DUP)):
        r = test(finding, _ctx())
        assert r["status"] == "cannot_test" and r["evidence"] is None and r["would_settle"]


GAP = {"id": "stock_gap:S9:D9:2026-01", "kind": "stock_gap", "site_id": "S9", "machine_id": None, "depot_id": "D9",
       "month": "2026-01", "title": "Gap", "litres": _fig(900.0)}


def _rows(*gaps):
    ends = ["2025-11-30", "2025-12-31", "2026-01-31", "2026-02-28", "2026-03-31"]
    return [{"depot_id": "D9", "month_end": e, "gap_l": g} for e, g in zip(ends, gaps)]


def test_unlogged_withdrawal_is_supported_when_the_gap_stays():
    r = dx.unlogged_withdrawal(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0, 890.0, 960.0)))
    assert r["status"] == "supported" and r["evidence"]["value"] == 900.0
    assert r["explains_pct"] == pytest.approx(100 * 885 / 900, abs=0.05)


def test_unlogged_withdrawal_is_not_supported_when_the_gap_moves_and_untestable_without_later_readings():
    assert dx.unlogged_withdrawal(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0, 890.0, 600.0)))["status"] == "not_supported"
    assert dx.unlogged_withdrawal(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0)))["status"] == "cannot_test"


def test_dip_error_is_supported_only_when_the_next_reading_goes_back():
    back = dx.dip_reading_error(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0, 40.0)))
    assert back["status"] == "supported" and back["evidence"]["value"] == 40.0
    assert dx.dip_reading_error(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0, 890.0)))["status"] == "not_supported"
    assert dx.dip_reading_error(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0)))["status"] == "cannot_test"


def _deliveries(rows):
    d = pd.DataFrame(rows, columns=["depot_id", "ts", "supplier", "doc_no", "litres"])
    return d.assign(ts=pd.to_datetime(d.ts))


def test_delivery_without_a_note_matching_the_step_is_supported():
    dl = _deliveries([("D9", "2026-01-10 06:00", "Supplier A", "DN-1", 950.0), ("D9", "2026-01-12 06:00", "Supplier A", "DN-2", 2400.0)])
    counts = {dx.note_key("Supplier A", "DN-2"): 1}
    r = dx.delivery_not_received_or_duplicated(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0, 890.0), deliveries=dl, note_counts=counts))
    assert r["status"] == "supported" and r["evidence"]["value"] == 950.0


def test_a_delivery_with_its_note_or_far_from_the_step_is_not_supported():
    dl = _deliveries([("D9", "2026-01-10 06:00", "Supplier A", "DN-1", 950.0), ("D9", "2026-01-12 06:00", "Supplier A", "DN-2", 2400.0)])
    counts = {dx.note_key("Supplier A", "DN-1"): 1}
    r = dx.delivery_not_received_or_duplicated(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0, 890.0), deliveries=dl, note_counts=counts))
    assert r["status"] == "not_supported" and r["evidence"]["value"] == 2400.0


def test_a_duplicate_outside_the_window_does_not_count():
    dl = _deliveries([("D9", "2025-11-10 06:00", "Supplier A", "DN-1", 900.0), ("D9", "2025-11-10 06:00", "Supplier A", "DN-1", 900.0)])
    r = dx.delivery_not_received_or_duplicated(GAP, _ctx(depot_rows=_rows(0.0, 5.0, 905.0, 890.0), deliveries=dl, note_counts={}))
    assert r["status"] == "not_supported"


DUP = {"id": "duplicate_delivery_note:S9:D9:2025-09:DN-7", "kind": "duplicate_delivery_note", "site_id": "S9", "machine_id": None,
       "depot_id": "D9", "month": "2025-09", "doc_no": "DN-7", "title": "Twice", "litres": _fig(900.0)}


def test_same_note_twice_is_supported_by_two_identical_log_rows():
    dl = _deliveries([("D9", "2025-09-08 06:00", "Supplier B", "DN-7", 900.0)] * 2)
    r = dx.same_note_entered_twice(DUP, _ctx(deliveries=dl))
    assert r["status"] == "supported" and r["evidence"]["value"] == 900.0 and r["explains_pct"] == 100.0
    one = dx.same_note_entered_twice(DUP, _ctx(deliveries=dl.iloc[:1]))
    assert one["status"] == "not_supported"


def test_two_real_deliveries_counts_paper_notes():
    dl = _deliveries([("D9", "2025-09-08 06:00", "Supplier B", "DN-7", 900.0)] * 2)
    key = dx.note_key("Supplier B", "DN-7")
    one = dx.two_real_deliveries(DUP, _ctx(deliveries=dl, note_counts={key: 1}))
    assert one["status"] == "not_supported" and one["evidence"]["value"] == 1 and one["evidence"]["unit"] == "notes"
    assert dx.two_real_deliveries(DUP, _ctx(deliveries=dl, note_counts={key: 2}))["status"] == "supported"
    assert dx.two_real_deliveries(DUP, _ctx(deliveries=dl, note_counts={}))["status"] == "cannot_test"
    assert dx.two_real_deliveries(DUP, _ctx(deliveries=dl, note_counts=None))["status"] == "cannot_test"


# --- ordering ---------------------------------------------------------------------------------------------------------

def test_order_is_supported_then_cannot_test_then_not_supported_with_ties_by_share():
    rows = [{"id": "a", "status": "not_supported", "explains_pct": 90.0}, {"id": "b", "status": "cannot_test", "explains_pct": None},
            {"id": "c", "status": "supported", "explains_pct": None}, {"id": "d", "status": "supported", "explains_pct": 40.0},
            {"id": "e", "status": "supported", "explains_pct": 80.0}]
    assert [r["id"] for r in dx.order(rows)] == ["e", "d", "c", "b", "a"]


# --- the planted problems on the real data ---------------------------------------------------------------------------

@pytest.mark.parametrize("fid, top", [("machine_over_dispense:S1:S1-T4:2025-10", "night_fuel_outside_shift"),
                                      ("stock_gap:S1:S1-D1:2026-01", "unlogged_withdrawal"),
                                      ("duplicate_delivery_note:S2:S2-D1:2025-09:DN-S2-0004", "same_note_entered_twice")])
def test_each_planted_problem_puts_its_cause_first(fid, top):
    d = dx.diagnose_anomaly(fid)
    assert d["hypotheses"][0]["id"] == top and d["hypotheses"][0]["status"] == "supported"
    assert d["disclaimer"] == "Gemini suggests; code tests; a person decides."
    assert all(h["suggested_by"] == "code" and h["status_text"] == dx.STATUS_TEXT[h["status"]] for h in d["hypotheses"])
    for h in d["hypotheses"]:
        assert h["evidence"] is None or (h["evidence"]["label"] and h["evidence"]["source_ids"] and h["evidence"]["how"])
    assert not FORBIDDEN.search(json.dumps(d))


def test_the_a1_overlap_with_the_frozen_recorder_is_shown_not_hidden():
    d = dx.diagnose_anomaly("machine_over_dispense:S1:S1-T4:2025-10")
    status = {h["id"]: h["status"] for h in d["hypotheses"]}
    assert status["recorder_understates_burn"] == "supported" and status["fuel_used_elsewhere"] == "cannot_test"


def test_an_unknown_or_undiagnosable_id_is_a_clean_error():
    with pytest.raises(ValueError, match="unknown finding"):
        dx.diagnose_anomaly("machine_over_dispense:S1:S1-T9:2025-10")
    with pytest.raises(ValueError, match="no causes to test"):  # every kind found today is diagnosable; a night dispense is not
        dx.diagnose({"id": "night_dispense:S1:S1-T4:2025-10", "kind": "night_dispense", "title": "t"}, _ctx())


# --- step 3: the Gemini layer (stubbed) -------------------------------------------------------------------------------

A1 = "machine_over_dispense:S1:S1-T4:2025-10"


def _summary_for(facts: dict) -> str:
    top = facts["tests"][0]
    return f"The data supports the idea that fuel was taken at night: {top['evidence']['value']:,} litres (measured) at night."


def stub(reply, prompts=None, fail=False):
    """A Gemini stand-in: records each prompt and returns `reply(facts_from_prompt)` as JSON."""
    def generate(prompt, schema):
        if prompts is not None:
            prompts.append((prompt, schema))
        if fail:
            raise RuntimeError("model down")
        facts = {"tests": json.loads(prompt.split("TESTS: ", 1)[1].split("\n", 1)[0])}
        return {"text": json.dumps(reply(facts)), "usage": {"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 0}}
    return generate


def _good(facts):
    return {"why": [{"id": t["id"], "text": "The code test result explains this."} for t in facts["tests"]],
            "extra_ideas": [], "summary": _summary_for(facts)}


def test_gemini_adds_why_lines_and_an_audited_summary_but_never_a_status_or_order():
    d = dx.diagnose_anomaly(A1)
    out = diagnosis_text.explain(d, stub(_good))
    assert [h["id"] for h in out["hypotheses"]] == [h["id"] for h in d["hypotheses"]]
    assert [h["status"] for h in out["hypotheses"]] == [h["status"] for h in d["hypotheses"]]
    assert all(h["why"] for h in out["hypotheses"])
    assert out["summary"]["narrative_source"] == "gemini" and out["summary"]["audited"]


def test_a_reordering_and_a_status_from_gemini_are_ignored():
    def sneaky(facts):
        r = _good(facts)
        r["why"] = list(reversed(r["why"]))
        r["why"][0]["status"] = "supported"
        return r
    d = dx.diagnose_anomaly(A1)
    out = diagnosis_text.explain(d, stub(sneaky))
    assert [(h["id"], h["status"]) for h in out["hypotheses"]] == [(h["id"], h["status"]) for h in d["hypotheses"]]


def test_an_id_not_on_the_menu_is_rejected_and_the_schema_only_allows_menu_ids():
    prompts = []
    def invents(facts):
        r = _good(facts)
        r["why"].append({"id": "aliens", "text": "Aliens took it."})
        return r
    out = diagnosis_text.explain(dx.diagnose_anomaly(A1), stub(invents, prompts))
    assert "aliens" not in {h["id"] for h in out["hypotheses"]} and out["rejected"] == ["aliens"]
    enum = prompts[0][1]["properties"]["why"]["items"]["properties"]["id"]["enum"]
    assert set(enum) == {h.id for h in dx.REGISTRY["machine_over_dispense"]}


def test_extra_ideas_are_capped_at_two_untested_and_tagged():
    def many(facts):
        r = _good(facts)
        r["extra_ideas"] = [{"title": f"Idea {k}", "reason": "Worth asking the site."} for k in "abc"]
        return r
    out = diagnosis_text.explain(dx.diagnose_anomaly(A1), stub(many))
    extra = [h for h in out["hypotheses"] if h["suggested_by"] == "gemini"]
    assert len(extra) == 2 and all(h["status"] == "cannot_test" and h["tag"] == "Suggested by Gemini" for h in extra)
    statuses = [h["status"] for h in out["hypotheses"]]
    assert statuses == sorted(statuses, key=["supported", "cannot_test", "not_supported"].index)


def test_a_why_line_with_an_invented_number_or_a_forbidden_word_is_dropped():
    def bad(facts):
        r = _good(facts)
        r["why"][0]["text"] = "It explains 77 litres (measured)."
        r["why"][1]["text"] = "This is the proven cause."
        return r
    d = dx.diagnose_anomaly(A1)
    out = diagnosis_text.explain(d, stub(bad))
    assert out["hypotheses"][0]["why"] is None and out["hypotheses"][1]["why"] is None
    assert out["hypotheses"][2]["why"]


def test_a_summary_that_fails_the_audit_twice_falls_back_to_the_template():
    def wrong(facts):
        return {**_good(facts), "summary": "The proven cause is night fuel: 12,345 litres."}
    out = diagnosis_text.explain(dx.diagnose_anomaly(A1), stub(wrong))
    s = out["summary"]
    assert s["narrative_source"] == "template" and not s["audited"] and s["attempts"] == 2
    assert "Fuel was taken at night" in s["text"] and not FORBIDDEN.search(s["text"])


def test_a_summary_with_a_made_up_bracket_label_is_sent_back_once():
    """A live run wrote "explains 100 [explains_pct]"; only measured, allocated or estimated may go in brackets."""
    replies = iter(["Same note entered twice: 900 L [measured], explaining 100 [explains_pct].", None])
    def odd_then_good(facts):
        text = next(replies)
        return {**_good(facts), "summary": text or _summary_for(facts)}
    out = diagnosis_text.explain(dx.diagnose_anomaly(A1), stub(odd_then_good))
    assert out["summary"]["attempts"] == 2 and out["summary"]["audited"]
    assert diagnosis_text.forbidden_words("900 L [measured] and 1 note [estimated].") is None
    assert "explains_pct" in diagnosis_text.forbidden_words("explains 100 [explains_pct]")


@pytest.mark.parametrize("fid", ["machine_over_dispense:S1:S1-T4:2025-10", "stock_gap:S1:S1-D1:2026-01",
                                 "duplicate_delivery_note:S2:S2-D1:2025-09:DN-S2-0004"])
def test_every_evidence_figure_says_what_it_measures_in_words_without_numbers(fid):
    """Live A1 called frozen-recorder hours 'hours of operation'; Gemini now reads what each figure counts."""
    d = dx.diagnose_anomaly(fid)
    tests = diagnosis_text.gemini_facts(d)["tests"]
    for h, t in zip(d["hypotheses"], tests):
        assert (h["evidence"] is None) == (h["evidence_measures"] is None)
        assert t["measures"] == h["evidence_measures"]
        assert h["evidence_measures"] is None or not re.search(r"\d", h["evidence_measures"])


def test_a_model_failure_keeps_the_tests_with_no_why_lines():
    d = dx.diagnose_anomaly(A1)
    out = diagnosis_text.explain(d, stub(_good, fail=True))
    assert all(h["why"] is None for h in out["hypotheses"]) and out["summary"]["error"]
    assert [h["status"] for h in out["hypotheses"]] == [h["status"] for h in d["hypotheses"]]


@pytest.mark.parametrize("fid", ["machine_over_dispense:S1:S1-T4:2025-10", "stock_gap:S1:S1-D1:2026-01",
                                 "duplicate_delivery_note:S2:S2-D1:2025-09:DN-S2-0004"])
def test_no_operator_id_reaches_the_prompt(fid):
    prompts = []
    diagnosis_text.explain(dx.diagnose_anomaly(fid), stub(_good, prompts))
    assert prompts and not any(re.search(r"OP-\d+|operator", p, re.IGNORECASE) for p, _ in prompts)


def test_the_prompt_carries_the_rules():
    prompts = []
    diagnosis_text.explain(dx.diagnose_anomaly(A1), stub(_good, prompts))
    p = prompts[0][0]
    assert "You do not decide results" in p and "up to 2 extra ideas" in p and '"proven"' in p and "MENU:" in p


# --- step 4: the endpoint ---------------------------------------------------------------------------------------------

@pytest.fixture
def fresh_api(monkeypatch):
    calls = []
    def generate(prompt, schema):
        calls.append(prompt)
        return stub(_good)(prompt, schema)
    monkeypatch.setattr(fleet_api, "gen_limiter", AskLimiter(per_minute=2, per_day=10, clock=lambda: 1_790_000_000.0,
                                                            messages=fleet_api.GEN_MESSAGES))
    monkeypatch.setattr(fleet_api, "_diagnosis_cache", {})
    monkeypatch.setattr(fleet_api, "diagnosis_generate", generate)
    return calls


def test_the_endpoint_without_narration_makes_no_model_call(fresh_api):
    for _ in range(4):
        r = api.get("/api/fleet/diagnosis", params={"finding_id": A1})
        assert r.status_code == 200
    body = r.json()
    assert body["hypotheses"][0]["id"] == "night_fuel_outside_shift" and "summary" not in body and fresh_api == []


def test_the_endpoint_with_narration_is_cached(fresh_api):
    for _ in range(3):
        r = api.get("/api/fleet/diagnosis", params={"finding_id": A1, "narrate": "true"})
        assert r.status_code == 200
    assert r.json()["summary"]["audited"] and len(fresh_api) == 1


def test_unknown_id_is_404_and_missing_id_is_422(fresh_api):
    assert api.get("/api/fleet/diagnosis", params={"finding_id": "nope"}).status_code == 404
    assert api.get("/api/fleet/diagnosis", params={"finding_id": "nope", "narrate": "true"}).status_code == 404
    assert api.get("/api/fleet/diagnosis").status_code == 422
    assert api.get("/api/fleet/diagnosis", params={"finding_id": "x" * 200}).status_code == 422
    assert fresh_api == []


def test_the_shared_limit_is_429(fresh_api):
    ids = ["machine_over_dispense:S1:S1-T4:2025-10", "stock_gap:S1:S1-D1:2026-01",
           "duplicate_delivery_note:S2:S2-D1:2025-09:DN-S2-0004"]
    codes = [api.get("/api/fleet/diagnosis", params={"finding_id": i, "narrate": "true"}).status_code for i in ids]
    assert codes == [200, 200, 429]


def test_a_model_failure_is_not_cached(fresh_api, monkeypatch):
    monkeypatch.setattr(fleet_api, "diagnosis_generate", stub(_good, fail=True))
    r = api.get("/api/fleet/diagnosis", params={"finding_id": A1, "narrate": "true"})
    assert r.status_code == 200 and r.json()["summary"]["narrative_source"] == "template"
    assert fleet_api._diagnosis_cache == {}


def test_the_diagnosis_eval_scores_all_three_planted_problems():
    from evals.fleet_diagnosis import score
    r = score(write=False)
    assert r["planted"] == 3 and r["correct"] == 3, r["results"]


# --- the agent tool ---------------------------------------------------------------------------------------------------

def test_the_agent_tool_returns_json_and_errors_as_data():
    from backend.agent import tools
    out = tools.diagnose_anomaly(A1)
    json.dumps(out)
    assert out["hypotheses"][0]["id"] == "night_fuel_outside_shift" and "summary" not in out
    assert "unknown finding id" in tools.diagnose_anomaly("nope")["error"]
    assert tools.diagnose_anomaly in tools.AGENT_TOOLS
