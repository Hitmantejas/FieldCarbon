from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

REF = Path(__file__).resolve().parents[2] / "data" / "reference"
AGG = Path(__file__).resolve().parents[2] / "data" / "aggregated"

# Below this, litres/ha is dominated by headland and start-up noise.
MIN_RATED_HA = 5.0

NON_WORKING_CLASSES = {"implement_nonproductive", "road_transport", "idle"}
ABOVE_BANDS = {"above_typical", "well_above"}


@dataclass(frozen=True)
class Reference:
    low: float
    typical: float
    high: float
    band_pct: float
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class OperationRating:
    operation_code: str
    display_name: str
    band: str
    hectares: float
    litres: float
    l_per_ha: float | None
    reference: Reference | None
    litres_at_stake_low: float
    litres_at_stake_high: float
    match_quality: str
    label: str  # area is derived from GPS and implement width, so not "measured"
    how: str


@dataclass(frozen=True)
class AboveRange:
    count: int
    litres_low: float
    litres_high: float


@dataclass(frozen=True)
class NotWorkingShare:
    litres: float
    total_litres: float
    share_pct: float
    label: str


@lru_cache(maxsize=1)
def _operations() -> pd.DataFrame:
    return pd.read_csv(REF / "ref_operations.csv").set_index("operation_code")


@lru_cache(maxsize=1)
def _rates() -> pd.DataFrame:
    return pd.read_csv(REF / "ref_fuel_use_rates.csv").set_index("rate_id")


def _row_range(row: pd.Series) -> tuple[float, float, float]:
    typical, pct = row.l_per_ha, row.published_band_pct / 100
    low = row.range_low_l_per_ha if pd.notna(row.range_low_l_per_ha) else typical * (1 - pct)
    high = row.range_high_l_per_ha if pd.notna(row.range_high_l_per_ha) else typical * (1 + pct)
    return low, typical, high


def reference_range(operation_code: str) -> Reference | None:
    ids = _operations().isu_rate_ids.get(operation_code)
    if pd.isna(ids):
        return None
    rows = _rates().loc[ids.split("|")]  # composite operations sum their rows (see ref_operations note)
    low, typical, high = map(sum, zip(*(_row_range(r) for _, r in rows.iterrows())))
    return Reference(low, typical, high, float(rows.published_band_pct.iloc[0]), tuple(rows.source_id.unique()))


def _band(l_per_ha: float, ref: Reference) -> str:
    if l_per_ha < ref.low:
        return "below_typical"
    if l_per_ha <= ref.high:
        return "typical"
    # "Well above" = beyond the top of the range by more than the published variability band.
    return "above_typical" if l_per_ha <= ref.high * (1 + ref.band_pct / 100) else "well_above"


def _explain(hectares: float, litres: float, lph: float, ref: Reference, match_quality: str) -> str:
    joined = ", two jobs added together" if match_quality == "composite" else ""
    return (
        f"{litres:,.0f} L of working fuel over {hectares:.1f} ha = {lph:.1f} L/ha. Typical range "
        f"{ref.low:.1f} to {ref.high:.1f} L/ha ({', '.join(ref.source_ids)}{joined}; where no range is published, "
        f"+-{ref.band_pct:g}% around the typical rate). Area comes from the GPS track and implement width, so this "
        "is allocated, not measured. The reference rates leave out field travel, so treat it as a guide."
    )


def _rate(op: str, hectares: float, litres: float) -> OperationRating:
    meta = _operations().loc[op]
    ref = reference_range(op)
    common = dict(operation_code=op, display_name=meta.display_name, hectares=float(hectares), litres=float(litres),
                  reference=ref, match_quality=meta.match_quality, label="allocated",
                  l_per_ha=None, litres_at_stake_low=0.0, litres_at_stake_high=0.0)
    if ref is None:
        return OperationRating(band="no_reference", how="No published fuel rate per hectare exists for this job, "
                               "so it cannot be rated.", **common)
    if hectares < MIN_RATED_HA:
        return OperationRating(band="insufficient_data", how=f"Only {hectares:.1f} ha recorded for this job "
                               f"(minimum {MIN_RATED_HA:g} ha), too little to compare fuel use per hectare fairly.",
                               **common)
    lph = litres / hectares
    # Only a farm above the typical range has anything at stake; inside it the spread is normal variation.
    above = lph > ref.high
    common.update(l_per_ha=lph,
                  litres_at_stake_low=(lph - ref.high) * hectares if above else 0.0,
                  litres_at_stake_high=(lph - ref.typical) * hectares if above else 0.0)
    return OperationRating(band=_band(lph, ref), how=_explain(hectares, litres, lph, ref, meta.match_quality), **common)


def rate_operations(field_files: pd.DataFrame) -> list[OperationRating]:
    per_op = field_files.groupby("operation_code")[["area_worked_ha", "litres_working"]].sum()
    ratings = [_rate(op, r.area_worked_ha, r.litres_working) for op, r in per_op.iterrows()]
    return sorted(ratings, key=lambda r: (-r.litres_at_stake_high, -r.litres))


def above_range(ratings: list[OperationRating]) -> AboveRange:
    hits = [r for r in ratings if r.band in ABOVE_BANDS]
    return AboveRange(len(hits), sum(r.litres_at_stake_low for r in hits), sum(r.litres_at_stake_high for r in hits))


def not_working_share(summary: pd.DataFrame) -> NotWorkingShare:
    total = float(summary.litres.sum())
    idle = float(summary[summary.activity_class.isin(NON_WORKING_CLASSES)].litres.sum())
    return NotWorkingShare(litres=idle, total_litres=total, share_pct=100 * idle / total, label="allocated")


def farm_a_ratings() -> tuple[list[OperationRating], NotWorkingShare]:
    return (
        rate_operations(pd.read_csv(AGG / "farm_a_field_files.csv")),
        not_working_share(pd.read_csv(AGG / "farm_a_operations_summary.csv")),
    )
