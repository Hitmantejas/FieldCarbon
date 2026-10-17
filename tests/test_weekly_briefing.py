"""F6 weekly briefing: three items chosen by fixed rules, an intro Gemini writes and code checks, and the endpoint."""
import json
import re
import sys
import types

import pytest
from fastapi.testclient import TestClient

from backend.agent import briefing_text
from backend.agent.narrate import _problems
from backend.api import fleet as fleet_api
from backend.api.limits import AskLimiter
from backend.api.main import app
from backend.tools import weekly_briefing as wb
from backend.tools.contracts import LABELS

api = TestClient(app)


def _fig(value, unit="L", label="measured", low=None, high=None):
    return {"value": value, "unit": unit, "label": label, "how": "- worked out", "source_ids": ["fleet_synthetic"],
            "low": low, "high": high}


def _cand(cid, family, severity, value, kind="stock_gap", **fig):
    return {"id": cid, "family": family, "kind": kind, "severity": severity, "title": f"Title {cid}",
            "figure": _fig(value, **fig), "link": "#/control"}


# --- choosing ---------------------------------------------------------------------------------------------------------

def test_order_is_severity_then_size_then_id():
    c = [_cand("b", "control", "medium", 900), _cand("a", "data", "high", 10), _cand("c", "benchmark", "high", 10),
         _cand("d", "opportunity", "high", 50)]
    assert [x["id"] for x in wb.ordered(c)] == ["d", "a", "c", "b"]


def test_a_range_is_sized_by_its_low_end():
    c = [_cand("r", "opportunity", "medium", None, low=120, high=5000), _cand("v", "control", "medium", 200)]
    assert [x["id"] for x in wb.ordered(c)] == ["v", "r"]


def test_at_most_one_item_per_family_while_other_families_are_left():
    c = [_cand("c1", "control", "high", 900), _cand("c2", "control", "high", 800), _cand("d1", "data", "high", 30),
         _cand("o1", "opportunity", "medium", 300)]
    assert [x["id"] for x in wb.choose(c)] == ["c1", "d1", "o1"]


def test_fewer_than_three_families_fill_from_the_ordered_list():
    c = [_cand("c1", "control", "high", 900), _cand("c2", "control", "high", 800), _cand("c3", "control", "low", 5),
         _cand("d1", "data", "low", 1)]
    assert [x["id"] for x in wb.choose(c)] == ["c1", "c2", "d1"]


def test_fewer_than_three_candidates_give_fewer_items_and_none_give_none():
    assert [x["id"] for x in wb.choose([_cand("c1", "control", "high", 9)])] == ["c1"]
    assert wb.choose([]) == []


def test_choosing_is_deterministic_whatever_the_input_order():
    c = [_cand(str(i), f, s, v) for i, (f, s, v) in enumerate(
        [("control", "high", 5), ("data", "high", 5), ("benchmark", "low", 7), ("opportunity", "medium", 5), ("control", "high", 5)])]
    first = [x["id"] for x in wb.choose(c)]
    assert all([x["id"] for x in wb.choose(list(reversed(c)))] == first for _ in range(3))


# --- candidates from the real tools -----------------------------------------------------------------------------------

def test_today_the_three_items_are_the_duplicate_note_the_frozen_recorder_and_the_top_idea():
    items = wb.weekly_briefing()["items"]
    assert [i["id"] for i in items] == ["duplicate_delivery_note:S2:S2-D1:2025-09:DN-S2-0004", "data_gap:S1:S1-T4",
                                        "opportunity:shift_up_throttle_down"]
    assert [i["family"] for i in items] == ["control", "data", "opportunity"]


def test_a_note_already_found_by_reconciliation_is_not_a_second_candidate():
    ids = [c["id"] for c in wb.candidates()]
    assert "note:entered_twice:DN-S2-0004" not in ids
    assert "note:price_differs:DN-S1-0004" in ids


def test_every_family_has_candidates_and_benchmark_groups_need_a_machine_above_peers():
    cands = wb.candidates()
    assert {c["family"] for c in cands} == {"control", "data", "benchmark", "opportunity"}
    groups = [c for c in cands if c["kind"] == "benchmark"]
    assert groups and all(c["figure"]["low"] is not None for c in groups)


def test_the_frozen_hours_total_is_a_candidate_only_without_a_data_gap_finding(monkeypatch):
    assert not [c for c in wb.candidates() if c["kind"] == "data_quality"]
    monkeypatch.setattr(wb, "detect_anomalies", lambda: {"findings": []})
    dq = [c for c in wb.candidates() if c["kind"] == "data_quality"]
    assert len(dq) == 1 and dq[0]["figure"]["unit"] == "h" and dq[0]["family"] == "data"


def test_only_feasible_ideas_are_candidates_and_only_the_top_one():
    ideas = [c for c in wb.candidates() if c["family"] == "opportunity"]
    assert len(ideas) == 1 and ideas[0]["id"] == "opportunity:shift_up_throttle_down"


def test_missing_optional_tools_are_skipped_and_a_present_one_adds_candidates(monkeypatch):
    monkeypatch.setattr(wb, "OPTIONAL_TOOLS", ("backend.tools.no_such_tool",))
    assert {c["family"] for c in wb.candidates()} == {"control", "data", "benchmark", "opportunity"}
    ledger = types.SimpleNamespace(briefing_candidates=lambda: [_cand("ledger:x", "ledger", "high", 5000, kind="ledger")])
    monkeypatch.setitem(sys.modules, "fake_ledger", ledger)
    monkeypatch.setattr(wb, "OPTIONAL_TOOLS", ("backend.tools.no_such_tool", "fake_ledger"))
    assert "ledger:x" in [c["id"] for c in wb.candidates()]


def test_every_item_has_a_labelled_sourced_figure_and_the_fixed_texts():
    b = wb.weekly_briefing()
    for i in b["items"]:
        f = i["figure"]
        assert f["label"] in LABELS and f["source_ids"] and f["how"]
        assert f["value"] is not None or (f["low"] is not None and f["high"] is not None)
        for key in ("title", "why_it_matters", "next_step", "would_improve", "link"):
            assert i[key], key
        assert i["severity"] in ("high", "medium", "low") and i["link"].startswith("#/")
    assert b["heading"] == "Week summary" and "May 2025 to April 2026" in b["period"]
    assert "this week" not in json.dumps(b).lower()


def test_the_would_improve_texts_follow_the_plan():
    by_kind = {i["kind"]: i["would_improve"] for i in wb.weekly_briefing()["items"]}
    assert by_kind["duplicate_delivery_note"] == "The supplier's invoice for that note number."
    assert by_kind["data_gap"] == "A fresh export from the machine that stopped reporting."
    assert "tyre pressure" in by_kind["opportunity"]
    assert wb.WOULD_IMPROVE["stock_gap"].startswith("A tank dip reading")


def test_every_candidate_kind_has_its_texts():
    for c in wb.candidates():
        assert wb.item(c)["next_step"] and wb.item(c)["would_improve"] and wb.item(c)["why_it_matters"]


def test_no_operator_id_or_verified_in_the_briefing():
    text = json.dumps(wb.weekly_briefing())
    assert not re.search(r"OP-\d+", text) and "verified" not in text.lower()


# --- the intro --------------------------------------------------------------------------------------------------------

def _write(*texts):
    asked = []

    def write(facts, rewrite):
        asked.append(rewrite)
        return {"text": texts[len(asked) - 1], "usage": {"input_tokens": 100, "output_tokens": 50, "thinking_tokens": 0}}
    write.asked = asked
    return write


def _good(facts):
    first = facts["items"][0]
    return f"This summary has three items. The first is {first['topic']}, about {first['litres']['value']:,} litres ({first['litres']['label']})."


def test_intro_facts_are_rounded_have_unit_keys_and_no_how_or_sources():
    facts = briefing_text.gemini_facts(wb.weekly_briefing())
    assert len(facts["items"]) == 3
    assert facts["items"][0]["litres"] == {"value": 900, "label": "measured"}
    assert facts["items"][1]["hours"]["label"] == "measured"
    assert set(facts["items"][2]["litres_per_year"]) == {"low", "high", "label"}
    assert "how" not in json.dumps(facts) and "source_ids" not in json.dumps(facts)
    assert not re.search(r"\d", " ".join(i["topic"] for i in facts["items"]))  # topics carry no numbers to misquote


def test_a_clean_intro_passes_and_an_invented_number_is_rewritten_once():
    b = wb.weekly_briefing()
    facts = briefing_text.gemini_facts(b)
    r = briefing_text.narrate_briefing(b, "en", write=_write(_good(facts)))
    assert r["narrative_source"] == "gemini" and r["audited"] and r["attempts"] == 1
    write = _write(_good(facts).replace("900", "950"), _good(facts))
    r = briefing_text.narrate_briefing(b, "en", write=write)
    assert r["audited"] and r["attempts"] == 2 and "950" in write.asked[1]


def test_a_long_intro_is_rewritten_then_falls_back():
    b = wb.weekly_briefing()
    long = "Word " * 70 + "end."
    r = briefing_text.narrate_briefing(b, "en", write=_write(long, long))
    assert r["narrative_source"] == "template" and r["audited"] is False


@pytest.mark.parametrize("language", briefing_text.LANGUAGES)
def test_the_standard_intro_has_no_numbers_and_passes_its_own_checks(language):
    facts = briefing_text.gemini_facts(wb.weekly_briefing())
    text, written_in = briefing_text.template(facts, language)
    assert written_in == language and not re.search(r"\d", text)
    assert _problems(text, facts)[0] is None


def test_the_prompt_carries_the_appendix_rules():
    p = briefing_text.build_prompt({"items": []}, "de")
    for rule in ("2 to 3 sentence introduction", "at most 60 words", "by topic only", "copied exactly",
                 "label in English in brackets", "No advice, no predictions", "Write in German", 'ITEMS: {"items":[]}'):
        assert rule in p


# --- endpoint ---------------------------------------------------------------------------------------------------------

@pytest.fixture
def fresh_api(monkeypatch):
    calls = []

    def write_for(language):
        def write(facts, rewrite):
            calls.append(language)
            return {"text": _good(facts), "usage": {"input_tokens": 100, "output_tokens": 50, "thinking_tokens": 0}}
        return write
    monkeypatch.setattr(fleet_api, "gen_limiter", AskLimiter(per_minute=2, per_day=10, clock=lambda: 1_790_000_000.0,
                                                            messages=fleet_api.GEN_MESSAGES))
    monkeypatch.setattr(fleet_api, "_briefing_cache", {})
    monkeypatch.setattr(fleet_api, "briefing_writer", write_for)
    return calls


def test_the_endpoint_gives_items_and_the_standard_intro_without_the_model(fresh_api):
    for _ in range(4):
        r = api.get("/api/fleet/briefing")
        assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3 and body["intro"]["narrative_source"] == "template" and body["language"] == "en"
    assert fresh_api == []


def test_narrate_true_calls_the_model_once_per_language_then_uses_the_cache(fresh_api):
    for language in ("en", "en", "de", "de"):
        body = api.get("/api/fleet/briefing", params={"language": language, "narrate": "true"}).json()
        assert body["intro"]["narrative_source"] == "gemini"
    assert fresh_api == ["en", "de"]


def test_unsupported_language_is_422(fresh_api):
    assert api.get("/api/fleet/briefing", params={"language": "fr"}).status_code == 422


def test_the_limit_is_429(fresh_api):
    for language in ("en", "de"):
        assert api.get("/api/fleet/briefing", params={"language": language, "narrate": "true"}).status_code == 200
    r = api.get("/api/fleet/briefing", params={"language": "es", "narrate": "true"})
    assert r.status_code == 429 and r.headers["Retry-After"]


def test_a_model_outage_shows_the_standard_intro_and_is_not_cached(fresh_api, monkeypatch):
    def broken(language):
        def write(facts, rewrite):
            raise RuntimeError("503 from Vertex AI")
        return write
    monkeypatch.setattr(fleet_api, "briefing_writer", broken)
    body = api.get("/api/fleet/briefing", params={"narrate": "true"}).json()
    assert body["intro"]["narrative_source"] == "template" and "could not be reached" in body["intro"]["error"]
    assert fleet_api._briefing_cache == {}


def test_a_failure_with_no_fallback_is_502(fresh_api, monkeypatch):
    def fails(*a, **k):
        raise RuntimeError("template broke")
    monkeypatch.setattr(fleet_api.briefing_text, "narrate_briefing", fails)
    r = api.get("/api/fleet/briefing", params={"narrate": "true"})
    assert r.status_code == 502 and "template" not in r.json()["detail"]
