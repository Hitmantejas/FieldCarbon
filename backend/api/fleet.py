from typing import Literal

from fastapi import APIRouter, Query

from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.check_delivery_notes import check_delivery_notes
from backend.tools.data_quality import data_quality
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_jobs import fleet_jobs
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.fleet_report import fleet_report
from backend.tools.fleet_summary import fleet_summary
from backend.tools.reconcile_fuel import reconcile_fuel
from backend.tools.what_if import what_if

router = APIRouter(prefix="/api/fleet")


@router.get("/summary")
def get_summary(group_by: Literal["site", "machine", "operation", "month", "client", "field"] = "site", site_id: str | None = None,
                machine_id: str | None = None, client_id: str | None = None, operation_code: str | None = None,
                operator_id: str | None = None, month: str | None = None):
    return fleet_summary(group_by, site_id, machine_id, client_id, operation_code, operator_id, month)


@router.get("/jobs")
def get_jobs(site_id: str | None = None, machine_id: str | None = None, client_id: str | None = None, operation_code: str | None = None,
             field_id: str | None = None, month: str | None = None, operator_id: str | None = None,
             sort: Literal["date", "litres", "hours"] = "date", limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0)):
    return fleet_jobs(site_id, machine_id, client_id, operation_code, field_id, month, operator_id, sort, limit, offset)


@router.get("/clients")
def get_clients(client_id: str | None = None):
    return emissions_per_client(client_id)


@router.get("/data-quality")
def get_data_quality():
    return data_quality()


@router.get("/reconciliation")
def get_reconciliation():
    return reconcile_fuel()


@router.get("/benchmark")
def get_benchmark(site_id: str | None = None, operation_code: str | None = None):
    return benchmark_peers(site_id, operation_code)


@router.get("/anomalies")
def get_anomalies():
    return detect_anomalies()


@router.get("/opportunities")
def get_opportunities(site_id: str | None = None, tyre_pressure_checked: bool | None = None, has_ctis: bool | None = None,
                      ballast_type: Literal["liquid", "none"] | None = None):
    given = {"tyre_pressure_checked": tyre_pressure_checked, "has_ctis": has_ctis, "ballast_type": ballast_type}
    return fleet_opportunities(site_id, {k: v for k, v in given.items() if v is not None})


@router.get("/what-if")
def get_what_if(change: Literal["implement_not_working", "peer_outliers", "hvo"], amount_pct: float = Query(gt=0, le=100),
                site_id: str | None = None):
    return what_if(change, amount_pct, site_id)


@router.get("/report")
def get_report(client_id: str | None = None):
    return fleet_report(client_id)


@router.get("/delivery-notes")
def get_delivery_notes():
    return check_delivery_notes()
