"""Farm B synthetic receipts and profile: totals tie to Farm A, paperwork adds up, no fuel or coordinates leak."""
from pathlib import Path

import pandas as pd
import pytest

import generate_farm_b as gen

OUT = gen.OUT
DOCS = pd.read_csv(OUT / "ground_truth_documents.csv", keep_default_na=False)
LINES = pd.read_csv(OUT / "ground_truth_lines.csv")
PROFILE = pd.read_csv(OUT / "farm_b_profile.csv")


def test_committed_ground_truth_is_what_the_generator_produces():
    docs, lines = gen.plan()
    assert [vars(d) for d in docs] == DOCS.assign(vat_rate=DOCS.vat_rate.astype(float)).to_dict("records")
    assert len(lines) == len(LINES)
    assert [l.litres for l in lines] == LINES.litres.tolist()


def test_counted_diesel_equals_farm_a_measured_litres():
    counted = LINES[LINES.counts_toward_fuel]
    assert (counted["product"] == gen.DIESEL).all()
    assert sum(round(x * 100) for x in counted.litres) == round(round(gen.farm_a_total_litres(), 1) * 100)
    assert counted.litres.sum() == pytest.approx(gen.farm_a_total_litres(), abs=0.05)


def test_document_count_and_traps():
    assert 20 <= len(DOCS) <= 30
    dup = DOCS[DOCS.duplicate_of != ""]
    assert len(dup) == 1 and not dup.counts_toward_total.iloc[0]
    original = DOCS[DOCS.doc_id == dup.duplicate_of.iloc[0]].iloc[0]
    assert original.doc_number == dup.doc_number.iloc[0]  # same paper, photographed twice
    adblue = LINES[LINES["product"] == gen.ADBLUE]
    assert len(adblue) == 1 and not adblue.counts_toward_fuel.iloc[0]


def test_every_document_adds_up_as_printed():
    for d in DOCS.itertuples():
        lines = LINES[LINES.doc_id == d.doc_id]
        for l in lines.itertuples():
            assert round(l.litres * l.unit_price_gbp, 2) == pytest.approx(l.net_gbp, abs=0.005), d.doc_id
        assert lines.net_gbp.sum() == pytest.approx(d.net_gbp, abs=0.005)
        assert round(d.net_gbp * d.vat_rate, 2) == pytest.approx(d.vat_gbp, abs=0.005)
        assert d.net_gbp + d.vat_gbp == pytest.approx(d.total_gbp, abs=0.005)


def test_prices_follow_defra_months_and_supplies_stay_under_the_reduced_rate_limit():
    prices = gen.monthly_prices()
    diesel = LINES[LINES["product"] == gen.DIESEL].merge(DOCS[["doc_id", "price_month", "date"]], on="doc_id")
    for l in diesel.itertuples():
        assert l.date.startswith(l.price_month) and l.price_month in prices
        assert l.unit_price_gbp == pytest.approx(prices[l.price_month], rel=0.031)
    assert diesel.litres.max() <= gen.MAX_SUPPLY_L


def test_document_numbers_rise_with_dates_per_supplier():
    originals = DOCS[DOCS.duplicate_of == ""]
    for _, g in originals.groupby("supplier"):
        numbers = g.sort_values("date").doc_number.str.split("-").str[1].astype(int)
        assert numbers.is_monotonic_increasing


def test_every_document_has_an_image():
    assert {p.stem for p in (OUT / "receipts").glob("*.jpg")} == set(DOCS.doc_id)


def test_profile_has_no_fuel_no_coordinates_and_valid_operations():
    cols = set(PROFILE.columns)
    assert not cols & {"litres", "lat", "lon", "latitude", "longitude", "x", "y", "geometry"}
    assert (PROFILE.label == "user-provided").all()
    assert (PROFILE.area_ha >= gen.MIN_PROFILE_HA).all() and (PROFILE.area_ha <= PROFILE.field_area_ha).all()
    ops = set(pd.read_csv(gen.REF / "ref_operations.csv").operation_code)
    assert set(PROFILE.operation_code) <= ops and "transport" not in set(PROFILE.operation_code)
    fields = set(pd.read_csv(gen.AGG / "farm_a_fields.csv").field_id)
    assert set(PROFILE.field_id) <= fields


@pytest.mark.skipif(not (gen.FONTS / "Inkfree.ttf").exists(), reason="rendering uses Windows fonts")
def test_rendering_is_deterministic():
    docs, lines = gen.plan()
    a, b = gen.render(docs[0], lines), gen.render(docs[0], lines)
    assert a.tobytes() == b.tobytes() and max(a.size) == 1000
