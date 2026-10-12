import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


def test_summary_has_labelled_figures_and_provenance():
    body = client.get("/api/farms/a/summary").json()
    assert body["litres"]["label"] == "measured"
    assert body["co2e_kg"]["unit"] == "kg CO2e" and "UK GHG CF 2025" in body["co2e_kg"]["how"]
    assert body["cost_gbp"]["low"] < body["cost_gbp"]["high"]
    assert body["provenance"]["demo_data"] is True
    assert "CC-BY-4.0" in body["provenance"]["licence"]
    assert len(body["tractors"]) == 5


def test_breakdown_by_each_grouping():
    for by in ("operation", "tractor", "field"):
        rows = client.get(f"/api/farms/a/breakdown/{by}").json()
        assert rows and all(r["litres"]["label"] in {"measured", "allocated"} for r in rows)


def test_breakdown_totals_match_summary():
    total = client.get("/api/farms/a/summary").json()["litres"]["value"]
    rows = client.get("/api/farms/a/breakdown/operation").json()
    assert sum(r["litres"]["value"] for r in rows) == pytest.approx(total)


def test_unknown_grouping_is_404():
    assert client.get("/api/farms/a/breakdown/colour").status_code == 404


def test_unknown_farm_is_404():
    assert client.get("/api/farms/z/summary").status_code == 404


def test_pain_points_endpoint():
    body = client.get("/api/farms/a/pain-points").json()
    assert 30 < body["not_working"]["share_pct"] < 36
    bands = {r["operation_code"]: r["band"] for r in body["ratings"]}
    assert bands["ploughing"] == "above_typical"


def test_summary_hours_exclude_frozen_data_and_attribution_is_complete():
    body = client.get("/api/farms/a/summary").json()
    assert body["excluded_hours"] > 90 and body["hours"] < 800    # 95.7 h excluded, not double counted
    assert "10.5281/zenodo.14619787" in body["provenance"]["dataset"]
    assert "Götz" in body["provenance"]["dataset"]
    assert body["litres"]["source_ids"] == ["tum_alc_data"]


def test_pain_points_show_where_the_two_sources_agree():
    body = client.get("/api/farms/a/pain-points").json()
    agree = {r["operation_code"]: r["sources_agree"] for r in body["ratings"]}
    assert agree["ploughing"] is False and agree["seedbed_combination"] is True
    assert body["above_range"]["label"] == "estimated"


def test_pain_points_carry_plain_explanations_and_a_summary():
    body = client.get("/api/farms/a/pain-points").json()
    assert all(r["how"] for r in body["ratings"])
    assert body["above_range"]["count"] >= 1
    assert body["above_range"]["litres_low"] <= body["above_range"]["litres_high"]


def test_interventions_endpoint_ranks_and_cites():
    body = client.get("/api/farms/a/interventions").json()
    assert [i["state"] for i in body] == sorted((i["state"] for i in body), key=["feasible", "needs_info", "not_feasible"].index)
    assert all(i["evidence"] and i["how"] and "roi" in i for i in body)
    assert client.get("/api/farms/z/interventions").status_code == 404
