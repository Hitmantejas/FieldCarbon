"""BigQuery views and the Python engine must agree, figure by figure (reads GCP; skipped by default).

Run with:  FIELDCARBON_GCP_TESTS=1 pytest -m gcp
The CSV side is the BigQuery export rounded to 4 decimals per row, hence the small tolerances.
"""
import os

import pytest

from backend.emissions import data
from backend.emissions.factors import wtw_factor

pytestmark = [
    pytest.mark.gcp,
    pytest.mark.skipif(os.environ.get("FIELDCARBON_GCP_TESTS") != "1",
                       reason="reads BigQuery; set FIELDCARBON_GCP_TESTS=1 to run"),
]
LITRES_TOL = 0.05   # L, from rounding 850 exported rows to 4 decimals
CO2E_TOL = 0.2      # kg, the same rounding times 3.38 kg/L


@pytest.fixture(scope="module")
def both():
    return data.farm_a_totals("bigquery"), data.farm_a_totals("csv")


def test_summary_agrees(both):
    bq, csv = both
    assert bq.summary.litres.value == pytest.approx(csv.summary.litres.value, abs=LITRES_TOL)
    assert bq.summary.co2e_kg.value == pytest.approx(csv.summary.co2e_kg.value, abs=CO2E_TOL)
    assert bq.summary.hours == pytest.approx(csv.summary.hours, abs=0.01)
    assert bq.excluded_hours == pytest.approx(csv.excluded_hours, abs=0.01)
    assert bq.summary.litres.label == csv.summary.litres.label


def test_bigquery_co2e_equals_python_factor(both):
    bq, _ = both
    factor = wtw_factor("gas_oil", 2025).kg_per_unit
    assert bq.summary.co2e_kg.value == pytest.approx(bq.summary.litres.value * factor, rel=1e-9)


@pytest.mark.parametrize("by", ["operation", "tractor", "field"])
def test_breakdowns_agree_row_by_row(by):
    bq = {r.key: r for r in data.farm_a_breakdown(by, "bigquery")}
    csv = {r.key: r for r in data.farm_a_breakdown(by, "csv")}
    assert bq.keys() == csv.keys()
    for key in bq:
        assert bq[key].litres.value == pytest.approx(csv[key].litres.value, abs=LITRES_TOL), key
        assert bq[key].co2e_kg.value == pytest.approx(csv[key].co2e_kg.value, abs=CO2E_TOL), key
        assert bq[key].litres.label == csv[key].litres.label, key
        assert bq[key].name == csv[key].name, key
