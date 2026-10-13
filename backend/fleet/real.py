"""Real-data loaders for the three fleet sites. One row per job, with the real litres, hours and areas.

S1: TUM arable site (raw telemetry, already aggregated in data/aggregated).
S2: vineyard site, Tuscany (per-operation summary, real dates; Rossi & Alemanno, CC BY 4.0).
S3: tillage site, Konya (raw CAN data, ten sessions; Dana, Ozener & Tellioglu, CC BY 4.0).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AGG = ROOT / "data" / "aggregated"
RAW = ROOT / "data" / "raw"
MAX_JOB_HOURS = 8.0  # a longer group of passes is split into working days

JOB_COLUMNS = ["job_id", "site_id", "machine_id", "field_id", "operation_code", "hours", "litres", "area_ha",
               "mean_load_pct", "idle_ratio", "sessions", "litres_label", "area_label", "source_id", "date_real"]

VINEYARD_OPS = {
    "Ridging": "vy_ridging", "Light rigding": "vy_light_ridging", "Unridging": "vy_unridging",
    "Sward and soil tillage": "vy_sward_soil_tillage", "Soil tillage": "vy_soil_tillage", "Mulching": "vy_mulching",
    "Shoot thinning": "vy_shoot_thinning", "Shoot removing": "vy_shoot_removing", "Leaf removing": "vy_leaf_removing",
    "Prepruning": "vy_prepruning", "Crop protection SR": "vy_crop_protection_single_row",
    "Crop protection MR": "vy_crop_protection_multi_row", "Harvest": "vy_harvest", "Fertilisation": "vy_fertilising",
}
TUMOSAN_IMPLEMENTS = {1: ("ploughing", 1.5), 2: ("rotary_tilling", 3.0)}  # 5 furrows x 30 cm; 3 m rotary tiller


def _split_long(df: pd.DataFrame) -> pd.DataFrame:
    """Split groups of passes longer than a working day into several jobs that share the totals equally."""
    parts = []
    for row in df.itertuples(index=False):
        n = max(1, math.ceil(row.hours / MAX_JOB_HOURS))
        for i in range(n):
            d = row._asdict()
            for k in ("hours", "litres", "area_ha"):
                d[k] = None if pd.isna(d[k]) else d[k] / n
            d["sessions"] = max(1, round(row.sessions / n))
            parts.append(d)
    return pd.DataFrame(parts)


def tum_jobs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """TUM jobs (tractor x operation x field) and the fuel that is not in any job (transport, idling, ...)."""
    summary = pd.read_csv(AGG / "farm_a_operations_summary.csv")
    files = pd.read_csv(AGG / "farm_a_field_files.csv")
    width = files.dropna(subset=["implement_width_m"]).groupby(["tractor_id", "operation_code"]).implement_width_m.first()

    is_job = (summary.activity_class == "field_work") & summary.operation_code.notna()
    work = summary[is_job].sort_values(["tractor_id", "operation_code", "field_id"], na_position="last").copy()
    w = [width.get((t, o), np.nan) for t, o in zip(work.tractor_id, work.operation_code)]
    work["area_ha"] = work.distance_km * pd.Series(w, index=work.index) / 10  # km x m / 10 = ha

    jobs = _split_long(pd.DataFrame({
        "machine_id": "S1-T" + work.tractor_id.str[-1], "field_id": "S1-" + work.field_id.astype("string"),
        "operation_code": work.operation_code, "hours": work.hours, "litres": work.litres, "area_ha": work.area_ha,
        "mean_load_pct": work.mean_load_pct, "idle_ratio": np.nan, "sessions": work.sessions,
    }).astype({"field_id": "object"}))
    jobs["field_id"] = jobs.field_id.where(jobs.field_id.notna() & (jobs.field_id != "S1-<NA>"), None)
    jobs.insert(0, "job_id", [f"S1-J{i + 1:04d}" for i in range(len(jobs))])
    jobs.insert(1, "site_id", "S1")
    jobs["litres_label"], jobs["area_label"] = "measured", "allocated"
    jobs["source_id"], jobs["date_real"] = "tum_alc_data", pd.NaT

    # Fuel that is in no job, plus the frozen-logger gaps (no fuel counted, kept for data-quality reporting).
    rest = summary[~is_job]
    rest = rest[(rest.litres > 0) | (rest.activity_class == "data_gap")]
    other = rest.groupby(["tractor_id", "activity_class"], as_index=False)[["hours", "litres"]].sum()
    other.insert(0, "machine_id", "S1-T" + other.tractor_id.str[-1])
    return jobs[JOB_COLUMNS], other.drop(columns="tractor_id").reset_index(drop=True)


def vineyard_jobs(path: Path | None = None) -> pd.DataFrame:
    v = pd.read_csv(path or RAW / "vineyard" / "Dataset.csv", sep=";")
    date_real = pd.to_datetime(dict(year=v.Year, month=v.Month, day=v.Day)) + pd.to_timedelta(v.Time + ":00")
    jobs = pd.DataFrame({
        "site_id": "S2", "machine_id": "S2-T" + v.Tractor.str.extract(r"(\d+)")[0],
        "field_id": "S2-F" + v.FieldNumber.str.extract(r"(\d+)")[0], "operation_code": v.Activity.map(VINEYARD_OPS),
        "hours": v.Minutes / 60, "litres": v.FuelConsumption, "area_ha": v.AreaHa, "mean_load_pct": v.Torque,
        "idle_ratio": v.IdleRatio, "sessions": 1, "litres_label": "measured", "area_label": "allocated",
        "source_id": "vineyard_ops", "date_real": date_real,
    })
    jobs = jobs.sort_values("date_real", kind="stable").reset_index(drop=True)
    jobs.insert(0, "job_id", [f"S2-J{i + 1:04d}" for i in range(len(jobs))])
    return jobs[JOB_COLUMNS]


def _otsu(values: np.ndarray) -> float:
    """Threshold that best separates two groups (hitch lowered / raised) in one file."""
    hist, edges = np.histogram(np.clip(values, 0, 100), bins=100, range=(0, 100))
    centres, total = (edges[:-1] + edges[1:]) / 2, hist.sum()
    best, thr = -1.0, 50.0
    for i in range(1, 100):
        w0, w1 = hist[:i].sum(), hist[i:].sum()
        if w0 == 0 or w1 == 0:
            continue
        m0, m1 = (hist[:i] * centres[:i]).sum() / w0, (hist[i:] * centres[i:]).sum() / w1
        between = w0 * w1 * (m0 - m1) ** 2 / total ** 2
        if between > best:
            best, thr = between, edges[i]
    return thr


def tumosan_jobs(folder: Path | None = None) -> pd.DataFrame:
    """Ten sessions. Litres are the fuel-rate integral (measured); area is speed x time with the hitch
    lowered x the tool width (allocated), because the published files have no GPS."""
    folder = folder or RAW / "tumosan" / "extracted"
    dt_h = 0.1 / 3600  # 10 Hz
    rows = []
    for path in sorted(folder.glob("FIELD_*_RAW.tab"), key=lambda p: int(p.name.split("_")[1])):
        n = int(path.name.split("_")[1])
        d = pd.read_csv(path, sep="\t")
        code, width = TUMOSAN_IMPLEMENTS[int(d.KeypadButon.iloc[0])]
        speed = d.WheelBasedVehicleSpeed.clip(lower=0)
        working = (d.HtcPositionSensPerc < _otsu(d.HtcPositionSensPerc.to_numpy())) & (speed > 1)
        rows.append({
            "site_id": "S3", "machine_id": "S3-T1", "field_id": f"S3-F{n:02d}", "operation_code": code,
            "hours": len(d) * dt_h, "litres": float(d.EngFuelRate.clip(lower=0).sum() * dt_h),
            "area_ha": float((speed[working] * dt_h).sum() * width / 10),
            "mean_load_pct": float(d.ActualEngine_PercTorque[working].mean()),
            "idle_ratio": float((speed < 0.5).mean()), "sessions": 1, "litres_label": "measured",
            "area_label": "allocated", "source_id": "tumosan_tillage", "date_real": pd.NaT,
        })
    jobs = pd.DataFrame(rows)
    jobs.insert(0, "job_id", [f"S3-J{i + 1:04d}" for i in range(len(jobs))])
    return jobs[JOB_COLUMNS]
