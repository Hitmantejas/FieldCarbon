"""Receipt reading: validation rules R1-R8, the extract_receipt tool (fake Gemini) and accuracy scoring. Offline."""
import copy
import json
import shutil

import pytest

from backend.receipts import validate as v
from backend.tools import extract_receipt as er
from evals import receipt_accuracy as acc

PERFECT = acc.ground_truth_extractions()
TARGET = 10813.7


def run(overrides: dict[str, dict] | None = None):
    x = copy.deepcopy(PERFECT)
    x.update(overrides or {})
    return v.validate(sorted(x.items()), "b")


def outcome(lines, rid, no=1):
    return next(l for l in lines if l.receipt_id == rid and l.line_no == no)


def edit(rid: str, **changes) -> dict:
    x = copy.deepcopy(PERFECT[rid])
    for k, val in changes.items():
        if k.startswith("line_"):
            x["lines"][0][k[5:]] = val
        else:
            x[k] = val
    return {rid: x}


# ------------------------------------------------------------------------------------------ rules

def test_a_perfect_reading_counts_exactly_farm_a_litres_and_catches_both_traps():
    lines = run()
    assert v.counted_litres(lines) == TARGET
    assert outcome(lines, "B03", 2).outcome == "excluded" and "R1" in outcome(lines, "B03", 2).reasons[0]
    dup = outcome(lines, "B24")
    assert dup.outcome == "excluded" and dup.duplicate_of == "B22"
    assert {l.outcome for l in lines} == {"accepted", "excluded"}


@pytest.mark.parametrize("product,fuel", [("Red diesel (gas oil)", "gas_oil"), ("GAS OIL", "gas_oil"),
                                          ("Red diesel", "gas_oil"), ("HVO", "hvo"), ("Diesel", "diesel_blend"),
                                          ("AdBlue", ""), ("Engine oil 15W-40", ""), ("Wiper blades", None)])
def test_product_mapping(product, fuel):
    assert v.fuel_type(product) == fuel


def test_misread_digit_is_held_for_review_not_counted():
    lines = run(edit("B04", line_litres=8094.0))  # 809.4 read as 8094
    line = outcome(lines, "B04")
    assert line.outcome == "needs_review" and not line.counts
    assert any(r.startswith("R3") for r in line.reasons) and any(r.startswith("R4") for r in line.reasons)
    assert v.review_litres(lines) == 8094.0
    assert v.counted_litres(lines) == pytest.approx(TARGET - 809.4)


def test_document_arithmetic_and_season():
    assert outcome(run(edit("B05", total=999.0)), "B05").outcome == "needs_review"
    late = outcome(run(edit("B05", date="2027-01-05")), "B05")
    assert late.outcome == "needs_review" and "R6" in " ".join(late.reasons)


def test_low_confidence_and_gallons_need_review():
    low = edit("B06")
    low["B06"]["confidence"]["litres"] = "low"
    assert "R8" in " ".join(outcome(run(low), "B06").reasons)
    assert outcome(run(edit("B06", line_quantity_unit="gallons")), "B06").outcome == "needs_review"


def test_price_in_pence_is_normalised_and_unknown_unit_is_inferred():
    x = edit("B02")
    line = x["B02"]["lines"][0]
    line.update(unit_price=100 * line["unit_price"], unit_price_unit="pence_per_litre")
    assert outcome(run(x), "B02").outcome == "accepted"
    line["unit_price_unit"] = None
    inferred = outcome(run(x), "B02")
    assert inferred.outcome == "accepted_with_warning" and inferred.counts
    assert inferred.unit_price_gbp == pytest.approx(PERFECT["B02"]["lines"][0]["unit_price"])


def test_implausible_price_is_a_warning_but_still_counts():
    x = edit("B07", line_unit_price=2.5)
    x["B07"]["lines"][0]["line_net"] = round(2.5 * x["B07"]["lines"][0]["litres"], 2)
    x["B07"]["net"] = x["B07"]["lines"][0]["line_net"]
    x["B07"]["vat"] = round(x["B07"]["net"] * 0.05, 2)
    x["B07"]["total"] = round(x["B07"]["net"] + x["B07"]["vat"], 2)
    line = outcome(run(x), "B07")
    assert line.outcome == "accepted_with_warning" and "R7" in line.reasons[0]


def test_same_number_with_different_details_is_not_silently_dropped():
    lines = run(edit("B24", total=1.0))
    assert outcome(lines, "B24").outcome == "needs_review"
    assert "R2" in " ".join(outcome(lines, "B24").reasons)


def test_duplicates_are_caught_across_batches():
    seen: dict = {}
    v.validate([("B22", PERFECT["B22"])], "b", seen=seen)
    later = v.validate([("B24", PERFECT["B24"])], "b", seen=seen)
    assert later[0].outcome == "excluded" and later[0].duplicate_of == "B22"


def test_unreadable_receipt_needs_review():
    lines = run({"B10": {"supplier": None, "doc_number": None, "date": None, "lines": [], "net": None,
                         "vat": None, "total": None, "confidence": {}}})
    line = outcome(lines, "B10", 0)
    assert line.outcome == "needs_review" and not line.counts


# ------------------------------------------------------------------------------------------- tool

@pytest.fixture
def farm(tmp_path, monkeypatch):
    shutil.copytree(er.FARM_RECEIPTS["b"] / "receipts", tmp_path / "receipts")
    monkeypatch.setitem(er.FARM_RECEIPTS, "b", tmp_path)
    return tmp_path


def test_read_receipt_stores_provenance_and_reuses_the_stored_reading(farm):
    calls = []

    def fake(image: bytes, mime: str) -> dict:
        calls.append((len(image), mime))
        return PERFECT["B03"]

    raw = er.read_receipt("B03", generate=fake, model="test-model", location="test")
    assert calls and calls[0][1] == "image/jpeg" and calls[0][0] > 10_000
    stored = json.loads((farm / "extractions" / "B03.json").read_text(encoding="utf-8"))
    assert stored["model_id"] == "test-model" and stored["prompt_version"] == er.PROMPT_VERSION
    assert stored["image"].endswith("receipts/B03.jpg") and stored["extracted"] == PERFECT["B03"]
    again = er.read_receipt("B03", generate=lambda *_: pytest.fail("should reuse the stored reading"))
    assert again == raw


def test_extract_receipt_tool_returns_raw_and_validated_lines(farm):
    for rid in ("B22", "B24", "B03"):
        er.read_receipt(rid, generate=lambda *_, r=rid: PERFECT[r])
    out = er.extract_receipt("B24")
    assert out["counted_litres"] == 0 and out["lines"][0]["duplicate_of"] == "B22"
    b03 = er.extract_receipt("B03")
    assert [l["counts"] for l in b03["lines"]] == [True, False]
    assert b03["counted_litres"] == PERFECT["B03"]["lines"][0]["litres"]
    with pytest.raises(KeyError):
        er.extract_receipt("B01", farm_id="z")


def test_prompt_forbids_arithmetic_and_schema_requires_confidence():
    assert "Never calculate" in er.PROMPT
    assert "confidence" in er.SCHEMA["required"] and "lines" in er.SCHEMA["required"]


# ---------------------------------------------------------------------------------------- scoring

def test_a_perfect_reading_scores_100_percent():
    result = acc.score(PERFECT)
    assert result["read"] == 24 and set(result["field_accuracy"].values()) == {1.0}
    assert result["counted_litres"] == result["target_litres"] == TARGET and result["misread_docs"] == []


def test_a_misread_shows_up_in_the_score():
    x = copy.deepcopy(PERFECT)
    x["B04"]["lines"][0]["litres"] = 8094.0
    del x["B10"]
    result = acc.score(x)
    assert result["read"] == 23 and result["field_accuracy"]["litres"] < 1
    assert "B04" in result["misread_docs"] and result["litres_error"] < 0
