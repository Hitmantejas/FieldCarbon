"""Litres, CO2e and cost figures for any slice of the fuel ledger, built to the shared figure contract."""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from backend.emissions.factors import wtw_factor
from backend.emissions.farm_summary import EF_YEAR, FUEL
from backend.emissions.text import bullets
from backend.fleet.data import price_by_month
from backend.tools.contracts import Figure, weakest

SYNTHETIC_SOURCE = "fleet_synthetic"
VINEYARD_SOURCE = "vineyard_ops"  # S2: fuel per operation read from the tank level (Rossi & Alemanno)


def _label(df: pd.DataFrame) -> str:
    return weakest(list(df.label.unique())) if len(df) else "measured"


def _sources(df: pd.DataFrame, synthetic: bool, *extra: str) -> tuple[str, ...]:
    ids = list(dict.fromkeys(df.source_id)) + ([SYNTHETIC_SOURCE] if synthetic else []) + list(extra)
    return tuple(dict.fromkeys(ids))


def slice_figures(df: pd.DataFrame, synthetic_cols: bool = False) -> dict:
    """The three figures for one slice. `synthetic_cols` is true when the slice is cut by a synthetic column."""
    litres, hours = float(df.litres.sum()), float(df.hours.sum())
    label = _label(df)
    price = price_by_month()
    cost = float((df.litres * df.month.map(price)).sum())
    factor = wtw_factor(FUEL, EF_YEAR)

    vineyard = df.source_id == VINEYARD_SOURCE
    how = [f"**{litres:,.0f} litres** burned over **{hours:,.0f} hours**."]
    if label != "measured":
        how.append("Includes fuel burned outside jobs (transport, idling, tool not working). It is measured in total and "
                   "**shared across months by rule**.")
    elif not vineyard.all():
        how.append("Recorded by the machines' own fuel data.")
    if vineyard.any():  # still measured, but a coarser reading than a flow sensor
        how.append(("Vineyard fuel is" if not vineyard.all() else "Fuel is") + " **read from the tractors' tank levels**, "
                   "not from a fuel-flow sensor.")
    if synthetic_cols:
        how.append("Dates, clients and operators in this demo are synthetic.")
    src = _sources(df, synthetic_cols)
    avg = cost / litres if litres else 0.0
    return {
        "litres": asdict(Figure(litres, "L", label, bullets(*how), source_ids=src)),
        "co2e_kg": asdict(Figure(litres * factor.kg_per_unit, "kg CO2e", label, bullets(
            f"**{litres:,.0f} litres** x **{factor.kg_per_unit:g} kg of CO2** for each litre of red diesel.",
            f"UK government figures for {EF_YEAR} (UK GHG CF {EF_YEAR}), including the CO2 from making and moving the fuel."),
            source_ids=src + (factor.source_id,))),
        "cost_gbp": asdict(Figure(cost, "GBP", label, bullets(
            f"**{litres:,.0f} litres** x the price paid in each month's fuel deliveries.",
            f"That averages **£{avg:.3f} a litre**. A month with no delivery uses the Defra red diesel price."),
            source_ids=tuple(dict.fromkeys(src + (SYNTHETIC_SOURCE, "defra_ukammg"))))),
    }
