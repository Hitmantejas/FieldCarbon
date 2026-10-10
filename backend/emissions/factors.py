from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

EF_CSV = Path(__file__).resolve().parents[2] / "data" / "reference" / "ref_emission_factors.csv"

# Biogenic CO2 sits outside the scopes; counting it would undo the HVO saving (CLAUDE.md section 6).
EXCLUDED_COMPONENT = "outside_scopes_biogenic_co2"


@dataclass(frozen=True)
class Factor:
    kg_per_unit: float
    unit: str
    year: int
    source_id: str
    ef_ids: tuple[str, ...]


@dataclass(frozen=True)
class Emissions:
    kg_co2e: float
    label: str
    factor: Factor
    formula: str


@lru_cache(maxsize=1)
def _table() -> pd.DataFrame:
    return pd.read_csv(EF_CSV)


def wtw_factor(fuel_type: str, year: int) -> Factor:
    rows = _table()
    rows = rows[(rows.fuel_type == fuel_type) & (rows.year == year) & (rows.component != EXCLUDED_COMPONENT)]
    if rows.empty:
        raise KeyError(f"no emission factor for {fuel_type} {year}")
    return Factor(
        kg_per_unit=float(rows.kgco2e_per_unit.sum()),
        unit=rows.unit.iloc[0],
        year=year,
        source_id=rows.source_id.iloc[0],
        ef_ids=tuple(rows.ef_id),
    )


def emissions_kg(amount: float, fuel_type: str, year: int, label: str) -> Emissions:
    if amount < 0:
        raise ValueError("amount must not be negative")
    f = wtw_factor(fuel_type, year)
    return Emissions(
        kg_co2e=amount * f.kg_per_unit,
        label=label,
        factor=f,
        formula=f"{amount:g} {f.unit} x {f.kg_per_unit:g} kg CO2e/{f.unit} (UK GHG CF {year}, well-to-wheel)",
    )
