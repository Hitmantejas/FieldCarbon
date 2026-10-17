from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from backend.emissions.factors import wtw_factor
from backend.emissions.farm_summary import EF_YEAR, FUEL
from backend.emissions.text import bullets
from backend.fleet.data import action_overlay, actions, jobs, machine_name, operation_name, site_name
from backend.fleet.figures import SYNTHETIC_SOURCE, VINEYARD_SOURCE
from backend.tools.contracts import Figure

MIN_AREA_HA = 0.5  # smaller jobs give wild litres per hectare
MIN_JOBS = 20  # in each of the four groups: changed and other machines, before and after
RESAMPLES = 2000
SEED = 2026
STATUS_TEXT = {
    "reduction_shown": "The changed machines now use less fuel for each hectare, and the other machines do not explain it.",
    "increase_shown": "The changed machines now use more fuel for each hectare, and the other machines do not explain it.",
    "cant_tell_yet": "Can't tell yet. The change may have made no difference: the result could be a small fall or a small rise.",
    "not_enough_jobs": "Too early to tell. There are not enough jobs before and after the change.",
}
CAVEATS = (
    "This change is made up to show how the check works. Your real fuel records are not changed.",
    "The machines were not chosen at random, so this is good evidence, not a trial.",
    "Hectares are estimated from GPS tracks and tool width, so fuel per hectare is not measured directly.",
)
GROUPS = ((True, False), (True, True), (False, False), (False, True))  # (changed, after), in a fixed order


def _job_table(action: pd.Series, overlay: pd.DataFrame) -> pd.DataFrame:
    changed = action.machine_ids.split(";")
    d = jobs()
    d = d[(d.site_id == action.site_id) & (d.area_ha >= MIN_AREA_HA)].copy()
    d["changed"] = d.machine_id.isin(changed)
    d["after"] = d.start_ts >= action.start_date
    with_action = overlay[overlay.action_id == action.name].set_index("job_id").litres_with_action  # this action's own overlay only
    d["litres"] = d.job_id.map(with_action).fillna(d.litres)
    d["lha"] = d.litres / d.area_ha
    typical = d[~d.changed].groupby("operation_code").lha.mean()  # what the other machines use for the same kind of work
    d = d[d.operation_code.isin(typical.index)]
    d["index"] = d.lha / d.operation_code.map(typical)
    return d


def _draws(d: pd.DataFrame) -> dict[tuple[bool, bool], np.ndarray]:
    rng = np.random.default_rng(SEED)
    out = {}
    for key in GROUPS:
        v = d[(d.changed == key[0]) & (d.after == key[1])]["index"].to_numpy()
        out[key] = v[rng.integers(0, len(v), (RESAMPLES, len(v)))].mean(axis=1)
    return out


def _net(means: dict):
    """The changed machines' move minus the other machines' move, as a share. Works on numbers or arrays of draws."""
    return means[(True, True)] / means[(True, False)] / (means[(False, True)] / means[(False, False)]) - 1


def _range_figure(point: float, draws: np.ndarray, how: str) -> Figure:
    low, high = np.percentile(draws, [5, 95])
    return Figure(100 * point, "% change in litres per hectare", "estimated", how,
                  source_ids=(SYNTHETIC_SOURCE, VINEYARD_SOURCE), low=100 * float(low), high=100 * float(high))


def _avoided(d: pd.DataFrame, change: Figure) -> tuple[Figure, Figure]:
    """Litres and tonnes of CO2e the changed machines did not burn after the change, as a range."""
    litres_after = float(d[d.changed & d.after].litres.sum())
    factor = wtw_factor(FUEL, EF_YEAR)

    def saved(pct: float) -> float:
        return -litres_after * (pct / 100) / (1 + pct / 100)
    low, high = saved(change.high), saved(change.low)  # the smallest fall is at the top of the range
    how = bullets(
        f"The changed machines burned **{litres_after:,.0f} litres** on jobs after the change.",
        "Without the change they would have burned more, by the same share as the fall shown above.",
        "The range follows the range of the fall.")
    litres = Figure(saved(change.value), "L", "estimated", how, source_ids=change.source_ids, low=low, high=high)
    tonnes = Figure(saved(change.value) * factor.kg_per_unit / 1000, "t CO2e", "estimated", bullets(
        "Litres avoided x **{:g} kg of CO2** for each litre of red diesel, divided by 1,000.".format(factor.kg_per_unit),
        f"UK government figures for {EF_YEAR} (UK GHG CF {EF_YEAR}), including the CO2 from making and moving the fuel."),
        source_ids=change.source_ids + (factor.source_id,), low=low * factor.kg_per_unit / 1000, high=high * factor.kg_per_unit / 1000)
    return litres, tonnes


def _one(action: pd.Series, overlay: pd.DataFrame) -> dict:
    d = _job_table(action, overlay)
    n = {k: int(((d.changed == k[0]) & (d.after == k[1])).sum()) for k in GROUPS}
    info = {"action_id": action.name, "name": action["name"], "site_id": action.site_id, "site_name": site_name(action.site_id),
            "machines": [machine_name(m) for m in action.machine_ids.split(";")], "intervention_id": action.intervention_id,
            "start_date": str(action.start_date.date()), "what_changed": action.what_changed, "is_illustrative": bool(action.is_synthetic)}
    groups = {"changed_before": n[(True, False)], "changed_after": n[(True, True)],
              "others_before": n[(False, False)], "others_after": n[(False, True)]}
    out = {"action": info, "jobs": groups, "caveats": [*CAVEATS], "change_pct": None, "others_change_pct": None, "changed_change_pct": None,
           "litres_avoided": None, "co2e_avoided_t": None, "operations": sorted(operation_name(o) for o in d.operation_code.unique())}
    if min(n.values()) < MIN_JOBS:
        short = {k: v for k, v in n.items() if v < MIN_JOBS}
        return {**out, "status": "not_enough_jobs", "headline": STATUS_TEXT["not_enough_jobs"],
                "what_would_improve": f"Wait for more jobs. We need at least {MIN_JOBS} jobs in each of the four groups (changed and other machines, before and after). {len(short)} of them have fewer."}

    m = {k: float(d[(d.changed == k[0]) & (d.after == k[1])]["index"].mean()) for k in GROUPS}
    draws = _draws(d)
    net, net_draws = _net(m), _net(draws)
    how = bullets(
        f"**{n[(True, False)]} jobs before** and **{n[(True, True)]} after** on the changed machines; "
        f"**{n[(False, False)]} before** and **{n[(False, True)]} after** on the other machines.",
        "For each job we work out the litres used for each hectare, and compare it with the other machines' average for the same kind of work.",
        "The effect is how much that moved on the changed machines, minus how much it moved on the other machines over the same dates.",
        f"We reshuffled the jobs {RESAMPLES:,} times to see how much the answer moves. **9 in 10** results fall inside the range.")
    change = _range_figure(net, net_draws, how)
    status = "reduction_shown" if change.high < 0 else "increase_shown" if change.low > 0 else "cant_tell_yet"
    out.update(
        status=status, headline=STATUS_TEXT[status], change_pct=asdict(change),
        changed_change_pct=asdict(_range_figure(m[(True, True)] / m[(True, False)] - 1, draws[(True, True)] / draws[(True, False)] - 1,
                                                bullets("Changed machines only: fuel for each hectare after the change, compared with before."))),
        others_change_pct=asdict(_range_figure(m[(False, True)] / m[(False, False)] - 1, draws[(False, True)] / draws[(False, False)] - 1,
                                               bullets("Other machines only: fuel for each hectare after the same date, compared with before. This shows how much fuel use moves anyway, for example with the season."))),
        what_would_improve=("Record more jobs on these tractors after the change. More jobs narrow the range." if status == "cant_tell_yet"
                            else "Keep recording jobs on these tractors. More jobs narrow the range."))
    if status == "reduction_shown":
        litres, tonnes = _avoided(d, change)
        out.update(litres_avoided=asdict(litres), co2e_avoided_t=asdict(tonnes))
    return out


def _proven(results: list[dict]) -> dict:
    shown = [r["co2e_avoided_t"] for r in results if r["co2e_avoided_t"]]
    if not shown:
        return asdict(Figure(0.0, "t CO2e", "measured", bullets(
            "A saving counts as proven only when a change is logged and the result is clear: even the smallest likely saving is above zero.",
            "**No logged change has clearly worked yet.**"), source_ids=(SYNTHETIC_SOURCE,)))
    return asdict(Figure(sum(f["value"] for f in shown), "t CO2e", "estimated", bullets(
        f"**{len(shown)} logged change{'s' if len(shown) > 1 else ''}** clearly worked: even the smallest likely saving is above zero, so the fall is unlikely to be chance.",
        "Each change's avoided tonnes are added: they are different machines on different dates.",
        "This is **illustrative demo data**."),
        source_ids=tuple(dict.fromkeys(s for f in shown for s in f["source_ids"])),
        low=sum(f["low"] for f in shown), high=sum(f["high"] for f in shown)))


def action_impact(action_id: str | None = None) -> dict:
    """Did a logged change work? Before and after on the changed machines, judged against the other machines."""
    log, overlay = actions(), action_overlay()
    if action_id is not None and action_id not in log.index:
        raise ValueError(f"unknown action {action_id!r}; known: {', '.join(log.index)}")
    results = [_one(log.loc[a], overlay) for a in ([action_id] if action_id else log.index)]
    return {"actions": results, "proven_co2e_t": _proven(results),
            "method": "We take how far fuel per hectare moved on the changed machines and subtract how far it moved on the other machines over the same dates."}
