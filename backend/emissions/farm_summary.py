from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.emissions.factors import emissions_kg
from backend.tools.contracts import Figure, weakest

REF = Path(__file__).resolve().parents[2] / "data" / "reference"
AGG = Path(__file__).resolve().parents[2] / "data" / "aggregated"

FUEL = "gas_oil"  # red diesel; TUM is a 2024 season, so the 2025 factor set
EF_YEAR = 2025
TELEMETRY_SOURCE = "tum_alc_data"
EXCLUDED_CLASS = "data_gap"  # frozen logger stretches: reported separately, never counted

# Rated power from the TUM article, Table 1; brands are anonymised.
TRACTOR_KW = {"tractor_1": 77, "tractor_2": 104, "tractor_3": 140, "tractor_4": 163, "tractor_5": 174}

CLASS_NAMES = {
    "implement_nonproductive": "Implement attached, not working",
    "road_transport": "Road transport",
    "idle": "Idling",
    "offroad_unassigned": "Off-road, unassigned",
}


@dataclass(frozen=True)
class PriceRange:
    low: float
    high: float
    from_month: str
    to_month: str
    source_id: str


@dataclass(frozen=True)
class Summary:
    litres: Figure
    co2e_kg: Figure
    cost_gbp: Figure
    hours: float


@dataclass(frozen=True)
class BreakdownRow:
    key: str
    name: str
    litres: Figure
    co2e_kg: Figure
    cost_gbp: Figure
    hours: float
    share_pct: float


@lru_cache(maxsize=1)
def fuel_price_range() -> PriceRange:
    p = pd.read_csv(REF / "ref_fuel_prices.csv")
    p = p[p.fuel_type == FUEL]
    return PriceRange(float(p.price_per_litre.min()), float(p.price_per_litre.max()),
                      p.price_month.min()[:7], p.price_month.max()[:7], p.source_id.iloc[0])


def _figures(litres: float, label: str, litres_how: str) -> tuple[Figure, Figure, Figure]:
    price = fuel_price_range()
    e = emissions_kg(litres, FUEL, EF_YEAR, label)
    return (
        Figure(litres, "L", label, litres_how, source_ids=(TELEMETRY_SOURCE,)),
        Figure(e.kg_co2e, "kg CO2e", label, e.formula, source_ids=(TELEMETRY_SOURCE, e.factor.source_id)),
        Figure(None, "GBP", "estimated",
               f"{litres:g} L x GBP {price.low:g}-{price.high:g}/L (Defra UKAMMG gas oil, {price.from_month} to "
               f"{price.to_month}; TUM dates are anonymised, so a price range is used; VAT basis not stated)",
               source_ids=(TELEMETRY_SOURCE, price.source_id),
               low=litres * price.low, high=litres * price.high),
    )


def summarise(rows: pd.DataFrame) -> Summary:
    litres, co2e, cost = _figures(float(rows.litres.sum()), "measured",
                                  "Engine fuel-rate (J1939) integrated over time, TUM Agricultural Load Cycles")
    # Engine hours leave out frozen logger stretches; those are reported separately as excluded hours.
    return Summary(litres, co2e, cost, float(rows[rows.activity_class != EXCLUDED_CLASS].hours.sum()))


def _key_and_name(rows: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = rows.copy()
    if by == "operation":
        ops = pd.read_csv(REF / "ref_operations.csv").set_index("operation_code").display_name
        working = (rows.activity_class == "field_work") & rows.operation_code.notna()
        rows["key"] = rows.operation_code.where(working, rows.activity_class)
        rows["name"] = rows.key.map(ops).fillna(rows.key.map(CLASS_NAMES))
    elif by == "tractor":
        rows["key"] = rows.tractor_id
        rows["name"] = rows.key.map(lambda t: f"Tractor {t[-1]}, {TRACTOR_KW[t]} kW")
    elif by == "field":
        rows["key"] = rows.field_id.fillna("unassigned")
        rows["name"] = rows.key
    else:
        raise ValueError(f"cannot group by {by}")
    return rows


def breakdown(rows: pd.DataFrame, by: str) -> list[BreakdownRow]:
    rows = _key_and_name(rows[rows.litres > 0], by)
    total = rows.litres.sum()
    out = []
    for key, g in rows.groupby("key"):
        # A tractor's own total is measured directly; its split by activity does not change it.
        # Per-field figures stay allocated even when litres are measured: boundaries have no ground truth.
        # By operation, the weakest label of the attributed rows wins.
        label = {"tractor": "measured", "field": "allocated"}.get(by) or weakest(g.attribution_label)
        litres, co2e, cost = _figures(float(g.litres.sum()), label,
                                      f"Measured telemetry litres attributed by {by} ({label})")
        out.append(BreakdownRow(key, g.name.iloc[0], litres, co2e, cost, float(g.hours.sum()),
                                100 * float(g.litres.sum()) / total))
    return sorted(out, key=lambda r: -r.litres.value)


def farm_a_rows() -> pd.DataFrame:
    return pd.read_csv(AGG / "farm_a_operations_summary.csv")
