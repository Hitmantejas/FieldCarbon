from __future__ import annotations

from dataclasses import asdict

from backend.emissions.text import bullets
from backend.fleet import data
from backend.tools.contracts import Figure

CAVEAT = ("Machines can differ in slope, soil, field and tool, so a difference here is something to investigate, "
          "not proof that fuel was lost.")


def _fig(value, unit, how, source, low=None, high=None) -> dict:
    return asdict(Figure(value, unit, "allocated", how, source_ids=(source,), low=low, high=high))


def benchmark_peers(site_id: str | None = None, operation_code: str | None = None, min_machines: int = 3,
                    min_jobs: int = 3, flag_pct: float = 25.0) -> dict:
    """Same job, same site: litres per hectare for each machine against its peers' middle value.

    The fuel at stake is a range: down to the peers' upper quarter at the low end, to their middle value at the high end.
    """
    jobs = data.jobs()
    jobs = jobs[(jobs.area_ha > 0) & (jobs.hours > 0.2)]
    if site_id:
        jobs = jobs[jobs.site_id == site_id]
    if operation_code:
        jobs = jobs[jobs.operation_code == operation_code]

    groups, skipped = [], []
    for (site, op), g in jobs.groupby(["site_id", "operation_code"], sort=True):
        per = g.groupby("machine_id").agg(jobs=("job_id", "count"), litres=("litres", "sum"), hours=("hours", "sum"),
                                          area=("area_ha", "sum"))
        per = per[per.jobs >= min_jobs]
        if len(per) < min_machines:
            skipped.append({"site_id": site, "operation_code": op, "operation": data.operation_name(op),
                            "reason": f"Only {len(per)} machine(s) did enough of this job to compare."})
            continue
        source = data.sites().source_id[site]
        per["lph"] = per.litres / per.area
        median, upper = float(per.lph.median()), float(per.lph.quantile(0.75))
        peers, stake_lo, stake_hi = [], 0.0, 0.0
        for machine, r in per.sort_values("lph", ascending=False).iterrows():
            diff = 100 * (r.lph / median - 1)
            above = diff >= flag_pct
            name = data.machine_name(machine)
            stake = None
            if above:
                lo, hi = max(0.0, (r.lph - upper) * r.area), (r.lph - median) * r.area
                stake_lo, stake_hi = stake_lo + lo, stake_hi + hi
                stake = _fig(None, "L per year", bullets(
                    f"{name} burned **{r.lph:.1f} litres per hectare** doing {data.operation_name(op).lower()}.",
                    f"Other machines doing this job at {data.site_name(site)} usually burn **{median:.1f}**, so this one burned **{diff:.0f}% more**.",
                    f"If it burned what the typical machine does, it would use about **{hi:,.0f} litres less**. If it only came down to where the "
                    f"thirstier quarter of machines sits, about **{lo:,.0f} litres less**.",
                    "Next step: compare these jobs with the others in the job notes: the tool, the field and the way it was driven. "
                    "If nothing explains the gap, look again next month.",
                    "The area is worked out from speed and tool width, so this is **allocated**."), source, lo, hi)
            peers.append({
                "machine_id": machine, "machine": name, "jobs": int(r.jobs), "hectares": float(r.area), "litres": float(r.litres),
                "l_per_ha": _fig(float(r.lph), "L/ha", bullets(
                    f"**{r.litres:,.0f} litres** over **{r.area:,.1f} hectares** in **{int(r.jobs)} jobs**.",
                    "Litres are measured; the area is worked out from speed and tool width, so it is **allocated**."), source),
                "difference_pct": float(diff), "above_peers": bool(above), "litres_at_stake": stake})
        groups.append({
            "site_id": site, "site": data.site_name(site), "operation_code": op, "operation": data.operation_name(op),
            "median_l_per_ha": _fig(median, "L/ha", bullets(
                f"The middle value of **{len(per)} machines** doing this job at {data.site_name(site)}."), source),
            "peers": peers, "caveat": CAVEAT,
            "litres_at_stake": _fig(None, "L per year", bullets(
                f"Machines above their peers could save **{stake_lo:,.0f} to {stake_hi:,.0f} litres** in this job."), source, stake_lo, stake_hi)
            if stake_hi > 0 else None})
    groups.sort(key=lambda g: -(g["litres_at_stake"]["high"] if g["litres_at_stake"] else 0))
    return {"groups": groups, "skipped": skipped, "settings": {"min_machines": min_machines, "min_jobs": min_jobs, "flag_pct": flag_pct}}
