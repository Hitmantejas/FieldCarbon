"""Where farm figures come from: the BigQuery calculated views (the app) or the committed CSV
aggregates (tests, offline work). Both paths return the same contract types.

FIELDCARBON_DATA=bigquery|csv selects the source (default csv, so tests never need GCP).
In bigquery mode, litres x emission factor is computed by the views in
backend/emissions/views/020_emissions_views.sql; Python only maps rows to Figures.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from backend.emissions.farm_summary import (EXCLUDED_CLASS, TELEMETRY_SOURCE, BreakdownRow, Summary, breakdown,
                                            display_name, farm_a_rows, summarise)
from backend.tools.contracts import Figure

PROJECT = os.environ.get("FIELDCARBON_PROJECT", "ai-hackathon-india")
DATASET = os.environ.get("FIELDCARBON_DATASET", "fieldcarbon")
LOCATION = "us-central1"
SOURCES = ("csv", "bigquery")
BREAKDOWN_VIEWS = {
    "operation": "v_farm_a_emissions_by_operation",
    "tractor": "v_farm_a_emissions_by_tractor",
    "field": "v_farm_a_emissions_by_field",
}

Query = Callable[[str], list[dict]]


@dataclass(frozen=True)
class FarmTotals:
    summary: Summary
    excluded_hours: float  # frozen logger stretches: reported, never counted
    data_source: str       # shown in the API provenance so the UI can say where numbers came from


def source() -> str:
    chosen = os.environ.get("FIELDCARBON_DATA", "csv")
    if chosen not in SOURCES:
        raise ValueError(f"FIELDCARBON_DATA must be one of {SOURCES}, got {chosen!r}")
    return chosen


def bigquery_query(sql: str) -> list[dict]:
    from google.cloud import bigquery  # imported lazily: CSV mode and tests need no GCP library

    client = bigquery.Client(project=PROJECT, location=LOCATION)
    return [dict(row.items()) for row in client.query(sql).result()]


def _view(name: str) -> str:
    return f"`{PROJECT}.{DATASET}.{name}`"


# ----------------------------------------------------------------------------------------- csv path

def _csv_totals() -> FarmTotals:
    rows = farm_a_rows()
    excluded = float(rows[rows.activity_class == EXCLUDED_CLASS].hours.sum())
    return FarmTotals(summarise(rows), excluded, "committed CSV aggregates (data/aggregated)")


# ------------------------------------------------------------------------------------ bigquery path

@lru_cache(maxsize=4)
def _settings(query: Query) -> dict:
    rows = query(f"SELECT * FROM {_view('v_farm_a_settings')}")
    if len(rows) != 1:
        raise RuntimeError(f"v_farm_a_settings returned {len(rows)} rows, expected 1")
    return rows[0]


def _bq_figures(row: dict, label: str, litres_how: str, view: str, s: dict) -> tuple[Figure, Figure, Figure]:
    litres = float(row["litres"])
    return (
        Figure(litres, "L", label, litres_how, source_ids=(TELEMETRY_SOURCE,)),
        Figure(float(row["co2e_kg"]), "kg CO2e", label,
               f"{litres:g} L x {s['kgco2e_per_l']:g} kg CO2e/L (UK GHG CF {s['ef_year']}, well-to-wheel), "
               f"computed in BigQuery view {view}",
               source_ids=(TELEMETRY_SOURCE, s["ef_source_id"])),
        Figure(None, "GBP", "estimated",
               f"{litres:g} L x GBP {s['price_low']:g}-{s['price_high']:g}/L (Defra UKAMMG gas oil, "
               f"{s['from_month']} to {s['to_month']}; TUM dates are anonymised, so a price range is used; "
               f"VAT basis not stated), computed in BigQuery view {view}",
               source_ids=(TELEMETRY_SOURCE, s["price_source_id"]),
               low=float(row["cost_gbp_low"]), high=float(row["cost_gbp_high"])),
    )


@lru_cache(maxsize=4)
def _bq_totals(query: Query) -> FarmTotals:
    rows = query(f"SELECT * FROM {_view('v_farm_a_summary')}")
    if len(rows) != 1:
        raise RuntimeError(f"v_farm_a_summary returned {len(rows)} rows, expected 1")
    r = rows[0]
    litres, co2e, cost = _bq_figures(
        r, r["label"], "Engine fuel-rate (J1939) integrated over time, TUM Agricultural Load Cycles",
        "v_farm_a_summary", _settings(query))
    return FarmTotals(Summary(litres, co2e, cost, float(r["hours"])), float(r["excluded_hours"]),
                      f"BigQuery calculated views ({PROJECT}.{DATASET})")


@lru_cache(maxsize=12)
def _bq_breakdown(by: str, query: Query) -> tuple[BreakdownRow, ...]:
    view = BREAKDOWN_VIEWS[by]
    s = _settings(query)
    out = []
    for r in query(f"SELECT * FROM {_view(view)}"):
        litres, co2e, cost = _bq_figures(r, r["label"], f"Measured telemetry litres attributed by {by} "
                                         f"({r['label']})", view, s)
        out.append(BreakdownRow(r["key"], display_name(by, r["key"]), litres, co2e, cost, float(r["hours"]),
                                float(r["share_pct"])))
    return tuple(sorted(out, key=lambda b: -b.litres.value))


# ------------------------------------------------------------------------------------------- public

def farm_a_totals(src: str | None = None, query: Query = bigquery_query) -> FarmTotals:
    return _bq_totals(query) if (src or source()) == "bigquery" else _csv_totals()


def farm_a_breakdown(by: str, src: str | None = None, query: Query = bigquery_query) -> list[BreakdownRow]:
    if by not in BREAKDOWN_VIEWS:
        raise ValueError(f"cannot group by {by}")
    if (src or source()) == "bigquery":
        return list(_bq_breakdown(by, query))
    return breakdown(farm_a_rows(), by)
