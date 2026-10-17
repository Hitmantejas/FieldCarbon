"""Gemini text checked by code: write, audit, one rewrite, then fixed wording. No live model: every writer is a stub."""
import json

import pytest

from backend.agent import gemini_text
from backend.agent.narrate import clean_facts, foreign_number_format, json_writer, narrate_with_audit

FACTS = {
    "client_name": "Client farm 03",
    "litres": {"value": 3200, "unit": "L", "label": "allocated"},
    "co2e_kg": {"value": 9400, "unit": "kg CO2e", "label": "allocated"},
    "co2e_kg_per_ha": {"value": 29.8, "unit": "kg CO2e/ha", "label": "allocated"},
}
GOOD = "Work on your fields used 3,200 litres of diesel (allocated). That is 9,400 kg of CO2 (allocated)."
INVENTED = "Work on your fields used 3,200 litres of diesel (allocated). That is 12,000 kg of CO2 (allocated)."
UNLABELLED = "Work on your fields used 3,200 litres of diesel."
UNROUNDED = "Work on your fields used 3,200.47 litres of diesel (allocated)."
GERMAN_COMMA = "Pro Hektar sind das 29,8 kg CO2 (allocated)."


def template(facts, language):
    return "Standard wording: 3,200 litres (allocated).", "en"


def scripted(*texts):
    """A writer that returns the given texts in turn and records what it was asked."""
    asked = []

    def write(facts, rewrite):
        asked.append(rewrite)
        text = texts[len(asked) - 1]
        if isinstance(text, Exception):
            raise text
        return {"text": text, "usage": {"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 1}}
    write.asked = asked
    return write


def test_clean_text_passes_on_the_first_try():
    r = narrate_with_audit(FACTS, scripted(GOOD), template)
    assert r["text"] == GOOD and r["narrative_source"] == "gemini" and r["audited"] is True and r["attempts"] == 1
    assert r["usage"] == {"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 1}


def test_an_invented_number_is_rewritten_once_and_the_fix_is_kept():
    write = scripted(INVENTED, GOOD)
    r = narrate_with_audit(FACTS, write, template)
    assert r["text"] == GOOD and r["audited"] is True and r["attempts"] == 2
    assert write.asked[0] is None and "12,000" in write.asked[1]
    assert r["usage"]["input_tokens"] == 20


def test_text_still_bad_after_the_rewrite_falls_back_to_the_fixed_wording():
    r = narrate_with_audit(FACTS, scripted(INVENTED, INVENTED), template)
    assert r["narrative_source"] == "template" and r["audited"] is False and r["attempts"] == 2
    assert r["text"].startswith("Standard wording") and "12,000" not in r["text"]


def test_a_figure_without_its_label_is_sent_back():
    write = scripted(UNLABELLED, GOOD)
    r = narrate_with_audit(FACTS, write, template)
    assert r["audited"] is True and "without its confidence label" in write.asked[1]


def test_an_unrounded_figure_is_sent_back():
    write = scripted(UNROUNDED, GOOD)
    r = narrate_with_audit(FACTS, write, template)
    assert r["audited"] is True and "3,200.47" in write.asked[1]


def test_a_german_decimal_comma_is_caught():
    assert foreign_number_format(GERMAN_COMMA) == ["29,8"]
    write = scripted(GERMAN_COMMA, GERMAN_COMMA)
    r = narrate_with_audit(FACTS, write, template, language="de")
    assert r["narrative_source"] == "template" and "full stop for decimals" in write.asked[1]


def test_digits_other_than_0_to_9_are_caught():
    assert foreign_number_format("कुल ३,२०० लीटर (allocated)") == ["३,२००"]
    assert foreign_number_format("16,492 litres and 29.8 kg (measured)") == []


def test_a_model_error_falls_back_to_the_fixed_wording_with_a_plain_note():
    r = narrate_with_audit(FACTS, scripted(RuntimeError("Vertex AI unavailable: 503 at /v1/...")), template)
    assert r["narrative_source"] == "template" and r["audited"] is False and r["attempts"] == 1
    assert r["error"] == "The model could not be reached, so standard wording is shown." and "503" not in r["error"]


def test_a_fallback_reports_the_language_it_was_written_in():
    r = narrate_with_audit(FACTS, scripted(INVENTED, INVENTED), template, language="hi")
    assert r["narrative_language"] == "en"
    assert narrate_with_audit(FACTS, scripted(GOOD), template, language="hi")["narrative_language"] == "hi"


def test_the_word_verified_is_never_let_through():
    r = narrate_with_audit(FACTS, scripted(GOOD + " All figures verified.", GOOD + " All figures verified."), template)
    assert r["narrative_source"] == "template"


def test_clean_facts_keeps_numbers_units_and_labels_only():
    raw = {"litres": {"value": 3200, "unit": "L", "label": "allocated", "how": "- **3,200 L** from 23 jobs",
                      "source_ids": ["fleet_synthetic"], "low": None, "high": None},
           "operator_id": "OP-04", "rows": [{"operator": "OP-02", "litres": 5}], "source_ids": ["x"]}
    assert clean_facts(raw) == {"litres": {"value": 3200, "unit": "L", "label": "allocated"}, "rows": [{"litres": 5}]}


def test_clean_facts_refuses_an_operator_id_hidden_in_text():
    with pytest.raises(ValueError, match="operator"):
        clean_facts({"note": "Driven by OP-07 at night"})


def test_json_writer_builds_the_prompt_and_parses_the_text():
    seen = []

    def generate(prompt, schema):
        seen.append((prompt, schema))
        return {"text": json.dumps({"text": GOOD}), "usage": {"input_tokens": 3, "output_tokens": 2, "thinking_tokens": 0},
                "model_version": "stub"}
    write = json_writer(lambda facts: f"FACTS: {json.dumps(facts)}", generate=generate)
    assert write(FACTS, None)["text"] == GOOD
    assert write(FACTS, "Fix 12,000.")["text"] == GOOD
    assert seen[0][1]["required"] == ["text"] and "Fix 12,000." in seen[1][0] and "Fix 12,000." not in seen[0][0]


def test_gemini_json_rejects_text_that_is_not_json():
    with pytest.raises(ValueError):
        gemini_text.gemini_json("p", {"type": "object"}, generate=lambda p, s: {"text": "not json", "usage": {}})


def test_gemini_text_returns_text_and_usage_from_the_stub():
    r = gemini_text.gemini_text("p", generate=lambda p, s: {"text": " hi ", "usage": {"input_tokens": 1}, "model_version": "m"})
    assert r == {"text": "hi", "usage": {"input_tokens": 1}, "model_version": "m"}
