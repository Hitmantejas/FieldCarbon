import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.emissions.factors import emissions_kg, wtw_factor
from backend.emissions.farm_summary import EF_YEAR
from backend.ranking.context import FarmContext

REF = Path(__file__).resolve().parents[2] / "data" / "reference"

# Effects overlap, so interventions are flagged against each other and never added up.
OVERLAPS = {
    "reduced_tillage": ("no_till",),
    "no_till": ("reduced_tillage",),
    "correct_tyre_pressure": ("central_tyre_inflation", "avoid_liquid_ballast"),
    "central_tyre_inflation": ("correct_tyre_pressure", "avoid_liquid_ballast"),
    "avoid_liquid_ballast": ("correct_tyre_pressure", "central_tyre_inflation"),
}

STATE_ORDER = {"feasible": 0, "needs_info": 1, "not_feasible": 2}
ROBUST_ORDER = {"strong": 0, "moderate": 1, "limited": 2}

# Farmer answers that rule an intervention out when True.
ALREADY_DONE = {"tyre_pressure_checked": "You have already checked your tyre pressure."}


@dataclass(frozen=True)
class Evidence:
    coef_id: str
    source_id: str
    title: str
    url: str  # empty when the source has no usable link yet
    link_status: str
    evidence_type: str
    region: str
    year: int | None
    is_manufacturer: bool
    low: float
    high: float
    unit: str
    baseline: str
    derivation: str
    value_status: str
    used_in_range: bool


@dataclass(frozen=True)
class InterventionResult:
    intervention_id: str
    name: str
    state: str  # feasible | needs_info | not_feasible
    reason: str | None
    missing_inputs: tuple[str, ...]
    litres_saved_low: float | None
    litres_saved_high: float | None
    co2e_avoided_low: float | None
    co2e_avoided_high: float | None
    robustness: str  # strong | moderate | limited
    n_sources: int
    relative_width: float | None
    label: str
    how: str
    overlaps: tuple[str, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class _Row:
    state: str
    reason: str | None = None
    missing: str | None = None
    litres: tuple[float, float] | None = None
    co2e: tuple[float, float] | None = None


@lru_cache(maxsize=1)
def _operations() -> pd.DataFrame:
    return pd.read_csv(REF / "ref_operations.csv").set_index("operation_code")


@lru_cache(maxsize=1)
def _sources() -> pd.DataFrame:
    return pd.read_csv(REF / "ref_sources.csv").set_index("source_id")


@lru_cache(maxsize=1)
def _coefficients() -> pd.DataFrame:
    return pd.read_csv(REF / "ref_interventions.csv")


def _is_manufacturer(source_id: str) -> bool:
    return bool(_sources().loc[source_id, "is_manufacturer"])


def _litres_in(ctx: FarmContext, categories: list[str]) -> float:
    cat = _operations().category
    return sum(l for op, l in ctx.litres_by_op.items() if cat.get(op) in categories)


def _drawbar_litres(ctx: FarmContext, load_max: float) -> float:
    ops = _operations()
    return sum(l for op, l in ctx.litres_by_op.items()
               if ops.drive_type.get(op) == "drawbar" and ctx.mean_load_by_op.get(op, 1e9) <= load_max)


def _apply(ctx: FarmContext, c) -> _Row:
    app = json.loads(c.applicability)
    machine = app.get("machine", {})

    required = app.get("requires_operation")
    if required and ctx.litres_by_op.get(required, 0) <= 0:
        return _Row("not_feasible", f"You did no {required.replace('_', ' ')}, and this idea replaces it.")
    if "fuel_type" in app and ctx.fuel_type not in app["fuel_type"]:
        return _Row("not_feasible", f"This idea is for farms using {' or '.join(app['fuel_type']).replace('_', ' ')}; "
                                        f"yours uses {ctx.fuel_type.replace('_', ' ')}.")

    missing = None
    key = app.get("unknown_input")
    if key:
        answer = ctx.known.get(key)
        if answer is True:
            return _Row("not_feasible", ALREADY_DONE[key])
        missing = key if answer is None else missing
    if "has_ctis" in machine:
        answer = ctx.known.get("has_ctis")
        if answer is True:
            return _Row("not_feasible", "A central tyre inflation system is already fitted.")
        missing = "has_ctis" if answer is None else missing
    if "ballast_type" in machine:
        answer = ctx.known.get("ballast_type")
        if answer is not None and answer != machine["ballast_type"]:
            return _Row("not_feasible", "There is no liquid ballast in the tyres.")
        missing = "ballast_type" if answer is None else missing

    if "rated_kw_max" in machine:
        small = [t for t, kw in ctx.tractor_kw.items() if kw <= machine["rated_kw_max"]]
        if not small:
            return _Row("not_feasible", f"The research only covers small tractors, up to {machine['rated_kw_max']:g} kW. "
                                        f"Your smallest tractor is {min(ctx.tractor_kw.values())} kW, so this does not apply to your farm.")
        base = sum(ctx.litres_by_tractor[t] for t in small)
    elif "load_pct_max" in app:
        base = _drawbar_litres(ctx, app["load_pct_max"])
        if base <= 0:
            return _Row("not_feasible", f"None of your towed jobs (like ploughing) ran at an engine load of "
                                        f"{app['load_pct_max']:g}% or less, so this does not apply to your farm.")
    elif "fuel_type" in app:
        base = ctx.total_litres
    else:
        base = _litres_in(ctx, app["operation_category"])
        if base <= 0:
            return _Row("not_feasible", f"You did no {' or '.join(app['operation_category']).replace('_', ' ')} work.")

    state = "needs_info" if missing else "feasible"
    factor = wtw_factor(ctx.fuel_type, EF_YEAR).kg_per_unit
    if c.effect_type == "fuel_reduction_pct":
        litres = (base * c.low / 100, base * c.high / 100)
        return _Row(state, missing=missing, litres=litres, co2e=(litres[0] * factor, litres[1] * factor))
    if c.effect_type == "litres_change_pct":  # HVO: more litres, far lower emission factor
        old = emissions_kg(base, ctx.fuel_type, EF_YEAR, "estimated").kg_co2e
        new = emissions_kg(base * (1 + c.value / 100), "hvo", EF_YEAR, "estimated").kg_co2e
        return _Row(state, missing=missing, litres=(-base * c.value / 100,) * 2, co2e=(old - new,) * 2)
    if c.effect_type == "ghg_reduction_pct":  # electric tractor: the source states GHG, not litres
        total = emissions_kg(base, ctx.fuel_type, EF_YEAR, "estimated").kg_co2e
        return _Row(state, missing=missing, co2e=(total * c.low / 100, total * c.high / 100))
    raise ValueError(f"unhandled effect type {c.effect_type}")


def _robustness(coefs: pd.DataFrame) -> tuple[str, int]:
    src = _sources()
    independent = {s for s in coefs.source_id if not src.loc[s, "is_manufacturer"] and src.loc[s, "evidence_type"] != "news"}
    n = len(independent)
    return ("strong" if n >= 3 else "moderate" if n == 2 else "limited"), n


def _text(value) -> str:
    return "" if pd.isna(value) else str(value)


def _year(value) -> int | None:
    return None if pd.isna(value) else int(value)


def _evidence(coefs: pd.DataFrame) -> tuple[Evidence, ...]:
    src = _sources()
    return tuple(Evidence(
        coef_id=c.coef_id, source_id=c.source_id, title=src.loc[c.source_id, "title"], url=_text(src.loc[c.source_id, "url"]), link_status=_text(src.loc[c.source_id, "link_status"]),
        evidence_type=src.loc[c.source_id, "evidence_type"], region=_text(src.loc[c.source_id, "region"]),
        year=_year(src.loc[c.source_id, "year"]), is_manufacturer=bool(src.loc[c.source_id, "is_manufacturer"]),
        low=float(c.low), high=float(c.high), unit=c.unit, baseline=c.baseline, derivation=c.derivation,
        value_status=c.value_status, used_in_range=not _is_manufacturer(c.source_id),
    ) for c in coefs.itertuples())


def _width(low: float | None, high: float | None) -> float | None:
    if low is None or high is None or low + high == 0:
        return None
    return (high - low) / ((high + low) / 2)


STRENGTH_TEXT = {
    "strong": "Strong evidence means three or more separate sources back the idea.",
    "moderate": "Moderate evidence means two separate sources back the idea.",
    "limited": "Limited evidence means only one source, or only claims by a maker.",
}


def _how(state: str, reason: str | None, chosen: list[_Row], used, n_sources: int, robustness: str) -> str:
    if state == "not_feasible":
        return reason
    first = used.iloc[0]
    if first.effect_type == "litres_change_pct":
        return (f"HVO is a diesel made from waste oils. Engines burn about {first.value:g}% more of it, but each litre "
                f"releases far less CO2. We worked out the CO2 from UK government figures for {EF_YEAR}, not from a "
                "study's percentage.")
    lows = [r.litres[0] for r in chosen if r.litres]
    highs = [r.litres[1] for r in chosen if r.litres]
    if lows:
        what = f"{min(lows):,.0f} to {max(highs):,.0f} litres of fuel a year"
    else:
        what = f"{min(r.co2e[0] for r in chosen) / 1000:.1f} to {max(r.co2e[1] for r in chosen) / 1000:.1f} tonnes of CO2 a year"
    text = (f"Researchers measured the fuel this idea saves. We applied their lowest and highest results to the fuel "
            f"your farm used on the matching work. That gives {what}. {n_sources} separate "
            f"{'source was' if n_sources == 1 else 'sources were'} used. {STRENGTH_TEXT[robustness]}")
    if state == "needs_info":
        text += " It only applies if the answer to our question fits your farm."
    return text


def _evaluate_one(ctx: FarmContext, intervention_id: str, coefs: pd.DataFrame) -> InterventionResult:
    # Manufacturer claims are shown as evidence but never set the range (CLAUDE.md section 6).
    used = coefs[[not _is_manufacturer(s) for s in coefs.source_id]]
    rows = [_apply(ctx, c) for c in used.itertuples()]
    feasible = [r for r in rows if r.state == "feasible"]
    needs = [r for r in rows if r.state == "needs_info"]
    chosen, state = (feasible, "feasible") if feasible else (needs, "needs_info") if needs else ([], "not_feasible")
    reason = rows[0].reason if state == "not_feasible" else None

    litres = [r.litres for r in chosen if r.litres]
    co2e = [r.co2e for r in chosen if r.co2e]
    litres_low = min(l[0] for l in litres) if litres else None
    litres_high = max(l[1] for l in litres) if litres else None
    co2e_low = min(c[0] for c in co2e) if co2e else None
    co2e_high = max(c[1] for c in co2e) if co2e else None
    robustness, n_sources = _robustness(coefs)
    width = _width(litres_low, litres_high) if litres else _width(co2e_low, co2e_high)

    return InterventionResult(
        intervention_id=intervention_id, name=coefs.intervention_name.iloc[0], state=state, reason=reason,
        missing_inputs=tuple(dict.fromkeys(r.missing for r in chosen if r.missing)) if state == "needs_info" else (),
        litres_saved_low=litres_low, litres_saved_high=litres_high, co2e_avoided_low=co2e_low, co2e_avoided_high=co2e_high,
        robustness=robustness, n_sources=n_sources, relative_width=width, label="estimated",
        how=_how(state, reason, chosen, used, n_sources, robustness),
        overlaps=OVERLAPS.get(intervention_id, ()), evidence=_evidence(coefs),
    )


def evaluate(ctx: FarmContext) -> list[InterventionResult]:
    return [_evaluate_one(ctx, iv, g) for iv, g in _coefficients().groupby("intervention_id", sort=False)]


def rank_interventions(ctx: FarmContext) -> list[InterventionResult]:
    return sorted(evaluate(ctx), key=lambda r: (
        STATE_ORDER[r.state], ROBUST_ORDER[r.robustness], 1e9 if r.relative_width is None else r.relative_width, r.name))


def required_operation(intervention_id: str) -> str | None:
    rows = _coefficients()
    first = rows[rows.intervention_id == intervention_id].applicability.iloc[0]
    return json.loads(first).get("requires_operation")
