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
    recorded = [r for r in load_runs() if not r.get("sample")]
    assert agent["self_test"]["runs"] == 4 and agent["agent"]["runs"] == len(recorded)  # samples never count as agent results


def test_tool_cases_and_label_coverage():
    t = run_all.tool_cases()
    assert t["passed"] == t["cases"] and t["label_and_source_coverage"] == 1.0


def test_a_negative_tool_value_is_matched_by_its_size_because_the_words_carry_the_sign():
    out = {"litres_saved": {"value": -443.36, "unit": "L per year", "label": "estimated", "how": "- **443 extra litres** a year.",
                            "source_ids": ["sondors2014"], "low": None, "high": None}}
    assert fa.audit("It would burn 443 extra litres a year.", [out]).faithful
    assert not fa.audit("It would burn 500 extra litres a year.", [out]).faithful


def test_agent_tokens_count_only_real_runs_that_recorded_them():
    runs = [{"tokens": {"input": 4000, "output": 300, "thinking": 1700}}, {"tokens": None},
            {"tokens": {"input": 9000, "output": 999, "thinking": 999}, "sample": True}]
    assert run_all.agent_tokens(runs) == {"runs": 1, "input": 4000, "output": 300, "thinking": 1700, "per_question": 6000}
    assert run_all.agent_tokens([{"tokens": None}]) is None


SAVING = {"litres_saved": {"value": -443.36, "unit": "L per year", "label": "estimated", "how": "- **443 extra litres** a year.",
                           "source_ids": ["sondors2014"], "low": -600.0, "high": 120.0}}


@pytest.mark.parametrize("answer", ["It would save 443 litres a year.", "That is 443 litres less fuel.",
                                    "You could cut fuel by 443 litres."])
def test_an_increase_called_a_saving_fails_even_though_the_size_matches(answer):
    a = fa.audit(answer, [SAVING])
    assert not a.faithful and a.unmatched[0].wrong_direction
    ok, note = fa.guard(answer, [SAVING])
    assert not ok and "opposite direction" in note


def test_a_real_saving_called_an_increase_fails_and_neutral_wording_passes():
    saved = {"litres_saved": {**SAVING["litres_saved"], "value": 812.0, "how": "Saves **812 litres** a year."}}
    assert fa.audit("It saves 812 litres a year (estimated).", [saved]).faithful
    assert not fa.audit("It needs 812 extra litres a year.", [saved]).faithful
    assert fa.audit("The change is 812 litres a year (estimated).", [saved]).faithful  # no direction stated: size only


def test_a_range_that_crosses_zero_keeps_each_ends_direction():
    assert fa.audit("Between 600 extra litres and a saving of 120 litres.", [SAVING]).faithful
    assert not fa.audit("It saves between 120 and 600 litres.", [SAVING]).faithful  # 600 is an increase


def test_direction_only_applies_to_savings_and_mixed_wording_is_not_judged():
    gap = {"gap_l": -900.0}  # not a saving-type key: the sign has no agreed meaning, so size only
    assert fa.audit("The depot is 900 litres short, more than expected.", [gap]).faithful
    assert fa.audit("It saves fuel on some jobs and uses more on others: 443 litres overall.", [SAVING]).faithful


def test_co2e_per_hectare_traces_as_kg_not_as_hectares():
    # Live run 2026-10-16: "10.65 kg CO2e per hectare" was flagged though client_statement returned exactly that.
    per_ha = {"co2e_per_ha": {"value": 10.65, "unit": "kg CO2e/ha", "label": "allocated", "how": "1,757 kg over 164.9 ha.",
                              "source_ids": ["x"]}}
    for said in ("10.65 kg CO2e per hectare", "10.65 kg CO2e/ha", "10.7 kg per hectare", "10.65 kg/ha"):
        assert fa.audit(f"Our work emitted {said} (allocated).", [per_ha]).faithful, said
    assert not fa.audit("It covered 10.65 hectares.", [per_ha]).faithful   # not an area


def test_each_checked_number_says_which_tool_output_and_which_label_it_came_from():
    """F8 6d: the Ask screen lists every audited number with the calculation it traces to."""
    outputs = [{"note": "Fuel 900 litres more"},
               {"totals": {"litres": {"value": 16492.4, "unit": "L", "label": "measured", "how": "sum", "source_ids": ["x"]}}}]
    a = fa.audit("The fleet used 16,492 litres (measured), against 900 litres in the note, 5 sites and 77 kW.", outputs,
                 "What about our 5 sites?")
    assert fa.traced(a, outputs) == [
        {"text": "16,492 litres", "call": 1, "label": "measured"},
        {"text": "900 litres", "call": 0, "label": None},          # a number in tool text has no figure label
        {"text": "5", "call": "question", "label": None},
        {"text": "77 kW", "call": None, "label": None},             # untraced
    ]
