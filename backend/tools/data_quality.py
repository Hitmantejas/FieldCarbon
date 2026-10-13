from __future__ import annotations

from dataclasses import asdict

from backend.emissions.text import bullets
from backend.fleet import data
from backend.tools.contracts import Figure


def _fig(value: float, unit: str, label: str, how: str, *sources: str) -> dict:
    return asdict(Figure(value, unit, label, how, source_ids=tuple(sources)))


def data_quality() -> dict:
    """How much of the fuel is measured, how much has no client, and what was left out."""
    ledger, jobs, other = data.ledger(), data.jobs(), data.other_activity()
    total = float(ledger.litres.sum())
    measured = float(ledger[ledger.label == "measured"].litres.sum())
    unassigned = float(ledger[ledger.client_id.isna()].litres.sum())
    frozen = float(other[other.activity_class == "data_gap"].hours.sum())
    no_area = int(jobs.area_ha.isna().sum())
    return {
        "measured_share_pct": _fig(100 * measured / total, "% of fuel", "measured", bullets(
            f"**{measured:,.0f} of {total:,.0f} litres** come straight from the machines' own fuel data.",
            "The rest is fuel burned outside jobs, which is measured in total but shared across months by rule."),
            "tum_alc_data", "vineyard_ops", "tumosan_tillage"),
        "unassigned_litres": _fig(unassigned, "L", "allocated", bullets(
            f"**{unassigned:,.0f} litres** cannot be given to a client farm.",
            "Most of it was burned outside jobs (travel, idling), where no field is known."), "tum_alc_data"),
        "frozen_hours": _fig(frozen, "h", "measured", bullets(
            f"**{frozen:,.1f} hours** are left out because the recorder repeated the same values.",
            "No fuel is counted in those hours."), "tum_alc_data"),
        "jobs_without_area": _fig(no_area, "jobs", "measured", bullets(
            f"**{no_area} jobs** have no area, so litres per hectare cannot be worked out for them.",
            "These are mostly transport jobs."), "tum_alc_data"),
    }
