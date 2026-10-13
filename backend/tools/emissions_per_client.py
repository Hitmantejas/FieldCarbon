from __future__ import annotations

from backend.emissions.text import bullets
from backend.fleet import data
from backend.fleet.figures import slice_figures
from backend.tools.fleet_summary import _filtered, fleet_summary


def _unassigned() -> tuple:
    """Fuel with no client, split in two: outside any job (company overhead) and jobs whose field was not matched."""
    df = _filtered(None, None, data.UNASSIGNED, None, None, None)
    return df[~df.is_job], df[df.is_job]


def emissions_per_client(client_id: str | None = None) -> dict:
    """Litres, CO2e and cost per client farm, plus the fuel that belongs to no client, so the parts add up to the fleet total."""
    summary = fleet_summary("client", client_id=client_id)
    out = {"rows": [{**r, "client_id": r["key"]} for r in summary["rows"] if r["key"] != data.UNASSIGNED],
           "months": [], "overhead": None, "unmatched_jobs": None, "total": summary["totals"]["litres"] if summary["totals"] else None}
    if client_id:
        df = _filtered(None, None, client_id, None, None, None)
        for month, g in df.groupby("month", sort=True):
            f = slice_figures(g, synthetic_cols=True)
            out["months"].append({"client_id": client_id, "client": data.client_name(client_id), "month": month,
                                  "litres": f["litres"], "co2e_kg": f["co2e_kg"]})
        return out

    overhead, unmatched = _unassigned()
    figs = slice_figures(overhead, synthetic_cols=True)
    figs["litres"]["how"] = bullets(
        f"**{overhead.litres.sum():,.0f} litres** were burned between and around jobs: travel, idling and tools attached but not working.",
        "No field is worked in that time, so the fuel belongs to the company, not to a client.",
        "The total is measured. Splitting it into these uses is done **by rule**, so it is **allocated**.")
    out["overhead"] = {**figs, "hours": float(overhead.hours.sum()), "breakdown": [
        {"key": code, "name": data.operation_name(code), "litres": slice_figures(g, synthetic_cols=True)["litres"]}
        for code, g in sorted(overhead.groupby("operation_code"), key=lambda kv: -kv[1].litres.sum())]}
    if len(unmatched):
        f = slice_figures(unmatched, synthetic_cols=True)
        f["litres"]["how"] = bullets(
            f"**{unmatched.litres.sum():,.0f} litres** were burned on **{len(unmatched)} jobs** whose GPS position fell outside every known field.",
            "We cannot say whose field it was, so these jobs are in no client's figures.")
        out["unmatched_jobs"] = {**f, "jobs": len(unmatched), "area_ha": float(unmatched.area_ha.sum())}
    return out
