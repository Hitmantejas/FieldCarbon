"""Row-level cleaning of TUM Agricultural Load Cycles telemetry (pure functions, chunk-safe).

Reads CSV only. The zips also contain .pkl files: never load them (untrusted pickle = code execution).
Aggregation happens in BigQuery; this module only prepares rows for `telemetry_raw`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
import pandas as pd

REF_DIR = Path(__file__).resolve().parents[1] / "reference"

COLUMN_MAP = {
    "Time_(s)": "time",
    "EngSpeed_(RPM)": "eng_speed_rpm",
    "EngPercentLoadAtCurrentSpeed_(%)": "eng_load_pct",
    "EngFuelRate_(L/h)": "fuel_rate_lph",
    "SpeedOverGround_(m/s)": "speed_mps",
    "WheelBasedMachineSpeed_(m/s)": "wheel_speed_mps",   # fallback when GNSS speed is absent (Fendt 820)
    "Latitude_(°)": "lat",
    "Longitude_(°)": "lon",
    "Altitude_(m)": "altitude_m",
    "RearPTOOutputShaftSpeed_(RPM)": "pto_rpm",
    "RearDraft_(N)": "rear_draft_n",
    "WorkType_[-]": "work_type",
    "Tractor_Model_[-]": "tractor_model",
    "Implement_Model_[-]": "implement_model",
    "Implement_Width_(m)": "implement_width_m",
    "Status_[-]": "status",
}

# Upper limits of the valid J1939 range; values above are "not available"/"error" sentinels.
J1939_MAX = {
    "eng_speed_rpm": 8031.875,
    "eng_load_pct": 250.0,
    "fuel_rate_lph": 3212.75,
    "speed_mps": 65.0,
    "pto_rpm": 8031.875,
    "rear_draft_n": 322550.0,
    "wheel_speed_mps": 65.0,
}

NOT_WORKING = "not working"
ON_ROAD = "Driving On-Road"

# Brands are dropped at load. Ordered by rated power (article Table 1).
TRACTORS = {
    "211": ("tractor_1", 77.0),
    "314": ("tractor_2", 104.0),
    "820": ("tractor_3", 140.0),
    "722": ("tractor_4", 163.0),
    "724": ("tractor_5", 174.0),
}

# (keywords that must all appear, case-insensitive) -> (implement_class, default operation_code).
# Ordered: combination drills first because they also contain "Zirkon".
IMPLEMENT_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("amazone",), "seed_drill_combination", "seed_drill_combination"),
    (("pöttinger",), "seed_drill_combination", "seed_drill_combination"),
    (("zirkon",), "power_harrow", "power_harrowing"),
    (("korund",), "seedbed_combination", "seedbed_combination"),
    (("europal",), "plough", "ploughing"),
    (("komet",), "cultivator", "cultivating_deep"),
    (("terrano",), "cultivator", "cultivating_deep"),
    (("cultivator",), "cultivator", "cultivating_shallow"),   # generic name (Tractor 4)
    (("joker",), "disc_harrow", "disc_harrowing"),
    (("disc harrow",), "disc_harrow", "disc_harrowing"),      # generic name (Tractor 4)
    (("monosem",), "precision_seeder", "precision_seeding"),
    (("rauch",), "fertiliser_spreader", "fertilizing"),
    (("gaspardo",), "sprayer", "spraying"),
    (("slicer",), "mower", "mowing"),
    (("disco",), "mower", "mowing"),
    (("swat",), "swather", "swathing"),
    (("mulcher",), "mulcher", "mulching"),
    (("rotary tiller",), "rotary_tiller", "rotary_tilling"),
    (("tipper",), "trailer", "transport"),
    (("agroliner",), "trailer", "transport"),
]


# Output schema of telemetry_raw (must match backend/emissions/ddl/001_tables.sql).
OUTPUT_SCHEMA: dict[str, str] = {
    "tractor_id": "string", "row_idx": "int64", "t_s": "float64", "dt_s": "float64", "session_id": "int64",
    "eng_speed_rpm": "float64", "eng_load_pct": "float64", "fuel_rate_lph": "float64", "fuel_l": "float64",
    "speed_mps": "float64", "lat": "float64", "lon": "float64", "altitude_m": "float64", "pto_rpm": "float64",
    "rear_draft_n": "float64", "speed_source": "string", "work_type": "string", "implement_class": "string", "implement_width_m": "float64",
    "status": "string", "activity_class": "string", "operation_code": "string", "attribution_label": "string",
}


# Schema of telemetry_field_points (must match backend/emissions/ddl/001_tables.sql).
FIELD_POINTS_SCHEMA: dict[str, str] = {
    "tractor_id": "string", "work_type": "string", "field_file": "string", "status": "string",
    "lat": "float64", "lon": "float64", "speed_mps": "float64", "dt_s": "float64", "implement_width_m": "float64",
}


@dataclass(frozen=True)
class Params:
    dt_cap_s: float = 1.0          # max time step credited with fuel (ignores logging gaps)
    session_gap_s: float = 60.0    # gap that starts a new session
    idle_speed_mps: float = 0.3    # below this, no implement and off-road = idle
    frozen_min_s: float = 60.0     # all signals + GPS unchanged this long while "active" = logger gap


# Signals that must all repeat for a row to count as frozen (carried-forward values, not measurements).
FROZEN_SIGNALS = ["eng_speed_rpm", "fuel_rate_lph", "speed_mps", "eng_load_pct", "lat", "lon"]
RAW_FROZEN_SIGNALS = [k for k, v in COLUMN_MAP.items() if v in FROZEN_SIGNALS or v == "wheel_speed_mps"]


@dataclass
class StreamState:
    """Carried between chunks so that chunked processing equals whole-file processing."""
    prev_t: float | None = None
    session_id: int = 0
    rows_seen: int = 0
    last_op: dict[tuple[int, str], str] = field(default_factory=dict)  # (session, implement) -> last labelled op


def load_worktype_map(ref_dir: Path = REF_DIR) -> dict[str, str]:
    ops = pd.read_csv(ref_dir / "ref_operations.csv").dropna(subset=["tum_worktypes"])
    return {w: row.operation_code for row in ops.itertuples() for w in row.tum_worktypes.split("|")}


def tractor_from_model(model: str) -> tuple[str, float]:
    for key, value in TRACTORS.items():
        if key in str(model):
            return value
    raise ValueError(f"Unknown tractor model: {model!r}")


def implement_class(model: object) -> tuple[str | None, str | None]:
    if model is None or (isinstance(model, float) and np.isnan(model)) or str(model).strip() == "":
        return None, None
    name = str(model).lower()
    for keywords, cls, op in IMPLEMENT_RULES:
        if all(k in name for k in keywords):
            return cls, op
    return "implement_unknown", None


def rename_and_null_sentinels(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename to snake_case, add missing columns as null, null J1939 sentinels, pick the speed signal."""
    df = raw.rename(columns=COLUMN_MAP)
    df = df.reindex(columns=list(COLUMN_MAP.values()))
    for col in df.columns:   # numeric columns: non-numeric text such as "unknown" becomes null
        if col in J1939_MAX or OUTPUT_SCHEMA.get(col) == "float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")   # ints too: fixed type
    for col, upper in J1939_MAX.items():
        df[col] = df[col].where(df[col] <= upper)
    gnss = df["speed_mps"].notna().any()
    if not gnss:
        df["speed_mps"] = df["wheel_speed_mps"]
    df["speed_source"] = "gnss" if gnss else "wheel"
    return df.drop(columns=["wheel_speed_mps"])


def derive_time(df: pd.DataFrame, state: StreamState, params: Params) -> pd.DataFrame:
    """Adds t_s, dt_s (capped, 0 at session start), session_id, fuel_l. Mutates `state`."""
    t = pd.to_timedelta(df["time"]).dt.total_seconds().to_numpy()
    prev = np.concatenate([[np.nan if state.prev_t is None else state.prev_t], t[:-1]])
    dt = t - prev
    new_session = np.isnan(dt) | (dt > params.session_gap_s) | (dt < 0)
    if state.prev_t is None:
        new_session[0] = False      # the very first row opens session 0
    session = state.session_id + np.cumsum(new_session)
    dt_s = np.where(new_session | np.isnan(dt), 0.0, np.minimum(dt, params.dt_cap_s))

    out = df.drop(columns=["time"]).copy()
    out.insert(0, "row_idx", np.arange(state.rows_seen, state.rows_seen + len(df), dtype=np.int64))
    out.insert(1, "t_s", t)
    out.insert(2, "dt_s", dt_s)
    out.insert(3, "session_id", session.astype(np.int64))
    out["fuel_l"] = out["fuel_rate_lph"].fillna(0.0) * dt_s / 3600.0

    if len(df):
        state.prev_t = float(t[-1])
        state.session_id = int(session[-1])
        state.rows_seen += len(df)
    return out


def frozen_mask(df: pd.DataFrame, params: Params) -> pd.Series:
    """Rows in a run where all FROZEN_SIGNALS repeat for >= frozen_min_s while the record claims activity.

    Such runs (e.g. 0 rpm at 3.36 m/s with a fixed GPS position for hours) are carried-forward values
    from logger gaps, not measurements. A genuinely parked tractor (all zeros) is not flagged.
    """
    sig = df[FROZEN_SIGNALS].fillna(-999999.0)
    same = (sig == sig.shift()).all(axis=1) & (df["session_id"] == df["session_id"].shift())
    run = (~same).cumsum()
    t = df["t_s"].groupby(run)
    duration = t.transform("max") - t.transform("min")
    active = ((df["eng_speed_rpm"].fillna(0) > 0) | (df["fuel_rate_lph"].fillna(0) > 0)
              | (df["speed_mps"].fillna(0) > 0))
    return (duration >= params.frozen_min_s) & active


def split_trailing_run(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split off the trailing run of rows whose signals equal the last row (may continue in the next chunk)."""
    cols = [c for c in RAW_FROZEN_SIGNALS if c in raw]
    sig = raw[cols].fillna(-999999.0)
    differs = np.flatnonzero(~(sig == sig.iloc[-1]).all(axis=1).to_numpy())
    start = int(differs[-1]) + 1 if len(differs) else 0
    return raw.iloc[:start], raw.iloc[start:]


def classify(df: pd.DataFrame, state: StreamState, worktype_map: dict[str, str], params: Params) -> pd.DataFrame:
    """Adds implement_class, activity_class, operation_code, attribution_label; drops brand columns.

    data_gap                frozen carried-forward values (see frozen_mask) -> excluded, fuel set to 0
    engine_off              engine speed exactly 0 and no fuel flow         -> measured (no fuel)
    field_work              WorkType labelled by the dataset authors        -> measured
    implement_nonproductive implement attached, not working: last op of      -> allocated
                            that implement in the session, else default
    road_transport / idle / offroad_unassigned (no implement)                -> allocated
    """
    out = df.copy()
    impl = out["implement_model"].map(implement_class)
    out["implement_class"] = impl.map(lambda x: x[0])
    default_op = impl.map(lambda x: x[1])

    wt = out["work_type"].fillna(NOT_WORKING)
    working = wt != NOT_WORKING
    labelled_op = wt.map(lambda w: worktype_map.get(w, f"unmapped:{w}")).where(working)
    has_impl = out["implement_class"].notna()
    frozen = frozen_mask(out, params)
    engine_off = (out["eng_speed_rpm"] == 0) & (out["fuel_rate_lph"].fillna(0) == 0)

    # Last labelled operation per (session, implement), carried across chunks.
    sess_impl = list(zip(out["session_id"], out["implement_class"]))
    carried = pd.Series([state.last_op.get(k) for k in sess_impl], index=out.index, dtype=object)
    key = out["session_id"].astype(str) + "|" + out["implement_class"].fillna("")
    last_op = labelled_op.groupby(key).ffill()
    last_op = last_op.where(last_op.notna(), carried)
    for k, op_ in labelled_op.dropna().groupby([out["session_id"], out["implement_class"]]).last().items():
        state.last_op[k] = op_
    state.last_op = {k: v for k, v in state.last_op.items() if k[0] == state.session_id}

    activity = np.select(
        [frozen, engine_off, working, has_impl, out["status"] == ON_ROAD,
         out["speed_mps"].fillna(0) < params.idle_speed_mps],
        ["data_gap", "engine_off", "field_work", "implement_nonproductive", "road_transport", "idle"],
        default="offroad_unassigned",
    )
    op = np.select(
        [activity == "field_work", activity == "implement_nonproductive",
         activity == "road_transport", activity == "idle"],
        [labelled_op.to_numpy(dtype=object), last_op.fillna(default_op).to_numpy(dtype=object),
         np.full(len(out), "transport", dtype=object), np.full(len(out), "idle", dtype=object)],
        default=None,
    )
    out["activity_class"] = activity
    out["operation_code"] = pd.Series(op, index=out.index, dtype=object)
    out["attribution_label"] = np.select(
        [activity == "data_gap", np.isin(activity, ["field_work", "engine_off"])], ["excluded", "measured"],
        default="allocated")
    out["fuel_l"] = out["fuel_l"].where(~frozen, 0.0)
    return out.drop(columns=["implement_model", "tractor_model"])


def clean_chunk(raw: pd.DataFrame, state: StreamState, worktype_map: dict[str, str],
                params: Params = Params()) -> pd.DataFrame:
    df = rename_and_null_sentinels(raw)
    tractor_id, _ = tractor_from_model(df["tractor_model"].dropna().iloc[0])
    df = derive_time(df, state, params)
    df = classify(df, state, worktype_map, params)
    df["tractor_id"] = tractor_id
    return df[list(OUTPUT_SCHEMA)].astype(OUTPUT_SCHEMA)


def clean_stream(raw_chunks: Iterable[pd.DataFrame], worktype_map: dict[str, str],
                 params: Params = Params()) -> Iterator[pd.DataFrame]:
    """Clean a sequence of raw CSV chunks. The trailing run of repeated rows is held back to the next
    chunk, so every frozen run is judged whole and chunked output equals whole-file output."""
    state, pending = StreamState(), None
    for raw in raw_chunks:
        if pending is not None and len(pending):
            raw = pd.concat([pending, raw], ignore_index=True)
        head, pending = split_trailing_run(raw)
        if len(head):
            yield clean_chunk(head.reset_index(drop=True), state, worktype_map, params)
    if pending is not None and len(pending):
        yield clean_chunk(pending.reset_index(drop=True), state, worktype_map, params)


def field_points(raw: pd.DataFrame, tractor_id: str, work_type: str, field_file: str,
                 params: Params = Params()) -> pd.DataFrame:
    """~1 Hz GPS points of one per-field file (first row of each second), typed for BigQuery."""
    df = derive_time(rename_and_null_sentinels(raw), StreamState(), params)
    keep = df["t_s"].floordiv(1.0).diff().ne(0)
    pts = df.loc[keep].assign(tractor_id=tractor_id, work_type=work_type, field_file=field_file)
    return pts[list(FIELD_POINTS_SCHEMA)].astype(FIELD_POINTS_SCHEMA).reset_index(drop=True)


def field_file_summary(raw: pd.DataFrame, params: Params = Params()) -> dict[str, float]:
    """Hours, litres and worked area for one per-field file (status 'working' rows only for area)."""
    df = rename_and_null_sentinels(raw)
    state = StreamState()
    df = derive_time(df, state, params)
    frozen = frozen_mask(df, params)
    df["fuel_l"] = df["fuel_l"].where(~frozen, 0.0)
    working = (df["status"] == "working") & ~frozen
    width = df["implement_width_m"].astype(float)
    area_m2 = (df["speed_mps"].fillna(0) * df["dt_s"] * width).where(working, 0.0).sum()
    return {
        "rows": int(len(df)),
        "hours_total": float(df["dt_s"].where(~frozen, 0.0).sum() / 3600.0),
        "hours_excluded_frozen": float(df["dt_s"].where(frozen, 0.0).sum() / 3600.0),
        "hours_working": float(df["dt_s"].where(working, 0.0).sum() / 3600.0),
        "litres_total": float(df["fuel_l"].sum()),
        "litres_working": float(df["fuel_l"].where(working, 0.0).sum()),
        "area_worked_ha": float(area_m2 / 10_000.0),
        "implement_width_m": float(width.dropna().median()) if width.notna().any() else float("nan"),
        "mean_load_pct_working": float(df["eng_load_pct"].where(working).mean()),
    }
