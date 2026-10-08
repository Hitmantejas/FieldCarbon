"""Integrity checks for data/reference: no source = no row, ranges well-formed, mappings resolvable."""
import json
from pathlib import Path

import pandas as pd
import pytest

REF = Path(__file__).resolve().parents[1] / "data" / "reference"


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(REF / name)


@pytest.fixture(scope="module")
def source_ids() -> set[str]:
    src = load("ref_sources.csv")
    assert src["source_id"].is_unique
    return set(src["source_id"])


@pytest.mark.parametrize("name", [
    "ref_emission_factors.csv", "ref_fuel_use_rates.csv", "ref_interventions.csv", "ref_fuel_prices.csv",
])
def test_every_row_has_a_known_source(name, source_ids):
    df = load(name)
    assert df["source_id"].notna().all()
    assert set(df["source_id"]) <= source_ids


def test_emission_factor_ids_unique_and_wtw_components_present():
    ef = load("ref_emission_factors.csv")
    assert ef["ef_id"].is_unique
    for year in (2025, 2026):
        for fuel in ("gas_oil", "diesel_blend", "hvo"):
            comps = set(ef[(ef.year == year) & (ef.fuel_type == fuel)]["component"])
            assert {"scope1_combustion", "wtt"} <= comps, (year, fuel)


def test_gas_oil_wtw_2025_matches_source_components():
    ef = load("ref_emission_factors.csv")
    rows = ef[(ef.year == 2025) & (ef.fuel_type == "gas_oil") & ef.component.isin(["scope1_combustion", "wtt"])]
    assert rows["kgco2e_per_unit"].sum() == pytest.approx(2.75541 + 0.62665)


def test_fuel_rates_conversion_and_ranges():
    r = load("ref_fuel_use_rates.csv")
    assert r["rate_id"].is_unique
    assert (r["l_per_ha"] - r["gal_per_acre"] * 9.354).abs().max() < 0.01
    ranged = r.dropna(subset=["range_low_l_per_ha"])
    assert (ranged.range_low_l_per_ha <= ranged.l_per_ha).all()
    assert (ranged.l_per_ha <= ranged.range_high_l_per_ha).all()


def test_operation_rate_ids_resolve():
    ops = load("ref_operations.csv")
    rate_ids = set(load("ref_fuel_use_rates.csv")["rate_id"])
    assert ops["operation_code"].is_unique
    for col in ("isu_rate_ids", "purdue_rate_ids"):
        for cell in ops[col].dropna():
            assert set(cell.split("|")) <= rate_ids, cell


def test_tum_worktypes_map_to_one_operation():
    ops = load("ref_operations.csv").dropna(subset=["tum_worktypes"])
    seen: list[str] = [w for cell in ops["tum_worktypes"] for w in cell.split("|")]
    assert len(seen) == len(set(seen))


def test_interventions_ranges_and_applicability():
    iv = load("ref_interventions.csv")
    assert iv["coef_id"].is_unique
    assert (iv["low"] <= iv["value"]).all() and (iv["value"] <= iv["high"]).all()
    for cell in iv["applicability"]:
        assert isinstance(json.loads(cell), dict)
    assert 8 <= iv["intervention_id"].nunique() <= 10


def test_fuel_prices_one_row_per_month():
    p = load("ref_fuel_prices.csv")
    assert not p.duplicated(["fuel_type", "price_month"]).any()
    assert (p["price_per_litre"] > 0).all()
