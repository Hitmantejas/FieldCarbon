"""Rank the evidence-table interventions for one farm (core journey step 4).

Deterministic: applicability rules from ref_interventions.csv, then published coefficient ranges
times the farm's own litres. Every saving is an `estimated` range; Gemini only explains the result.
Intervention cost and payback belong to calculate_roi.
"""
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.emissions.factors import wtw_factor
from backend.emissions.farm_summary import EF_YEAR, FUEL, TELEMETRY_SOURCE, TRACTOR_KW, farm_a_rows, fuel_price_range
from backend.tools.contracts import Figure

REF = Path(__file__).resolve().parents[2] / "data" / "reference"

STATUS_ORDER = ("applies", "conditional", "not_applicable")

# Jobs the tractor pulls without driving the implement through the PTO. Shift up / throttle down
# evidence covers drawbar work only. Engineering classification, not a sourced value.
DRAWBAR_OPERATIONS = {"ploughing", "cultivating_deep", "cultivating_shallow", "disc_harrowing",
                      "seedbed_combination", "precision_seeding"}

# Savings that act on the same fuel: never add them up.
OVERLAPS = {
    "reduced_tillage": ("no_till",),
    "no_till": ("reduced_tillage",),
    "correct_tyre_pressure": ("central_tyre_inflation",),
    "central_tyre_inflation": ("correct_tyre_pressure",),
}

# Machine facts we may not know; None in the farm profile means unknown.
FACT_QUESTIONS = {
    "tyre_pressure_checked": "Are tyre pressures set to the manufacturer's figure for each job?",
    "has_ctis": "Do your tractors have central tyre inflation?",
    "ballast_type": "Do your tyres carry liquid ballast?",
}


@dataclass(frozen=True)
class Tractor:
    name: str
    rated_kw: float
    litres: float


@dataclass(frozen=True)
class FarmProfile:
    farm_id: str
    fuel_type: str
    total_litres: float
    # Working fuel per field job (measured); "transport" adds road transport (allocated).
    job_litres: Mapping[str, float]
    # Litres-weighted mean engine load while working, per job.
    working_load_pct: Mapping[str, float]
    # Working fuel per job on the fields that were ploughed (allocated: field boundaries are derived).
    ploughed_field_litres: Mapping[str, float]
    ploughed_fields: int
    tractors: tuple[Tractor, ...]
    facts: Mapping[str, object] = field(default_factory=dict)
    source_ids: tuple[str, ...] = (TELEMETRY_SOURCE,)


@dataclass(frozen=True)
class RankedIntervention:
    rank: int
    intervention_id: str
    name: str
    status: str  # applies | conditional | not_applicable
    reason: str
    litres_saved: Figure | None
    co2e_avoided_kg: Figure | None
    cost_saved_gbp: Figure | None  # None when the price it needs is not sourced yet
    n_sources: int
    source_ids: tuple[str, ...]
    context_source_ids: tuple[str, ...]  # manufacturer claims: shown, not counted in the range
    overlaps_with: tuple[str, ...]
    needs: str | None  # the unknown farm fact this depends on (feeds what_would_improve)
    evidence_status: str
    how: str


@lru_cache(maxsize=1)
def _coefficients() -> pd.DataFrame:
    rows = pd.read_csv(REF / "ref_interventions.csv")
    rows["rules"] = rows.applicability.map(json.loads)
    makers = set(pd.read_csv(REF / "ref_sources.csv").query("is_manufacturer").source_id)
    rows["is_manufacturer"] = rows.source_id.isin(makers)
    return rows


@lru_cache(maxsize=1)
def _categories() -> dict[str, str]:
    return pd.read_csv(REF / "ref_operations.csv").set_index("operation_code").category.to_dict()


def _pct_range(rows: pd.DataFrame) -> tuple[float, float]:
    """Spread across independent studies: the lowest low to the highest high."""
    return float(rows.low.min()) / 100, float(rows.high.max()) / 100


def _eligible_rows(op: str, load: float | None, rows: pd.DataFrame) -> pd.DataFrame:
    rows = rows[rows.rules.map(lambda r: _categories().get(op) in r.get("operation_category", []))
                | rows.rules.map(lambda r: "operation_category" not in r)]
    if rows.empty or not rows.rules.iloc[0].get("load_pct_max"):
        return rows
    if op not in DRAWBAR_OPERATIONS or load is None:
        return rows.iloc[0:0]
    # Use the evidence for the nearest load level at or above this job's mean load.
    caps = rows.rules.map(lambda r: r["load_pct_max"])
    fitting = caps[caps >= load]
    return rows[caps == fitting.min()] if not fitting.empty else rows.iloc[0:0]


def _check(rules: dict, farm: FarmProfile) -> tuple[str, str, str | None]:
    """(status, reason, needs) from the applicability rules."""
    if "fuel_type" in rules and farm.fuel_type not in rules["fuel_type"]:
        return "not_applicable", f"Applies to diesel only; this farm uses {farm.fuel_type}.", None
    op = rules.get("requires_operation")
    if op and farm.job_litres.get(op, 0) <= 0:
        return "not_applicable", f"No {op} recorded, so there is no {op} to replace.", None
    machine = dict(rules.get("machine", {}))
    kw_max = machine.pop("rated_kw_max", None)
    if kw_max is not None and not any(t.rated_kw <= kw_max for t in farm.tractors):
        smallest = min(t.rated_kw for t in farm.tractors)
        return ("not_applicable", f"The evidence covers tractors up to {kw_max:g} kW; the smallest tractor "
                f"here is {smallest:g} kW.", None)
    wanted = dict(machine)
    if "unknown_input" in rules:
        wanted[rules["unknown_input"]] = False  # e.g. tyre pressure not yet checked
    for fact, value in wanted.items():
        known = farm.facts.get(fact)
        if known is None:
            return "conditional", f"Depends on a fact we don't have: {FACT_QUESTIONS.get(fact, fact)}", fact
        if known != value:
            return "not_applicable", f"Already in place: {FACT_QUESTIONS.get(fact, fact)} ({known}).", None
    if op:
        return "applies", f"You plough on {farm.ploughed_fields} fields.", None
    if "fuel_type" in rules:
        return "applies", "Your tractors run on diesel; check with your dealer that each engine is approved for it.", None
    if "load_pct_max" in rules:
        return ("applies", f"Some drawbar jobs run at or below {rules['load_pct_max']}% mean engine load; "
                "the figures list which.", None)
    return "applies", "The conditions in the evidence hold for this farm.", None


def _price_figure(litres_low: float, litres_high: float, sources: tuple[str, ...]) -> Figure:
    p = fuel_price_range()
    return Figure(None, "GBP", "estimated",
                  f"{litres_low:,.0f} to {litres_high:,.0f} L x GBP {p.low:g}-{p.high:g}/L (Defra UKAMMG gas oil, "
                  f"{p.from_month} to {p.to_month})", source_ids=sources + (p.source_id,),
                  low=litres_low * p.low, high=litres_high * p.high)


def _fuel_saving(rows: pd.DataFrame, farm: FarmProfile, rules: dict):
    """Per job: litres x the % range of the evidence rows that cover it. Returns (low, high, jobs)."""
    base = farm.ploughed_field_litres if rules.get("requires_operation") else farm.job_litres
    low = high = 0.0
    jobs = []
    for op, litres in base.items():
        hits = _eligible_rows(op, farm.working_load_pct.get(op), rows)
        if hits.empty or litres <= 0:
            continue
        lo, hi = _pct_range(hits)
        low, high = low + litres * lo, high + litres * hi
        pct = f"{100 * lo:.1f}%" if lo == hi else f"{100 * lo:.1f}-{100 * hi:.1f}%"
        jobs.append(f"{op} {litres:,.0f} L x {pct}")
    return low, high, jobs


def _figures(iid: str, rows: pd.DataFrame, farm: FarmProfile):
    """(litres_saved, co2e_avoided, cost_saved, how) for an intervention that applies or is conditional."""
    rules, effect = rows.rules.iloc[0], rows.effect_type.iloc[0]
    sources = farm.source_ids + tuple(rows.source_id.unique())
    go = wtw_factor(FUEL, EF_YEAR)
    status = f"Coefficients are {rows.value_status.iloc[0].replace('_', ' ')}, not yet checked against the primary source."
    co2_sources = sources + (go.source_id,)

    if effect == "fuel_reduction_pct":
        low, high, jobs = _fuel_saving(rows, farm, rules)
        if not jobs:
            return None
        basis = ("working fuel on ploughed fields (allocated)" if rules.get("requires_operation")
                 else "working fuel per job (measured)")
        if any(j.startswith("transport ") for j in jobs):
            basis += "; transport includes road transport (allocated)"
        how = (f"{'; '.join(jobs)}. Base: {basis}; counts working fuel only, so it is conservative. "
               f"Range spans {rows.source_id.nunique()} source(s). {status}")
        if rules.get("load_pct_max"):
            how += " Uses each job's mean engine load, so part-load time within a job is approximate."
        return (Figure(None, "L", "estimated", how, sources, low, high),
                Figure(None, "kg CO2e", "estimated", f"{low:,.0f} to {high:,.0f} L x {go.kg_per_unit:g} kg CO2e/L "
                       f"(UK GHG CF {EF_YEAR}, well-to-wheel)", co2_sources, low * go.kg_per_unit, high * go.kg_per_unit),
                _price_figure(low, high, sources), how)

    if effect == "litres_change_pct":  # HVO: an emission-factor switch with slightly more litres
        pct = float(rows.value.iloc[0]) / 100
        hvo = wtw_factor("hvo", EF_YEAR)
        litres = farm.total_litres
        avoided = litres * go.kg_per_unit - litres * (1 + pct) * hvo.kg_per_unit
        how = (f"HVO uses {100 * pct:.1f}% more litres: {litres:,.0f} L becomes {litres * (1 + pct):,.0f} L. "
               f"CO2e: {litres:,.0f} L x {go.kg_per_unit:g} minus {litres * (1 + pct):,.0f} L x {hvo.kg_per_unit:g} "
               f"kg CO2e/L (UK GHG CF {EF_YEAR}, well-to-wheel; biogenic CO2 outside scopes). HVO price is not "
               f"sourced yet, so no cost figure. {status}")
        return (Figure(-litres * pct, "L", "estimated", how, sources, -litres * pct, -litres * pct),
                Figure(avoided, "kg CO2e", "estimated", how, co2_sources + (hvo.source_id,), avoided, avoided),
                None, how)

    if effect == "ghg_reduction_pct":  # electric tractor replaces eligible tractors' diesel
        kw_max = rules["machine"]["rated_kw_max"]
        litres = sum(t.litres for t in farm.tractors if t.rated_kw <= kw_max)
        lo, hi = _pct_range(rows)
        kg = litres * go.kg_per_unit
        how = (f"{litres:,.0f} L of diesel on tractors up to {kw_max:g} kW; GHG {100 * lo:.1f}-{100 * hi:.1f}% lower "
               f"including electricity. Electricity price is not sourced yet, so no cost figure. {status}")
        return (Figure(None, "L", "estimated", how, sources, litres, litres),
                Figure(None, "kg CO2e", "estimated", how, co2_sources, kg * lo, kg * hi), None, how)

    raise ValueError(f"unknown effect type {effect} for {iid}")


def _evaluate(iid: str, rows: pd.DataFrame, farm: FarmProfile) -> RankedIntervention:
    counted = rows[~rows.is_manufacturer & (rows.unit != "l_per_ha")]
    context = tuple(rows[rows.is_manufacturer | (rows.unit == "l_per_ha")].source_id.unique())
    status, reason, needs = _check(counted.rules.iloc[0], farm)
    figs = _figures(iid, counted, farm) if status != "not_applicable" else None
    if status != "not_applicable" and figs is None:
        status, reason = "not_applicable", "No job on this farm meets the conditions in the evidence."
    litres, co2e, cost, how = figs or (None, None, None, reason)
    return RankedIntervention(0, iid, rows.intervention_name.iloc[0], status, reason, litres, co2e, cost,
                              int(counted.source_id.nunique()), tuple(counted.source_id.unique()), context,
                              OVERLAPS.get(iid, ()), needs, str(counted.value_status.iloc[0]), how)


def _robustness(r: RankedIntervention) -> tuple:
    """Applies before conditional before not applicable; then the most certain CO2e saving; then more sources."""
    floor = r.co2e_avoided_kg.low if r.co2e_avoided_kg else 0.0
    return STATUS_ORDER.index(r.status), -floor, -r.n_sources


def rank_interventions(farm: FarmProfile) -> list[RankedIntervention]:
    rows = _coefficients()
    out = sorted((_evaluate(iid, g, farm) for iid, g in rows.groupby("intervention_id", sort=False)), key=_robustness)
    return [RankedIntervention(**{**vars(r), "rank": i}) for i, r in enumerate(out, 1)]


def farm_a_profile(facts: Mapping[str, object] | None = None) -> FarmProfile:
    rows = farm_a_rows()
    work = rows[rows.activity_class == "field_work"]
    job = work.groupby("operation_code").litres.sum().to_dict()
    job["transport"] = job.get("transport", 0.0) + float(rows[rows.activity_class == "road_transport"].litres.sum())
    weighted = work.assign(w=work.litres * work.mean_load_pct).groupby("operation_code")[["w", "litres"]].sum()
    ploughed = set(work[(work.operation_code == "ploughing") & work.field_id.notna()].field_id)
    tractors = rows.groupby("tractor_id").litres.sum()
    return FarmProfile(
        farm_id="a", fuel_type=FUEL, total_litres=float(rows.litres.sum()),
        job_litres={k: float(v) for k, v in job.items()},
        working_load_pct=(weighted.w / weighted.litres).dropna().to_dict(),
        ploughed_field_litres=work[work.field_id.isin(ploughed)].groupby("operation_code").litres.sum().to_dict(),
        ploughed_fields=len(ploughed),
        tractors=tuple(Tractor(f"Tractor {t[-1]}, {TRACTOR_KW[t]} kW", TRACTOR_KW[t], float(l))
                       for t, l in tractors.items()),
        facts=dict(facts or {}),
    )
