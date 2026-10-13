"""Fleet delivery notes: generated papers, Gemini-read (faked here) and checked against the fuel log. Offline."""
import copy
import shutil

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import generate_delivery_notes as gen
from backend.api.main import app
from backend.receipts.ground_truth import ground_truth, ground_truth_extractions
from backend.receipts.validate import default_settings, fleet_settings, validate
from backend.tools import check_delivery_notes as cdn
from backend.tools import extract_receipt as er

client = TestClient(app)
PERFECT = ground_truth_extractions("fleet")


def kinds(result) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in result["findings"]:
        out.setdefault(f["kind"], []).append(f["doc_no"])
    return out


def test_one_paper_per_note_and_the_planted_price_typo():
    docs, lines = ground_truth("fleet")
    log = pd.read_csv(gen.FLEET / "fuel_deliveries.csv")
    assert len(docs) == log.drop_duplicates(["depot_id", "supplier", "doc_no"]).shape[0] == len(log) - 1
    note = lines[lines.doc_id == gen.PRICE_TYPO_DOC].unit_price_gbp.iloc[0]
    logged = log[log.doc_no == gen.PRICE_TYPO_DOC].unit_price_gbp.iloc[0]
    assert (f"{note:.4f}", f"{logged:.4f}") == ("0.7427", "0.7472")  # last two digits swapped
    for d in docs.itertuples():  # every paper adds up as printed
        l = lines[lines.doc_id == d.doc_id].iloc[0]
        assert round(l.litres * l.unit_price_gbp, 2) == pytest.approx(d.net_gbp, abs=0.005)
        assert d.net_gbp + d.vat_gbp == pytest.approx(d.total_gbp, abs=0.005)
    assert {p.stem for p in (gen.OUT / "receipts").glob("*.jpg")} == set(docs.doc_id)


def test_check_finds_the_duplicate_and_the_price_typo_and_nothing_else():
    r = cdn.check_delivery_notes()
    assert "pending" in r["data_source"] or r["data_source"].startswith("Gemini readings")  # before / after the run
    assert kinds(r) == {"entered_twice": ["DN-S2-0004"], "price_differs": ["DN-S1-0004"]}
    assert (r["notes"], r["log_rows"], r["notes_matching_log"]) == (14, 15, 12)
    price = next(f for f in r["findings"] if f["kind"] == "price_differs")
    assert price["figure"]["value"] == pytest.approx((0.7472 - 0.7427) * 1800)
    assert price["figure"]["label"] == "measured" and "fleet_delivery_notes" in price["figure"]["source_ids"]
    assert r["litres_in_log"]["value"] - r["litres_on_notes"]["value"] == pytest.approx(900)


def test_a_misread_note_is_held_for_review_not_blamed_on_the_log(monkeypatch):
    bad = copy.deepcopy(PERFECT)
    bad["DN-S1-0003"]["lines"][0]["litres"] = 8100.0  # 1,800 read as 8,100
    monkeypatch.setattr(cdn, "_readings", lambda: (bad, "test readings"))
    k = kinds(cdn.check_delivery_notes())
    assert k["note_needs_review"] == ["DN-S1-0003"] and "litres_differ" not in k


def test_a_note_missing_from_the_log_and_a_log_row_without_a_note(monkeypatch):
    log = cdn.data.deliveries()
    monkeypatch.setattr(cdn.data, "deliveries", lambda: log[log.doc_no != "DN-S1-0002"])
    assert kinds(cdn.check_delivery_notes())["note_not_in_log"] == ["DN-S1-0002"]
    fewer = {k: v for k, v in PERFECT.items() if k != "DN-S1-0005"}
    monkeypatch.setattr(cdn.data, "deliveries", lambda: log)
    monkeypatch.setattr(cdn, "_readings", lambda: (fewer, "test readings"))
    assert kinds(cdn.check_delivery_notes())["log_row_without_note"] == ["DN-S1-0005"]


def test_a_depot_delivery_can_be_larger_than_a_farm_receipt():
    note = {"DN-S1-0006": PERFECT["DN-S1-0006"]}  # 2,400 L into a 3,000 L depot
    assert validate(list(note.items()), "fleet", fleet_settings())[0].outcome == "accepted"
    assert validate(list(note.items()), "b", default_settings())[0].outcome == "needs_review"


def test_stored_gemini_readings_replace_the_ground_truth(tmp_path, monkeypatch):
    shutil.copytree(er.FARM_RECEIPTS["fleet"] / "receipts", tmp_path / "receipts")
    monkeypatch.setitem(er.FARM_RECEIPTS, "fleet", tmp_path)
    for rid, x in PERFECT.items():
        er.read_receipt(rid, "fleet", generate=lambda *_, x=x: x, model="test-model", location="test")
    r = cdn.check_delivery_notes()
    assert r["data_source"].startswith("Gemini readings (test-model)")
    assert kinds(r) == {"entered_twice": ["DN-S2-0004"], "price_differs": ["DN-S1-0004"]}


def test_api_endpoint():
    body = client.get("/api/fleet/delivery-notes").json()
    assert body["notes"] == 14 and len(body["findings"]) == 2
