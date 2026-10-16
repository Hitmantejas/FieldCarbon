import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from backend.agent import statement_text
from backend.api.limits import AskLimiter, Refused, caller_of

from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.check_delivery_notes import check_delivery_notes
from backend.tools.client_statement import client_statement
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


# Gemini-written texts (F4 statement; later the diagnosis, briefing and upload): one limiter for all of them.
GEN_MESSAGES = ("Today's limit of texts written by Gemini has been reached. Try again tomorrow.",
                "You can ask for {n} texts written by Gemini a minute. Please wait a moment and try again.")
gen_limiter = AskLimiter.from_env(minute_var="FIELDCARBON_GEN_PER_MINUTE", day_var="FIELDCARBON_GEN_PER_DAY", defaults=(6, 300),
                                  messages=GEN_MESSAGES)


def _admit(request: Request) -> None:
    """Count one Gemini call for this caller, before the model is called (a failed call may still have spent tokens)."""
    try:
        gen_limiter.admit(caller_of(request.headers.get("x-forwarded-for"), request.client.host if request.client else None))
    except Refused as e:
        raise HTTPException(429, e.message, headers={"Retry-After": str(e.retry_after_s)}) from e


# F4 client statement
statement_writer = statement_text.writer
_statement_cache: dict[tuple[str, str], dict] = {}
_statement_lock = threading.Lock()


@router.get("/client-statement")
def get_client_statement(request: Request, client_id: str, language: Literal["en", "de", "es", "hi"] = "en", narrate: bool = True):
    """One client farm's statement with a short summary in its language. Gemini writes the summary and code checks every
    number in it; `narrate=false` gives the standard wording without calling the model. Repeat views come from a cache."""
    try:
        s = client_statement(client_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    key = (client_id, language)
    with _statement_lock:
        cached = _statement_cache.get(key)
    if narrate and cached is None:
        _admit(request)
    try:
        if not narrate:
            text, written_in = statement_text.template(statement_text.gemini_facts(s), language)
            narrative = {"text": text, "narrative_source": "template", "narrative_language": written_in, "audited": False,
                         "attempts": 0, "numbers_checked": 0, "usage": None, "error": None}
        else:
            narrative = cached or statement_text.narrate_statement(s, language, statement_writer(language))
    except Exception as e:  # noqa: BLE001 - the standard wording itself failed; numbers come from the other endpoints
        raise HTTPException(502, "The statement summary could not be written. The figures are still on the client report.") from e
    if narrate and cached is None and narrative["error"] is None:  # a model outage is not cached, so a reload can try again
        with _statement_lock:
            _statement_cache[key] = narrative
    return {**s, "language": language, "narrative": narrative}
