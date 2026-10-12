"""Tier 3: a farm seen through fuel receipts and a farm profile only (Farm B).

- Total litres: receipt lines accepted by the validation rules (measured: metered quantities on
  documents; assumes the fuel bought this season was used this season).
- Split by operation: worked area x the Iowa A3-27 fuel-use range (estimated).
- Remainder: total minus the field estimate = travel, idling and implement not working (estimated).
No telemetry is used, so the comparison with Farm A (evals/range_coverage.py) is a genuine test.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.emissions.factors import emissions_kg
from backend.emissions.farm_summary import EF_YEAR, FUEL, BreakdownRow, Summary, co2e_lines, display_name
from backend.emissions.pain_points import reference_range
from backend.emissions.text import bullets
from backend.tools.contracts import Figure

ROOT = Path(__file__).resolve().parents[2]
FARM_B = ROOT / "data" / "synthetic" / "farm_b"
RECEIPTS_SOURCE = "farm_b_receipts"
PROFILE_SOURCE = "farm_b_profile"
REMAINDER_KEY = "travel_idle_nonworking"
REMAINDER_NAME = "Travel, idling and implement not working"


@dataclass(frozen=True)
class ReceiptTotals:
    litres: float
    net_gbp: float      # money paid for the counted fuel lines, before VAT
    documents: int
    review_litres: float
    data_source: str


@dataclass(frozen=True)
class OperationEstimate:
    operation_code: str
    area_ha: float
    low: float
    typical: float
    high: float
    source_ids: tuple[str, ...]


@lru_cache(maxsize=1)
def receipt_totals() -> ReceiptTotals:
    """Validated Gemini readings once every receipt has one; until then the receipts' ground truth."""
    from backend.tools.extract_receipt import cache_path, validate_farm

    ids = sorted(p.stem for p in (FARM_B / "receipts").glob("*.jpg"))
    if ids and all(cache_path("b", rid).exists() for rid in ids):
        validated = validate_farm("b")
        lines = [l for l in validated if l.counts and l.litres]
        review = sum(l.litres for l in validated if l.outcome == "needs_review" and l.litres)
        return ReceiptTotals(round(sum(l.litres for l in lines), 2),
                             round(sum(l.line_net_gbp or 0.0 for l in lines), 2),
                             len({l.receipt_id for l in lines}), round(review, 2),
                             "Gemini receipt readings, checked by validation rules R1-R8")
    gt = pd.read_csv(FARM_B / "ground_truth_lines.csv")
    counted = gt[gt.counts_toward_fuel]
    return ReceiptTotals(round(float(counted.litres.sum()), 2), round(float(counted.net_gbp.sum()), 2),
                         int(counted.doc_id.nunique()), 0.0,
                         "receipt ground truth (Gemini reading pending the Vertex AI endpoint decision)")


@lru_cache(maxsize=1)
def profile() -> pd.DataFrame:
    return pd.read_csv(FARM_B / "farm_b_profile.csv")


def operation_estimates(prof: pd.DataFrame | None = None) -> list[OperationEstimate]:
    """Worked area x published L/ha range per operation; operations without a published rate are skipped
    (their fuel stays in the remainder)."""
    prof = profile() if prof is None else prof
    out = []
    for op, area in prof.groupby("operation_code").area_ha.sum().items():
        ref = reference_range(op)
        if ref is None:
            continue
        out.append(OperationEstimate(op, float(area), area * ref.low, area * ref.typical, area * ref.high,
                                     (PROFILE_SOURCE, *ref.source_ids)))
    return sorted(out, key=lambda e: -e.typical)


def summarise(t: ReceiptTotals | None = None) -> Summary:
    t = t or receipt_totals()
    e = emissions_kg(t.litres, FUEL, EF_YEAR, "measured")
    litres = Figure(t.litres, "L", "measured", bullets(
        f"Added up from **{t.documents} fuel receipts**, read and checked by fixed rules.",
        "Lines that are not fuel, and the same receipt photographed twice, are **left out**.",
        "We assume the fuel bought this season was used this season (tank level the same at start and end).",
    ), source_ids=(RECEIPTS_SOURCE,))
    co2e = Figure(e.kg_co2e, "kg CO2e", "measured", bullets(*co2e_lines(t.litres, e.factor.kg_per_unit, EF_YEAR)),
                  source_ids=(RECEIPTS_SOURCE, e.factor.source_id))
    cost = Figure(t.net_gbp, "GBP", "measured", bullets(
        "**What you paid**, added up from the receipts, before VAT.",
        "Only the fuel lines count; AdBlue and duplicates are left out.",
    ), source_ids=(RECEIPTS_SOURCE,), low=t.net_gbp, high=t.net_gbp)
    return Summary(litres, co2e, cost, None)


def _figures(low: float, typical: float, high: float, how: str, sources: tuple[str, ...],
             price: float) -> tuple[Figure, Figure, Figure]:
    kg = emissions_kg(1.0, FUEL, EF_YEAR, "estimated").factor
    return (
        Figure(typical, "L", "estimated", how, sources, low, high),
        Figure(typical * kg.kg_per_unit, "kg CO2e", "estimated",
               bullets(f"**{low:,.0f} to {high:,.0f} litres** x **{kg.kg_per_unit:g} kg of CO2** per litre.",
                       f"UK government figures for {EF_YEAR}, including making and moving the fuel."),
               sources + (kg.source_id,), low * kg.kg_per_unit, high * kg.kg_per_unit),
        Figure(typical * price, "GBP", "estimated",
               bullets(f"**{low:,.0f} to {high:,.0f} litres** x **£{price:.3f} a litre**, "
                       "the average you paid on your receipts (before VAT)."),
               sources + (RECEIPTS_SOURCE,), low * price, high * price),
    )


def breakdown_by_operation(t: ReceiptTotals | None = None,
                           estimates: list[OperationEstimate] | None = None) -> list[BreakdownRow]:
    t = t or receipt_totals()
    estimates = operation_estimates() if estimates is None else estimates
    price = t.net_gbp / t.litres
    rows = []
    for e in estimates:
        how = bullets(f"You worked **{e.area_ha:,.1f} hectares** with this job (your farm profile).",
                      f"Published fuel use for this job: **{e.low / e.area_ha:.1f} to {e.high / e.area_ha:.1f} "
                      "litres a hectare** (Iowa State A3-27).",
                      "Your receipts do not say which job used the fuel, so this is **estimated**.")
        litres, co2e, cost = _figures(e.low, e.typical, e.high, how, e.source_ids, price)
        rows.append(BreakdownRow(e.operation_code, display_name("operation", e.operation_code), litres, co2e, cost,
                                 None, 100 * e.typical / t.litres))
    sums = [sum(getattr(e, k) for e in estimates) for k in ("low", "typical", "high")]
    # The remainder is widest when the field jobs are at their lowest, and never below zero.
    low, typical, high = (max(t.litres - s, 0.0) for s in (sums[2], sums[1], sums[0]))
    how = bullets(f"Your receipts add up to **{t.litres:,.0f} litres**.",
                  f"The field jobs above account for **{sums[0]:,.0f} to {sums[2]:,.0f} litres**.",
                  "The rest went on **travel between fields, idling and time with the implement not working**.",
                  "Published rates leave these out, so this is the **remainder**, estimated.")
    litres, co2e, cost = _figures(low, typical, high, how, (RECEIPTS_SOURCE, PROFILE_SOURCE, "isu_a3_27"), price)
    rows.append(BreakdownRow(REMAINDER_KEY, REMAINDER_NAME, litres, co2e, cost, None, 100 * typical / t.litres))
    return sorted(rows, key=lambda r: -r.litres.value)
