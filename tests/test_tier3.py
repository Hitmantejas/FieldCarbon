"""Farm B (Tier 3): receipts total, estimated split by operation, remainder, range coverage, API. Offline."""
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.emissions import tier3
from backend.emissions.factors import wtw_factor
from backend.emissions.pain_points import reference_range
from evals import range_coverage

client = TestClient(app)
GAS_OIL = wtw_factor("gas_oil", 2025).kg_per_unit


def all_figures(rows):
    for r in rows:
        yield from (r.litres, r.co2e_kg, r.cost_gbp)


def test_receipt_totals_add_up_to_farm_a_fuel_and_money_paid():
    t = tier3.receipt_totals()
    assert t.litres == 10813.7 and t.documents == 23  # 24 images, one is a duplicate photo
    assert 8000 < t.net_gbp < 12000
    s = tier3.summarise(t)
    assert s.litres.label == "measured" and s.litres.source_ids == ("farm_b_receipts",)
    assert s.co2e_kg.value == pytest.approx(t.litres * GAS_OIL)
    assert s.cost_gbp.label == "measured" and s.cost_gbp.low == s.cost_gbp.high == t.net_gbp
    assert "used this season" in s.litres.how and s.hours is None


def test_operation_ranges_are_area_times_published_rates():
    est = {e.operation_code: e for e in tier3.operation_estimates()}
    area = tier3.profile().groupby("operation_code").area_ha.sum()
    ref = reference_range("ploughing")
    p = est["ploughing"]
    assert p.area_ha == pytest.approx(area["ploughing"])
    assert (p.low, p.typical, p.high) == pytest.approx((p.area_ha * ref.low, p.area_ha * ref.typical, p.area_ha * ref.high))
    assert "transport" not in est  # no published rate: its fuel stays in the remainder


def test_breakdown_is_estimated_sourced_and_never_cites_telemetry():
    rows = tier3.breakdown_by_operation()
    for f in all_figures(rows):
        assert f.label == "estimated" and f.low <= f.value <= f.high
        assert "tum_alc_data" not in f.source_ids  # Farm B never sees the telemetry
    ops = [r for r in rows if r.key != tier3.REMAINDER_KEY]
    assert all({"farm_b_profile", "isu_a3_27"} <= set(r.litres.source_ids) for r in ops)


def test_remainder_is_total_minus_field_jobs_and_never_negative():
    t = tier3.receipt_totals()
    est = tier3.operation_estimates()
    rem = next(r for r in tier3.breakdown_by_operation(t, est) if r.key == tier3.REMAINDER_KEY)
    assert rem.litres.low == pytest.approx(t.litres - sum(e.high for e in est))
    assert rem.litres.high == pytest.approx(t.litres - sum(e.low for e in est))
    huge = [tier3.OperationEstimate("ploughing", 1000, 20000, 30000, 40000, ("farm_b_profile", "isu_a3_27"))]
    rem = next(r for r in tier3.breakdown_by_operation(t, huge) if r.key == tier3.REMAINDER_KEY)
    assert rem.litres.low == rem.litres.value == rem.litres.high == 0.0


def test_range_coverage_is_reported_honestly():
    c = range_coverage.coverage()
    assert c["operations"] == 12 and c["operations_inside"] == 8 and c["remainder_inside"]
    assert {m["key"] for m in c["misses"]} == {"ploughing", "mulching", "seedbed_combination", "mowing"}
    assert all((m["side"] == "above") == (m["measured"] > m["high"]) for m in c["misses"])


def test_farm_b_api():
    s = client.get("/api/farms/b/summary").json()
    assert s["farm"]["tier"] == 3 and s["litres"]["value"] == 10813.7 and s["provenance"]["demo_data"]
    rows = client.get("/api/farms/b/breakdown/operation").json()
    assert rows[0]["litres"]["label"] == "estimated"
    r = client.get("/api/farms/b/breakdown/tractor")
    assert r.status_code == 404 and "receipts only" in r.json()["detail"]
    sources = {x["source_id"] for x in client.get("/api/sources").json()}
    cited = {i for row in rows for k in ("litres", "co2e_kg", "cost_gbp") for i in row[k]["source_ids"]}
    cited |= {i for k in ("litres", "co2e_kg", "cost_gbp") for i in s[k]["source_ids"]}
    assert cited <= sources
