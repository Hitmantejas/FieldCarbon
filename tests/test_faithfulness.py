"""Auditor: every number in an answer must come from a tool output. Offline."""
import json

import pytest

from backend.agent import faithfulness as fa
from backend.agent.runs import load_runs, record_run
from evals import run_all

OUT = {"rows": [{"name": "Arable site (Bavaria)", "hours": 766.1487,
                 "litres": {"value": 10813.6912, "unit": "L", "label": "measured", "how": "- **10,814 litres** over 766 hours.",
                            "source_ids": ["tum_alc_data"], "low": None, "high": None},
                 "co2e_kg": {"value": 36572.55, "unit": "kg CO2e", "label": "measured", "how": "x 3.38206 kg",
                             "source_ids": ["tum_alc_data", "uk_ghg_2025"], "low": None, "high": None},
                 "cost_gbp": {"value": None, "unit": "GBP", "label": "estimated", "how": "price range",
                              "source_ids": ["defra_ukammg"], "low": 8099.4, "high": 12717.2},
                 "share_pct": 65.57, "jobs": 329}]}


def faithful(answer: str, question: str = "") -> bool:
    return fa.audit(answer, [OUT], question).faithful


@pytest.mark.parametrize("answer", [
    "The arable site burned 10,814 litres.",           # rounded as displayed
    "It burned 10,813.69 L.",                           # more decimals, still within display rounding
    "About 36.6 t of CO2e.",                            # kg in the tool, tonnes in the answer
    "Emissions were 36,573 kg CO2e.",
    "Fuel cost £8.1k to £12.7k.",                       # money with k suffix, a range from low/high
    "It was 65.6% of the fleet's fuel over 766 hours.",  # percent and hours from raw fields
    "Roughly 11,000 litres.",                           # trailing zeros mean "to the nearest thousand"
    "329 jobs were recorded.",                          # a count
    "No numbers at all in this answer.",
])
def test_faithful_answers_pass(answer):
    assert faithful(answer)


@pytest.mark.parametrize("answer,bad", [
    ("The arable site burned 10,841 litres.", "10,841 litres"),       # swapped digits
    ("About 37.6 t of CO2e.", "37.6 t"),                               # wrong value in another unit
    ("It burned 36.6 litres.", "36.6 litres"),                         # right digits, wrong unit
    ("Fuel and CO2 together come to 47,386.", "47,386"),               # a sum the tools never gave
    ("That is 12% less than last year.", "12%"),                       # an invented comparison
])
def test_unfaithful_answers_are_flagged(answer, bad):
    a = fa.audit(answer, [OUT])
    assert not a.faithful and bad in [n.text for n in a.unmatched]


def test_numbers_from_the_question_are_allowed():
    assert not faithful("Your 20% goal needs 7.3 t.")
    assert fa.audit("Your 20% goal is noted.", [OUT], "I want to cut emissions by 20%").faithful


@pytest.mark.parametrize("text", [
    "Data from 2025, tractor S1-T4, Iowa A3-27 rates, operator OP-01, CO2e.",
    "On 17 January 2026 and on 2025-10-03 the depot was checked.",
    "1. First idea\n2. Second idea",
    "Client farm 09 is a 4x4 operation, the 2nd largest.",
])
def test_ids_dates_years_and_list_numbers_are_not_figures(text):
    assert fa.find_numbers(text) == []


def test_ranges_share_their_unit_and_results_say_where_numbers_came_from():
    found = fa.find_numbers("between 1.0 and 3.6 t")
    assert [f.family for f in found] == ["kg", "kg"] and found[0].value == 1000
    a = fa.audit("The arable site burned 10,814 litres.", [OUT])
    assert a.numbers[0].source == "tool[0].rows[0].litres.value"


def test_numbers_written_in_tool_text_count_as_tool_output():
    assert fa.audit("A factor of 3.38206 kg per litre.", [OUT]).faithful


def test_guard_returns_a_note_listing_the_untraced_numbers():
    ok, note = fa.guard("It burned 10,814 litres.", [OUT])
    assert ok and note is None
    ok, note = fa.guard("It burned 10,841 litres, 12% less.", [OUT])
    assert not ok and "10,841 litres" in note and "12%" in note


def test_record_run_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.agent.runs.RUNS", tmp_path)
    record_run("fleet-summary", "How much fuel?", [{"name": "fleet_summary", "args": {}, "output": OUT}],
               "10,814 litres.", "test-model", "v0")
    runs = load_runs(tmp_path)
    assert runs[0]["model"] == "test-model" and runs[0]["sample"] is False
    assert json.loads((tmp_path / "agent.jsonl").read_text(encoding="utf-8"))["case_id"] == "fleet-summary"


def test_harness_scores_runs_and_keeps_samples_apart():
    results = [run_all.score_run(r) for r in load_runs() if r.get("sample")]
    assert len(results) == 4
    assert sum(r["faithful"] for r in results) == 2       # two faithful, two unfaithful on purpose
    assert any(r["tool_selection"] is False for r in results)  # the wrong-tool sample
    agent = run_all.agent_runs()
    assert agent["self_test"]["runs"] == 4 and agent["agent"]["runs"] == 0


def test_tool_cases_and_label_coverage():
    t = run_all.tool_cases()
    assert t["passed"] == t["cases"] and t["label_and_source_coverage"] == 1.0
