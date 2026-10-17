"""One client farm's carbon statement: the facts only, no model (F4).

The totals are the same figures as emissions_per_client and the client report. Per hectare and per job are divided here,
in code, never in a prompt. The Gemini summary is added by the API (backend/api/fleet.py), so the agent can call this
tool freely and its tests need no stub.
"""
from __future__ import annotations

from dataclasses import asdict

from backend.emissions.factors import wtw_factor
from backend.emissions.farm_summary import EF_YEAR, FUEL
from backend.emissions.text import bullets
from backend.fleet import data
from backend.fleet.figures import SYNTHETIC_SOURCE, slice_figures
from backend.tools.contracts import Figure, weakest
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_summary import _filtered, fleet_summary

MAX_OPERATIONS = 5
LIMITS = [
    "Fuel burned between jobs (travel, idling, a tool attached but not working) is company overhead, reported separately, "
    "and is not in this statement.",
    "Which field a job was on comes from matching GPS positions to field outlines, so per-field and per-hectare figures are allocated.",
    "Dates, clients and operators in this demo are synthetic.",
]


def _by_operation(client_id: str, df, total: float) -> list[dict]:
    """The client's largest operations by litres; past five, the smallest are one 'Other work' row so shares make 100."""
    codes = [r["key"] for r in fleet_summary("operation", client_id=client_id)["rows"]]
    shown = codes if len(codes) <= MAX_OPERATIONS else codes[:MAX_OPERATIONS - 1]
    parts = [(data.operation_name(c), c, df[df.operation_code == c]) for c in shown]
    if len(codes) > len(shown):
        parts.append(("Other work", None, df[df.operation_code.isin(codes[len(shown):])]))
    out = []
    for name, code, g in parts:
        f = slice_figures(g, synthetic_cols=True)  # cut by client, a synthetic column
        out.append({"operation": name, "operation_code": code, "litres": f["litres"], "co2e_kg": f["co2e_kg"],
                    "share_pct": 100 * float(g.litres.sum()) / total if total else 0.0})
    return out


def client_statement(client_id: str) -> dict:
    """Totals, per hectare, per job, the largest operations, the months covered and the limits for one client farm."""
    if client_id not in data.clients().index:
        raise ValueError(f"unknown client {client_id}")
    name = data.client_name(client_id)
    rows = emissions_per_client(client_id)["rows"]
    if not rows:
        raise ValueError(f"{name} has no jobs in the company year")
    row = rows[0]
    df = _filtered(None, None, client_id, None, None, None)
    jobs = data.jobs()[lambda d: d.client_id == client_id]
    with_area = jobs[jobs.area_ha.notna()]
    missing = len(jobs) - len(with_area)
    co2e = row["co2e_kg"]
    factor = wtw_factor(FUEL, EF_YEAR)

    area_sources = tuple(dict.fromkeys(list(with_area.source_id) + [SYNTHETIC_SOURCE]))
    area = float(with_area.area_ha.sum())
    area_fig = asdict(Figure(area, "ha", "allocated", bullets(
        f"**{area:,.1f} hectares** worked in **{len(with_area)} jobs**: the sum of each job's area.",
        "A job's area comes from its GPS track and the tool's working width, and which field it was on from matching GPS "
        "positions to field outlines, so it is **allocated**.",
        *([f"**{missing} jobs** have no recorded area and are not counted."] if missing else [])), source_ids=area_sources))

    per_ha = per_job = None
    if area:
        kg = float(with_area.litres.sum()) * factor.kg_per_unit
        per_ha = asdict(Figure(kg / area, "kg CO2e/ha", weakest([co2e["label"], "allocated"]), bullets(
            f"**{kg:,.0f} kg CO2e** from the jobs with an area, divided by **{area:,.1f} hectares**.",
            "The area is **allocated**, so this figure is too.",
            *([f"The fuel of **{missing} jobs** with no recorded area is left out, so it is not spread over too few hectares."]
              if missing else [])), source_ids=tuple(dict.fromkeys(tuple(co2e["source_ids"]) + area_sources))))
    if row["jobs"]:
        per_job = asdict(Figure(co2e["value"] / row["jobs"], "kg CO2e", co2e["label"], bullets(
            f"**{co2e['value']:,.0f} kg CO2e** divided by **{row['jobs']} jobs**."), source_ids=tuple(co2e["source_ids"])))

    return {
        "client_id": client_id, "client_name": name, "demo_data": True,
        "period": {"from": df.month.min(), "to": df.month.max()},
        "totals": {"litres": row["litres"], "co2e_kg": co2e, "cost_gbp": row["cost_gbp"]},
        "area_ha": area_fig, "co2e_per_ha": per_ha, "co2e_per_job": per_job,
        "jobs": row["jobs"], "jobs_without_area": missing, "hours": row["hours"],
        "by_operation": _by_operation(client_id, df, float(df.litres.sum())),
        "limits": LIMITS,
    }
