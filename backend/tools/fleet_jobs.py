from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from backend.emissions.text import bullets
from backend.fleet import data
from backend.fleet.figures import slice_figures
from backend.tools.contracts import Figure

SORTS = {"date": ("start_ts", True), "litres": ("litres", False), "hours": ("hours", False)}


def field_name(field_id: str) -> str:
    return f"Field {field_id.replace('-', '_').split('_')[-1]}"


def _frame() -> pd.DataFrame:
    j = data.jobs()
    return j.assign(label=j.litres_label, month=j.start_ts.dt.to_period("M").astype(str))


def _row(r) -> dict:
    figs = slice_figures(pd.DataFrame([r._asdict()]), synthetic_cols=True)
    per_ha = None
    if r.area_ha and r.area_ha > 0:
        per_ha = asdict(Figure(r.litres / r.area_ha, "L/ha", "allocated", bullets(
            f"**{r.litres:,.1f} litres** over **{r.area_ha:,.1f} hectares**.",
            "Litres are measured; the area is worked out from speed and tool width, so it is **allocated**."), source_ids=(r.source_id,)))
    return {
        "job_id": r.job_id, "date": r.start_ts.date().isoformat(), "month": r.month, "site_id": r.site_id,
        "machine_id": r.machine_id, "machine": data.machine_name(r.machine_id), "operation_code": r.operation_code,
        "operation": data.operation_name(r.operation_code),
        "client_id": None if pd.isna(r.client_id) else r.client_id, "client": None if pd.isna(r.client_id) else data.client_name(r.client_id),
        "field_id": None if pd.isna(r.field_id) else r.field_id, "field": None if pd.isna(r.field_id) else field_name(r.field_id),
        "hours": float(r.hours), "area_ha": None if pd.isna(r.area_ha) else float(r.area_ha),
        "litres": figs["litres"], "co2e_kg": figs["co2e_kg"], "cost_gbp": figs["cost_gbp"], "l_per_ha": per_ha,
    }


def fleet_jobs(site_id: str | None = None, machine_id: str | None = None, client_id: str | None = None,
               operation_code: str | None = None, field_id: str | None = None, month: str | None = None,
               operator_id: str | None = None, sort: str = "date", limit: int = 25, offset: int = 0) -> dict:
    """The job list, filtered and paged, with each job's fuel, emissions and cost. Operators are only a filter."""
    if sort not in SORTS:
        raise ValueError(f"cannot sort by {sort}")
    df = _frame()
    for col, value in (("site_id", site_id), ("machine_id", machine_id), ("client_id", client_id), ("operation_code", operation_code),
                       ("field_id", field_id), ("month", month), ("operator_id", operator_id)):
        if value:
            df = df[df[col] == value]
    by, ascending = SORTS[sort]
    page = df.sort_values([by, "job_id"], ascending=[ascending, True]).iloc[offset:offset + limit]
    return {"total_jobs": len(df), "offset": offset, "limit": limit, "sort": sort,
            "rows": [_row(r) for r in page.itertuples()],
            "totals": slice_figures(df, synthetic_cols=True) if len(df) else None}
