from typing import Literal

from fastapi import APIRouter

from backend.tools.data_quality import data_quality
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_summary import fleet_summary
from backend.tools.reconcile_fuel import reconcile_fuel

router = APIRouter(prefix="/api/fleet")


@router.get("/summary")
def get_summary(group_by: Literal["site", "machine", "operation", "month", "client"] = "site", site_id: str | None = None,
                machine_id: str | None = None, client_id: str | None = None, operation_code: str | None = None,
                operator_id: str | None = None, month: str | None = None):
    return fleet_summary(group_by, site_id, machine_id, client_id, operation_code, operator_id, month)


@router.get("/clients")
def get_clients(client_id: str | None = None):
    return emissions_per_client(client_id)


@router.get("/data-quality")
def get_data_quality():
    return data_quality()


@router.get("/reconciliation")
def get_reconciliation():
    return reconcile_fuel()
