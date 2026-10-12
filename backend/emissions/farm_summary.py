from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.emissions.factors import emissions_kg
from backend.emissions.text import bullets, month_name
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


# Plain-language "how" lines, shared by the CSV path here and the BigQuery path in data.py.
TOTAL_LITRES_HOW = bullets("Each tractor's **own fuel sensor** records how fast it burns fuel.",
                           "We add that up over the whole season, from a public research recording "
                           "(Technical University of Munich).",
                           "Stretches where the recording froze are **left out**.")


def co2e_lines(litres: float, kg_per_l: float, year: int) -> list[str]:
    return [f"**{litres:,.0f} litres** x **{kg_per_l:g} kg of CO2** for each litre of red diesel.",
            f"UK government figures for {year} (UK GHG CF {year}), including the CO2 from making and moving the fuel."]


def cost_lines(litres: float, low: float, high: float, from_month: str, to_month: str) -> list[str]:
    return [f"**{litres:,.0f} litres** x the price of red diesel.",
            f"The price ranged from **£{low:.2f} to £{high:.2f} a litre** between "
            f"{month_name(from_month)} and {month_name(to_month)}.",
            "Your recording has no dates, so we use the whole price range.",
            "The price data does not say whether VAT is included."]


def _figures(litres: float, label: str, litres_how: str) -> tuple[Figure, Figure, Figure]:
    price = fuel_price_range()
    e = emissions_kg(litres, FUEL, EF_YEAR, label)
    return (
        Figure(litres, "L", label, litres_how, source_ids=(TELEMETRY_SOURCE,)),
        Figure(e.kg_co2e, "kg CO2e", label, bullets(*co2e_lines(litres, e.factor.kg_per_unit, EF_YEAR)),
               source_ids=(TELEMETRY_SOURCE, e.factor.source_id)),
        Figure(None, "GBP", "estimated",
               bullets(*cost_lines(litres, price.low, price.high, price.from_month, price.to_month)),
               source_ids=(TELEMETRY_SOURCE, price.source_id), low=litres * price.low, high=litres * price.high),
    )


def summarise(rows: pd.DataFrame) -> Summary:
    litres, co2e, cost = _figures(float(rows.litres.sum()), "measured", TOTAL_LITRES_HOW)
    # Engine hours leave out frozen logger stretches; those are reported separately as excluded hours.
    return Summary(litres, co2e, cost, float(rows[rows.activity_class != EXCLUDED_CLASS].hours.sum()))


@lru_cache(maxsize=1)
def _operation_names() -> dict[str, str]:
    return pd.read_csv(REF / "ref_operations.csv").set_index("operation_code").display_name.to_dict()


def display_name(by: str, key: str) -> str:
    """Plain-language name for a breakdown key; shared by the CSV and BigQuery paths."""
    if by == "operation":
        return _operation_names().get(key) or CLASS_NAMES.get(key, key)
    if by == "tractor":
        return f"Tractor {key[-1]}, {TRACTOR_KW[key]} kW"
    if by == "field":
        return key
    raise ValueError(f"cannot group by {by}")


def split_how(by: str, label: str) -> str:
    if by == "tractor":
        return bullets("Each tractor's litres come straight from **its own fuel sensor**.")
    if by == "field":
        return bullets("The fuel is **measured** by the tractor's sensor.",
                       "Field boundaries are drawn from GPS tracks, so the split by field is **allocated**: less certain than the total.")
    if label == "measured":
        return bullets("The fuel is **measured** by the tractor's sensor.", "This job is labelled in the recording.")
    return bullets("The fuel is **measured** by the tractor's sensor.",
                   "We assigned it to this kind of time by rule, so it is **allocated**: less certain than the total.")


def _key_and_name(rows: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = rows.copy()
    if by == "operation":
        working = (rows.activity_class == "field_work") & rows.operation_code.notna()
        rows["key"] = rows.operation_code.where(working, rows.activity_class)
    elif by == "tractor":
        rows["key"] = rows.tractor_id
    elif by == "field":
        rows["key"] = rows.field_id.fillna("unassigned")
    else:
        raise ValueError(f"cannot group by {by}")
    rows["name"] = rows.key.map(lambda k: display_name(by, k))
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
                                      split_how(by, label))
        out.append(BreakdownRow(key, g.name.iloc[0], litres, co2e, cost, float(g.hours.sum()),
                                100 * float(g.litres.sum()) / total))
    return sorted(out, key=lambda r: -r.litres.value)


@lru_cache(maxsize=1)
def farm_a_rows() -> pd.DataFrame:
    return pd.read_csv(AGG / "farm_a_operations_summary.csv")
