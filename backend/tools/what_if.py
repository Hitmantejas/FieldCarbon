from __future__ import annotations

from dataclasses import asdict

from backend.emissions.factors import emissions_kg
from backend.emissions.farm_summary import EF_YEAR, FUEL
from backend.emissions.text import bullets
from backend.fleet import data
from backend.ranking.interventions import _coefficients
from backend.ranking.roi import _cost_for
from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.contracts import Figure

CHANGES = ("implement_not_working", "peer_outliers", "hvo")
NOT_WORKING = "other_implement_nonproductive"


def _fig(unit: str, how: str, sources: tuple[str, ...], value=None, low=None, high=None) -> dict:
    return asdict(Figure(value, unit, "estimated", how, source_ids=tuple(dict.fromkeys(sources)), low=low, high=high))


def _result(title: str, assumption: str, litres: dict, co2e: dict, cost: dict) -> dict:
    return {"available": True, "is_scenario": True, "scenario": title, "assumption": assumption,
            "litres_saved": litres, "co2e_avoided_kg": co2e, "cost_saved_gbp": cost}


def what_if(change: str, amount_pct: float, site_id: str | None = None) -> dict:
    """A scenario with an assumption you set. It is arithmetic on measured fuel, not a prediction."""
    if change not in CHANGES:
        raise ValueError(f"unknown scenario {change}")
    if not 0 < amount_pct <= 100:
        raise ValueError("amount must be above 0 and at most 100 percent")
    share = amount_pct / 100
    ledger = data.ledger()
    scope = ledger[ledger.site_id == site_id] if site_id else ledger
    factor = emissions_kg(1.0, FUEL, EF_YEAR, "estimated").factor
    price = data.price_by_month()
    sources = tuple(dict.fromkeys(scope.source_id)) + ("fleet_synthetic", factor.source_id, "defra_ukammg")

    if change == "implement_not_working":
        rows = scope[scope.operation_code == NOT_WORKING]
        if rows.empty:
            return {"available": False, "is_scenario": True, "reason":
                    "Only the arable site records fuel burned with the tool attached but not working."}
        base = float(rows.litres.sum())
        saved = share * base
        money = share * float((rows.litres * rows.month.map(price)).sum())
        how = lambda x: bullets(f"The fleet burned **{base:,.0f} litres** with a tool attached but not working.", x)
        return _result(
            "Cut the fuel burned with the tool attached but not working",
            f"Assumption: you cut that fuel by {amount_pct:g}%. No research says how easy that is.",
            _fig("L per year", how(f"We assume you cut it by **{amount_pct:g}%**: **{saved:,.0f} litres**."), sources, saved),
            _fig("kg CO2e per year", bullets(f"**{saved:,.0f} litres** x **{factor.kg_per_unit:g} kg of CO2** for each litre.",
                                             f"UK government figures for {EF_YEAR}."), sources, saved * factor.kg_per_unit),
            _fig("GBP per year", bullets(f"**{saved:,.0f} litres** saved, priced at the invoice price for the months they were burned."), sources, money))

    if change == "peer_outliers":
        flagged = [p for g in benchmark_peers(site_id=site_id)["groups"] for p in g["peers"] if p["above_peers"]]
        lo = share * sum(p["litres_at_stake"]["low"] for p in flagged)
        hi = share * sum(p["litres_at_stake"]["high"] for p in flagged)
        avg = float((scope.litres * scope.month.map(price)).sum() / scope.litres.sum())
        return _result(
            "Bring the machines that burn more than their peers to the peers' middle value",
            f"Assumption: you close {amount_pct:g}% of the gap between each flagged machine and its peers.",
            _fig("L per year", bullets(f"**{len(flagged)} machine-and-job groups** burned more per hectare than their peers.",
                                       f"Closing {amount_pct:g}% of the gap would save **{lo:,.0f} to {hi:,.0f} litres**."), sources, None, lo, hi),
            _fig("kg CO2e per year", bullets(f"**{lo:,.0f} to {hi:,.0f} litres** x **{factor.kg_per_unit:g} kg of CO2** for each litre."),
                 sources, None, lo * factor.kg_per_unit, hi * factor.kg_per_unit),
            _fig("GBP per year", bullets(f"The litres saved, priced at the fleet's average **£{avg:.3f} a litre**."), sources, None, lo * avg, hi * avg))

    # HVO: more litres burned, far less CO2 per litre (emission factors, not a study's percentage).
    total = float(scope.litres.sum())
    extra_pct = float(_coefficients().set_index("coef_id").value["hvo_sondors"])
    moved = share * total
    extra = moved * extra_pct / 100
    old = emissions_kg(moved, FUEL, EF_YEAR, "estimated").kg_co2e
    new = emissions_kg(moved + extra, "hvo", EF_YEAR, "estimated").kg_co2e
    cost = _cost_for("hvo_switch")
    avg = float((scope.litres * scope.month.map(price)).sum() / scope.litres.sum())
    extra_cost_lo, extra_cost_hi = extra * avg + (moved + extra) * cost.low, extra * avg + (moved + extra) * cost.high
    hvo_sources = sources + ("sondors2014",) + cost.source_ids
    return _result(
        "Switch part of the fuel to HVO",
        f"Assumption: {amount_pct:g}% of the fleet's fuel is replaced by HVO, a diesel made from waste oils.",
        _fig("L per year", bullets(f"**{moved:,.0f} litres** would be replaced by HVO.",
                                   f"Engines burn about **{extra_pct:g}% more** of it: **{extra:,.0f} extra litres** a year."), hvo_sources, -extra),
        _fig("kg CO2e per year", bullets("We worked out the CO2 of the diesel now and of the HVO instead, using UK government figures "
                                         f"for {EF_YEAR}.", f"The difference is **{old - new:,.0f} kg** a year."), hvo_sources, old - new),
        _fig("GBP per year", bullets(f"You burn **{extra:,.0f} more litres** and every litre of HVO costs **{cost.low * 100:.0f}p to {cost.high * 100:.0f}p more**.",
                                     "We only have a rough price for HVO: ask a fuel supplier for a quote."), hvo_sources,
             None, -extra_cost_hi, -extra_cost_lo))
