from __future__ import annotations

from backend.fleet import data
from backend.fleet.figures import slice_figures
from backend.tools.fleet_summary import _filtered, fleet_summary


def emissions_per_client(client_id: str | None = None) -> dict:
    """Litres, CO2e and cost per client farm. Fuel with no field, so no client, is shown as Unassigned."""
    rows = fleet_summary("client", client_id=client_id)["rows"]
    out = {"rows": [{**r, "client_id": r["key"]} for r in rows], "months": []}
    if client_id:
        df = _filtered(None, None, client_id, None, None, None)
        for month, g in df.groupby("month", sort=True):
            f = slice_figures(g, synthetic_cols=True)
            out["months"].append({"client_id": client_id, "client": data.client_name(client_id), "month": month,
                                  "litres": f["litres"], "co2e_kg": f["co2e_kg"]})
    return out
