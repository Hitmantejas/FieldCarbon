"""Well-to-wheel CO2e from litres: boundary rules from CLAUDE.md section 6."""
import pytest

from backend.emissions.factors import emissions_kg, wtw_factor


def test_gas_oil_2025_is_combustion_plus_wtt():
    assert wtw_factor("gas_oil", 2025).kg_per_unit == pytest.approx(2.75541 + 0.62665)


def test_hvo_excludes_biogenic_co2():
    # Including the 2.43 biogenic row would make HVO look like diesel again.
    assert wtw_factor("hvo", 2025).kg_per_unit == pytest.approx(0.03558 + 0.56439)


def test_electricity_sums_generation_td_and_both_wtt():
    expected = 0.177 + 0.01853 + 0.0459 + 0.00397
    assert wtw_factor("electricity_uk", 2025).kg_per_unit == pytest.approx(expected)


def test_factor_is_traceable():
    f = wtw_factor("gas_oil", 2025)
    assert f.year == 2025
    assert f.unit == "litre"
    assert f.source_id == "uk_ghg_2025"
    assert set(f.ef_ids) == {"gas_oil_s1_2025", "gas_oil_wtt_2025"}


def test_emissions_scale_linearly_and_carry_the_label():
    e = emissions_kg(1000, "gas_oil", 2025, label="measured")
    assert e.kg_co2e == pytest.approx(3382.06)
    assert e.label == "measured"
    assert "1000" in e.formula and "3.38206" in e.formula


def test_zero_litres_is_zero_emissions():
    assert emissions_kg(0, "gas_oil", 2025, label="measured").kg_co2e == 0


def test_negative_amount_is_rejected():
    with pytest.raises(ValueError):
        emissions_kg(-1, "gas_oil", 2025, label="measured")


def test_unknown_fuel_or_year_is_rejected():
    with pytest.raises(KeyError):
        wtw_factor("kerosene", 2025)
    with pytest.raises(KeyError):
        wtw_factor("gas_oil", 1999)
