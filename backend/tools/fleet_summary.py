from __future__ import annotations

import pandas as pd

from backend.fleet import data
from backend.fleet.figures import slice_figures

GROUPS = {"site": "site_id", "machine": "machine_id", "operation": "operation_code", "month": "month", "client": "client_id"}
NAMERS = {"site": data.site_name, "machine": data.machine_name, "operation": data.operation_name,
          "month": lambda m: m, "client": data.client_name}


def _filtered(site_id, machine_id, client_id, operation_code, operator_id, month) -> pd.DataFrame:
    df = data.ledger()
    if site_id:
        df = df[df.site_id == site_id]
    if machine_id:
        df = df[df.machine_id == machine_id]
    if client_id:
        df = df[df.client_id.isna()] if client_id == data.UNASSIGNED else df[df.client_id == client_id]
    if operation_code:
        df = df[df.operation_code == operation_code]
    if operator_id:  # a filter only: operators are never ranked or scored
        df = df[df.operator_id == operator_id]
    if month:
        df = df[df.month == month]
    return df


def fleet_summary(group_by: str = "site", site_id: str | None = None, machine_id: str | None = None,
                  client_id: str | None = None, operation_code: str | None = None, operator_id: str | None = None,
                  month: str | None = None) -> dict:
    """Fuel, CO2e and cost for the fleet, grouped by site, machine, operation, month or client."""
    if group_by not in GROUPS:
        raise ValueError(f"cannot group by {group_by}")
    df = _filtered(site_id, machine_id, client_id, operation_code, operator_id, month)
    synthetic = group_by in ("month", "client") or bool(operator_id)
    total = float(df.litres.sum())
    key_col = df[GROUPS[group_by]].fillna(data.UNASSIGNED)
    rows = []
    for key, g in df.groupby(key_col, sort=True):
        rows.append({"key": key, "name": NAMERS[group_by](key), **slice_figures(g, synthetic),
                     "hours": float(g.hours.sum()), "area_ha": float(g.area_ha.sum()), "jobs": int(g.is_job.sum()),
                     "share_pct": 100 * float(g.litres.sum()) / total if total else 0.0})
    rows.sort(key=lambda r: -r["litres"]["value"] if group_by != "month" else r["key"])
    return {"group_by": group_by, "rows": rows, "totals": slice_figures(df, synthetic) if len(df) else None}
