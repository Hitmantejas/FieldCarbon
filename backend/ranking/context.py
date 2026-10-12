from dataclasses import dataclass, field, replace
from functools import lru_cache

import pandas as pd

from backend.emissions.farm_summary import AGG, TRACTOR_KW, FUEL


@dataclass(frozen=True)
class FarmContext:
    """What the engine knows about a farm. Anything absent from `known` is genuinely unknown."""

    litres_by_op: dict[str, float]
    hectares_by_op: dict[str, float]
    mean_load_by_op: dict[str, float]
    tractor_kw: dict[str, int]
    litres_by_tractor: dict[str, float]
    total_litres: float
    fuel_type: str = FUEL
    known: dict[str, object] = field(default_factory=dict)  # farmer-provided answers, e.g. tyre_pressure_checked
    # Working litres per job on the fields that were ploughed. Tillage changes replace the plough system,
    # so jobs on fields already worked without a plough are not counted. None = no field data: use litres_by_op.
    ploughed_litres_by_op: dict[str, float] | None = None


@lru_cache(maxsize=1)
def _farm_a_base() -> FarmContext:
    rows = pd.read_csv(AGG / "farm_a_operations_summary.csv")
    work = rows[(rows.activity_class == "field_work") & rows.operation_code.notna()].copy()
    work["load_hours"] = work.mean_load_pct * work.hours
    per_op = work.groupby("operation_code")[["litres", "hours", "load_hours"]].sum()
    areas = pd.read_csv(AGG / "farm_a_field_files.csv").groupby("operation_code").area_worked_ha.sum()
    ploughed = set(work[(work.operation_code == "ploughing") & work.field_id.notna()].field_id)
    return FarmContext(
        litres_by_op=per_op.litres.to_dict(),
        hectares_by_op=areas.to_dict(),
        mean_load_by_op=(per_op.load_hours / per_op.hours).to_dict(),
        tractor_kw=dict(TRACTOR_KW),
        litres_by_tractor=rows.groupby("tractor_id").litres.sum().to_dict(),
        total_litres=float(rows.litres.sum()),
        ploughed_litres_by_op=work[work.field_id.isin(ploughed)].groupby("operation_code").litres.sum().to_dict(),
    )


def farm_a_context(known: dict[str, object] | None = None) -> FarmContext:
    return replace(_farm_a_base(), known=known or {})
