"""Data layer: CSV and BigQuery paths return the same contract; tests use a fake BigQuery (no GCP)."""
import pytest

from backend.emissions import data
from backend.emissions.farm_summary import breakdown, farm_a_rows, summarise

SETTINGS = {"fuel_type": "gas_oil", "ef_year": 2025, "kgco2e_per_l": 3.38206, "ef_ids": ["a", "b"],
            "ef_source_id": "uk_ghg_2025", "price_low": 0.718, "price_high": 1.176,
            "from_month": "2025-05", "to_month": "2026-08", "price_source_id": "defra_ukammg"}
SUMMARY = {"litres": 100.0, "co2e_kg": 338.206, "cost_gbp_low": 74.9, "cost_gbp_high": 117.6,
           "hours": 10.0, "excluded_hours": 2.0, "label": "measured"}
TRACTORS = [
    {"key": "tractor_1", "litres": 40.0, "co2e_kg": 135.2824, "cost_gbp_low": 29.96, "cost_gbp_high": 47.04,
     "hours": 4.0, "share_pct": 40.0, "label": "measured"},
    {"key": "tractor_2", "litres": 60.0, "co2e_kg": 202.9236, "cost_gbp_low": 44.94, "cost_gbp_high": 70.56,
     "hours": 6.0, "share_pct": 60.0, "label": "measured"},
]
seen: list[str] = []


def fake_query(sql: str) -> list[dict]:
    seen.append(sql)
    if "v_farm_a_settings" in sql:
        return [SETTINGS]
    if "v_farm_a_summary" in sql:
        return [SUMMARY]
    if "v_farm_a_emissions_by_tractor" in sql:
        return TRACTORS
    raise AssertionError(f"unexpected query: {sql}")


def test_default_source_is_csv_and_unknown_is_rejected(monkeypatch):
    monkeypatch.delenv("FIELDCARBON_DATA", raising=False)
    assert data.source() == "csv"
    monkeypatch.setenv("FIELDCARBON_DATA", "excel")
    with pytest.raises(ValueError):
        data.source()


def test_csv_path_matches_the_python_engine():
    rows = farm_a_rows()
    t = data.farm_a_totals("csv")
    assert t.summary == summarise(rows)
    assert t.excluded_hours == pytest.approx(float(rows[rows.activity_class == "data_gap"].hours.sum()))
    assert data.farm_a_breakdown("field", "csv") == breakdown(rows, "field")


def test_bigquery_summary_maps_view_rows_to_labelled_sourced_figures():
    t = data.farm_a_totals("bigquery", query=fake_query)
    s = t.summary
    assert (s.litres.value, s.co2e_kg.value, s.hours, t.excluded_hours) == (100.0, 338.206, 10.0, 2.0)
    assert s.litres.label == "measured" and s.cost_gbp.label == "estimated"
    assert (s.cost_gbp.low, s.cost_gbp.high) == (74.9, 117.6)
    assert s.co2e_kg.source_ids == ("tum_alc_data", "uk_ghg_2025")
    assert "v_farm_a_summary" in s.co2e_kg.how and "3.38206" in s.co2e_kg.how
    assert "BigQuery" in t.data_source
    assert any("`ai-hackathon-india.fieldcarbon.v_farm_a_summary`" in q for q in seen)


def test_bigquery_breakdown_uses_python_names_and_sorts_by_litres():
    rows = data.farm_a_breakdown("tractor", "bigquery", query=fake_query)
    assert [r.key for r in rows] == ["tractor_2", "tractor_1"]
    assert rows[0].name == "Tractor 2, 104 kW" and rows[0].share_pct == 60.0
    assert all(r.litres.label == "measured" for r in rows)


def test_unknown_grouping_is_rejected_on_both_paths():
    for src in ("csv", "bigquery"):
        with pytest.raises(ValueError):
            data.farm_a_breakdown("colour", src, query=fake_query)


def test_bigquery_explanations_match_the_csv_wording_plus_where_it_was_calculated():
    bq = data.farm_a_totals("bigquery", query=fake_query).summary
    csv = data.farm_a_totals("csv").summary
    assert bq.litres.how == csv.litres.how
    assert bq.co2e_kg.how.splitlines()[-1] == "- Calculated in BigQuery (view v_farm_a_summary)."
    row = data.farm_a_breakdown("tractor", "bigquery", query=fake_query)[0]
    assert row.litres.how == data.farm_a_breakdown("tractor", "csv")[0].litres.how
