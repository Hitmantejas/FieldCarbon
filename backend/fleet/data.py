"""Cached readers for the fleet tables in data/fleet, plus the fuel ledger every fleet tool starts from."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "data" / "fleet"

OTHER_NAMES = {
    "other_road_transport": "Road transport", "other_idle": "Idling",
    "other_implement_nonproductive": "Implement attached, not working", "other_offroad_unassigned": "Off-road, unassigned",
}
UNASSIGNED = "unassigned"


def _read(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(FLEET / f"{name}.csv", **kw)


@lru_cache(maxsize=1)
def jobs() -> pd.DataFrame:
    return _read("jobs", parse_dates=["start_ts", "date_real"])


@lru_cache(maxsize=1)
def other_activity() -> pd.DataFrame:
    return _read("other_activity")


@lru_cache(maxsize=1)
def machines() -> pd.DataFrame:
    return _read("machines").set_index("machine_id")


@lru_cache(maxsize=1)
def sites() -> pd.DataFrame:
    return _read("sites").set_index("site_id")


@lru_cache(maxsize=1)
def operations() -> pd.DataFrame:
    return _read("operations").set_index("operation_code")


@lru_cache(maxsize=1)
def clients() -> pd.DataFrame:
    return _read("clients").set_index("client_id")


@lru_cache(maxsize=1)
def deliveries() -> pd.DataFrame:
    return _read("fuel_deliveries", parse_dates=["ts"])


@lru_cache(maxsize=1)
def dispenses() -> pd.DataFrame:
    return _read("fuel_dispenses", parse_dates=["ts"])


@lru_cache(maxsize=1)
def depots() -> pd.DataFrame:
    return _read("depots").set_index("depot_id")


@lru_cache(maxsize=1)
def stock_readings() -> pd.DataFrame:
    return _read("depot_stock_readings", parse_dates=["date"])


@lru_cache(maxsize=1)
def maintenance() -> pd.DataFrame:
    """Workshop events per machine (synthetic): event_id, machine_id, date, event_type, job_hours_at_event, note."""
    return _read("maintenance_events", parse_dates=["date"])


@lru_cache(maxsize=1)
def ledger() -> pd.DataFrame:
    """All fuel burned, one row per job or per machine-month of non-job fuel (data gaps carry no fuel and are left out)."""
    j = jobs().assign(month=lambda d: d.start_ts.dt.to_period("M").astype(str), is_job=True, label=lambda d: d.litres_label)
    o = other_activity()
    o = o[o.activity_class != "data_gap"].assign(
        site_id=lambda d: d.machine_id.str[:2], operation_code=lambda d: "other_" + d.activity_class, operator_id=None,
        client_id=None, field_id=None, area_ha=np.nan, label="allocated", source_id="tum_alc_data", is_job=False)
    cols = ["site_id", "machine_id", "operator_id", "client_id", "field_id", "operation_code", "month", "litres", "hours",
            "area_ha", "label", "source_id", "is_job"]
    return pd.concat([j[cols], o[cols]], ignore_index=True)


@lru_cache(maxsize=1)
def price_by_month() -> pd.Series:
    """Red diesel price per litre by month: what the deliveries cost, weighted by litres; Defra's price for months without one."""
    d = deliveries().drop_duplicates(["depot_id", "supplier", "doc_no"])
    paid = (d.litres * d.unit_price_gbp).groupby(d.ts.dt.to_period("M")).sum() / d.litres.groupby(d.ts.dt.to_period("M")).sum()
    defra = pd.read_csv(ROOT / "data" / "reference" / "ref_fuel_prices.csv", parse_dates=["price_month"])
    defra = defra.set_index(defra.price_month.dt.to_period("M")).price_per_litre
    months = pd.period_range("2025-05", "2026-04", freq="M")
    price = paid.reindex(months).fillna(defra.reindex(months))
    price.index = price.index.astype(str)
    return price


def machine_name(machine_id: str) -> str:
    return machines().display_name[machine_id]


def site_name(site_id: str) -> str:
    return sites().name[site_id]


def operation_name(code: str) -> str:
    return OTHER_NAMES.get(code) or operations().display_name[code]


def client_name(client_id) -> str:
    return "Unassigned" if client_id is None or client_id == UNASSIGNED or pd.isna(client_id) else clients().name[client_id]
