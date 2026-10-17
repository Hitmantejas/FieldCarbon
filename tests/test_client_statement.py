"""F4 client carbon statement: the facts (no model), the narration with stub writers, and the endpoint."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.agent import statement_text
from backend.agent.coverage import unlabelled_sentences
from backend.agent.narrate import _problems, clean_facts
from backend.api import fleet as fleet_api
from backend.api.limits import AskLimiter
from backend.api.main import app
from backend.fleet import data
from backend.tools.client_statement import client_statement
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_report import fleet_report
from backend.tools.contracts import LABELS

api = TestClient(app)
CLIENTS = ["C01", "C03", "C09", "C16"]


@pytest.mark.parametrize("cid", CLIENTS)
def test_totals_equal_the_client_figures_everywhere_else(cid):
    s = client_statement(cid)
    row = emissions_per_client(cid)["rows"][0]
    report = fleet_report(cid)["totals"]
    for key in ("litres", "co2e_kg", "cost_gbp"):
        assert s["totals"][key]["value"] == row[key]["value"] == report[key]["value"]
        assert s["totals"][key]["label"] == row[key]["label"]
    assert s["jobs"] == row["jobs"] and s["client_name"] == data.client_name(cid)


@pytest.mark.parametrize("cid", CLIENTS)
def test_per_hectare_is_allocated_or_weaker_and_is_co2e_over_area(cid):
    s = client_statement(cid)
    assert s["area_ha"]["label"] == "allocated"
    assert LABELS.index(s["co2e_per_ha"]["label"]) >= LABELS.index("allocated")
    jobs = data.jobs()[lambda d: d.client_id == cid]
    with_area = jobs[jobs.area_ha.notna()]
    factor = s["totals"]["co2e_kg"]["value"] / s["totals"]["litres"]["value"]
    assert s["area_ha"]["value"] == pytest.approx(with_area.area_ha.sum(), rel=1e-9)
    assert s["co2e_per_ha"]["value"] == pytest.approx(with_area.litres.sum() * factor / s["area_ha"]["value"], rel=1e-9)
    assert s["co2e_per_job"]["value"] == pytest.approx(s["totals"]["co2e_kg"]["value"] / s["jobs"], rel=1e-9)
    assert s["co2e_per_job"]["label"] == s["totals"]["co2e_kg"]["label"]


def test_a_client_with_jobs_missing_an_area_says_they_are_left_out_of_per_hectare():
    s = client_statement("C03")  # 7 of its jobs have no recorded area
    assert s["jobs_without_area"] == 7 and "7 jobs" in s["co2e_per_ha"]["how"]
    assert client_statement("C09")["jobs_without_area"] == 0


@pytest.mark.parametrize("cid", CLIENTS)
def test_by_operation_has_at_most_five_rows_whose_shares_make_100(cid):
    ops = client_statement(cid)["by_operation"]
    assert 1 <= len(ops) <= 5
    assert sum(o["share_pct"] for o in ops) == pytest.approx(100, abs=0.01)
    assert sum(o["litres"]["value"] for o in ops) == pytest.approx(client_statement(cid)["totals"]["litres"]["value"], rel=1e-9)


def test_more_than_five_operations_end_in_one_other_work_row():
    ops = client_statement("C09")["by_operation"]
    assert len(data.jobs()[lambda d: d.client_id == "C09"].operation_code.unique()) > 5
    assert ops[-1]["operation"] == "Other work" and len(ops) == 5


@pytest.mark.parametrize("cid", CLIENTS)
def test_every_figure_has_a_label_and_a_source(cid):
    s = client_statement(cid)
    figs = [s["totals"][k] for k in ("litres", "co2e_kg", "cost_gbp")] + [s["area_ha"], s["co2e_per_ha"], s["co2e_per_job"]]
    figs += [o[k] for o in s["by_operation"] for k in ("litres", "co2e_kg")]
    assert all(f["label"] in LABELS and f["source_ids"] and f["how"] for f in figs)


def test_period_and_limits():
    s = client_statement("C03")
    months = data.ledger()[lambda d: d.client_id == "C03"].month
    assert s["period"] == {"from": months.min(), "to": months.max()}
    text = " ".join(s["limits"])
    assert "overhead" in text and "synthetic" in text and "allocated" in text


def test_an_unknown_client_is_a_clean_error():
    with pytest.raises(ValueError, match="unknown client"):
        client_statement("C99")


def test_no_operator_id_anywhere_in_the_statement_or_the_facts_for_gemini():
    for cid in CLIENTS:
        s = client_statement(cid)
        assert not re.search(r"OP-\d+", json.dumps(s))
        assert not re.search(r"OP-\d+", json.dumps(statement_text.gemini_facts(s)))


# --- narration -------------------------------------------------------------------------------------------------------

def _write(*texts):
    asked = []

    def write(facts, rewrite):
        asked.append(rewrite)
        t = texts[len(asked) - 1]
        return {"text": t, "usage": {"input_tokens": 100, "output_tokens": 50, "thinking_tokens": 0}}
    write.asked = asked
    return write


def _good(facts):
    return (f"Work on your fields used {facts['litres']['value']:,} litres of diesel ({facts['litres']['label']}). "
            f"That is {facts['co2e_kg']['value']:,} kg of CO2e ({facts['co2e_kg']['label']}).")


def test_gemini_facts_are_rounded_cleaned_and_use_keys_the_auditor_reads():
    f = statement_text.gemini_facts(client_statement("C03"))
    assert set(f) >= {"client_name", "period", "litres", "co2e_kg", "cost_gbp", "area_ha", "co2e_kg_per_ha", "co2e_kg_per_job", "jobs",
                      "by_operation"}
    assert f == clean_facts(f)
    assert isinstance(f["litres"]["value"], int) and f["litres"]["label"] in LABELS
    assert "co2e_per_ha" not in f  # read as hectares by the auditor


def test_clean_narration_passes_and_an_invented_number_is_rewritten_once():
    s = client_statement("C03")
    facts = statement_text.gemini_facts(s)
    r = statement_text.narrate_statement(s, "en", write=_write(_good(facts)))
    assert r["narrative_source"] == "gemini" and r["audited"] and r["attempts"] == 1
    write = _write(_good(facts).replace(f"{facts['co2e_kg']['value']:,}", "99,999"), _good(facts))
    r = statement_text.narrate_statement(s, "en", write=write)
    assert r["audited"] and r["attempts"] == 2 and "99,999" in write.asked[1]


def test_still_bad_text_gives_the_standard_wording():
    s = client_statement("C03")
    r = statement_text.narrate_statement(s, "de", write=_write("Sie haben 99,999 Liter verbraucht (measured).", "Immer noch 99,999 Liter (measured)."))
    assert r["narrative_source"] == "template" and r["audited"] is False and r["narrative_language"] == "de"
    assert "99,999" not in r["text"]


def test_a_german_decimal_comma_and_a_dropped_label_both_fail():
    s = client_statement("C03")
    facts = statement_text.gemini_facts(s)
    per_ha = f"{facts['co2e_kg_per_ha']['value']}".replace(".", ",")
    assert _problems(f"Das sind {per_ha} kg CO2e pro Hektar (allocated).", facts)[0] is not None
    assert _problems(f"Work on your fields used {facts['litres']['value']:,} litres of diesel.", facts)[0] is not None


@pytest.mark.parametrize("language", statement_text.LANGUAGES)
@pytest.mark.parametrize("cid", CLIENTS)
def test_the_standard_wording_passes_its_own_checks_in_every_language(cid, language):
    facts = statement_text.gemini_facts(client_statement(cid))
    text, written_in = statement_text.template(facts, language)
    assert written_in == language
    assert _problems(text, facts)[0] is None, text
    assert not re.search(r"verif", text, re.IGNORECASE)


def test_hindi_sentences_end_with_a_danda_and_are_still_checked_one_by_one():
    assert unlabelled_sentences("कुल 3,200 लीटर (measured)। यह 9,400 kg CO2e है।") == ["यह 9,400 kg CO2e है।"]


def test_the_prompt_carries_every_rule_and_the_language():
    p = statement_text.build_prompt({"litres": {"value": 1}}, "hi")
    for rule in ("Copy each number exactly", "full stop for decimals", "(measured), (allocated) or (estimated)", "Do not mention people",
                 "At most 120 words", "Write in Hindi", 'FACTS: {"litres":{"value":1}}'):
        assert rule in p


# --- endpoint --------------------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_api(monkeypatch):
    """Empty cache and an empty limiter (2 a minute) for every test; the model is a stub that counts its calls."""
    calls = []

    def write_for(language):
        def write(facts, rewrite):
            calls.append(language)
            return {"text": _good(facts), "usage": {"input_tokens": 100, "output_tokens": 50, "thinking_tokens": 0}}
        return write
    monkeypatch.setattr(fleet_api, "gen_limiter", AskLimiter(per_minute=2, per_day=10, clock=lambda: 1_790_000_000.0,
                                                            messages=fleet_api.GEN_MESSAGES))
    monkeypatch.setattr(fleet_api, "_statement_cache", {})
    monkeypatch.setattr(fleet_api, "statement_writer", write_for)
    return calls


def test_the_endpoint_returns_facts_and_an_audited_narrative(fresh_api):
    r = api.get("/api/fleet/client-statement", params={"client_id": "C03", "language": "es"})
    assert r.status_code == 200
    body = r.json()
    assert body["client_name"] == "Client farm 03" and body["language"] == "es"
    assert body["narrative"]["narrative_source"] == "gemini" and body["narrative"]["audited"]
    assert body["totals"]["litres"]["value"] == client_statement("C03")["totals"]["litres"]["value"]
    assert "verified" not in json.dumps(body).lower()


def test_the_cache_serves_the_second_view_without_the_model_or_the_limit(fresh_api):
    for _ in range(4):
        assert api.get("/api/fleet/client-statement", params={"client_id": "C03", "language": "en"}).status_code == 200
    assert fresh_api == ["en"]


def test_unknown_client_is_404_and_unsupported_language_is_422(fresh_api):
    assert api.get("/api/fleet/client-statement", params={"client_id": "C99"}).status_code == 404
    assert api.get("/api/fleet/client-statement", params={"client_id": "C03", "language": "fr"}).status_code == 422
    assert fresh_api == []


def test_the_limit_is_429_with_retry_after(fresh_api):
    for cid in ("C01", "C02"):
        assert api.get("/api/fleet/client-statement", params={"client_id": cid}).status_code == 200
    r = api.get("/api/fleet/client-statement", params={"client_id": "C04"})
    assert r.status_code == 429 and r.headers["Retry-After"] and "a minute" in r.json()["detail"]


def test_without_narration_there_is_no_model_call_and_no_limit(fresh_api):
    for cid in ("C01", "C02", "C04", "C05"):
        r = api.get("/api/fleet/client-statement", params={"client_id": cid, "narrate": "false"})
        assert r.status_code == 200 and r.json()["narrative"]["narrative_source"] == "template"
    assert fresh_api == []


def test_a_model_failure_shows_the_standard_wording_and_is_not_cached(fresh_api, monkeypatch):
    def broken(language):
        def write(facts, rewrite):
            raise RuntimeError("503 from Vertex AI")
        return write
    monkeypatch.setattr(fleet_api, "statement_writer", broken)
    body = api.get("/api/fleet/client-statement", params={"client_id": "C03"}).json()
    assert body["narrative"]["narrative_source"] == "template" and "could not be reached" in body["narrative"]["error"]
    assert fleet_api._statement_cache == {}


def test_a_failure_with_no_fallback_is_502(fresh_api, monkeypatch):
    def fails(*a, **k):
        raise RuntimeError("template broke")
    monkeypatch.setattr(fleet_api.statement_text, "narrate_statement", fails)
    r = api.get("/api/fleet/client-statement", params={"client_id": "C03"})
    assert r.status_code == 502 and "template" not in r.json()["detail"]


def test_gemini_text_limits_have_their_own_env_vars_and_defaults(monkeypatch):
    def gen():
        return AskLimiter.from_env(minute_var="FIELDCARBON_GEN_PER_MINUTE", day_var="FIELDCARBON_GEN_PER_DAY", defaults=(6, 300))
    monkeypatch.delenv("FIELDCARBON_GEN_PER_MINUTE", raising=False)
    monkeypatch.delenv("FIELDCARBON_GEN_PER_DAY", raising=False)
    assert (gen().per_minute, gen().per_day) == (6, 300)
    monkeypatch.setenv("FIELDCARBON_GEN_PER_MINUTE", "3")
    monkeypatch.setenv("FIELDCARBON_ASK_PER_MINUTE", "9")
    assert gen().per_minute == 3 and AskLimiter.from_env().per_minute == 9
