import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from backend.agent import briefing_text, diagnosis_text, statement_text
from backend.agent.gemini_text import vertex_generate
from backend.api.limits import AskLimiter, Refused, caller_of

from backend.tools import upload_note, voice_note
from backend.tools.action_impact import action_impact
from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.carbon_ledger import carbon_ledger
from backend.tools.check_delivery_notes import check_delivery_notes
from backend.tools.client_statement import client_statement
from backend.tools.data_quality import data_quality
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.diagnose_anomaly import diagnose_anomaly
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_jobs import fleet_jobs
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.fleet_report import fleet_report
from backend.tools.fleet_summary import fleet_summary
from backend.tools.reconcile_fuel import reconcile_fuel
from backend.tools.weekly_briefing import weekly_briefing
from backend.tools.trust_scoreboard import trust_scoreboard
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


@router.get("/ledger")
def get_ledger(goal_pct: float = Query(20, ge=1, le=90), tyre_pressure_checked: bool | None = None,
               has_ctis: bool | None = None, ballast_type: Literal["liquid", "none"] | None = None):
    given = {"tyre_pressure_checked": tyre_pressure_checked, "has_ctis": has_ctis, "ballast_type": ballast_type}
    return carbon_ledger(goal_pct, {k: v for k, v in given.items() if v is not None})


@router.get("/actions")
def get_actions(action_id: str | None = None):
    try:
        return action_impact(action_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/trust")
def get_trust():
    return trust_scoreboard()


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
GEN_MESSAGES = ("Today's limit of Gemini requests has been reached. Try again tomorrow.",
                "You can make {n} Gemini requests a minute. Please wait a moment and try again.")
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


# F5 anomaly diagnosis
diagnosis_generate = vertex_generate
_diagnosis_cache: dict[str, dict] = {}
_diagnosis_lock = threading.Lock()


@router.get("/diagnosis")
def get_diagnosis(request: Request, finding_id: str = Query(min_length=1, max_length=120), narrate: bool = False):
    """Possible causes of one finding, each tested against the data by code. `narrate=true` adds Gemini's one-line
    reasons, up to two untested ideas and a checked summary; it never changes a result or the order."""
    try:
        d = diagnose_anomaly(finding_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    if not narrate:
        return d
    with _diagnosis_lock:
        cached = _diagnosis_cache.get(finding_id)
    if cached is not None:
        return cached
    _admit(request)
    try:
        out = diagnosis_text.explain(d, diagnosis_generate)
    except Exception as e:  # noqa: BLE001 - the checks or the fixed wording failed; the tests are still at narrate=false
        raise HTTPException(502, "The explanation could not be written. The tested causes are still shown.") from e
    if out["summary"]["error"] is None:  # a model outage is not cached, so a reload can try again
        with _diagnosis_lock:
            _diagnosis_cache[finding_id] = out
    return out


# F6 weekly briefing
briefing_writer = briefing_text.writer
_briefing_cache: dict[str, dict] = {}
_briefing_lock = threading.Lock()


@router.get("/briefing")
def get_briefing(request: Request, language: Literal["en", "de", "es", "hi"] = "en", narrate: bool = False):
    """The three things to look at first, chosen by fixed rules, with a short intro. `narrate=true` has Gemini write the
    intro (code checks every number); otherwise, and on any failure, the standard wording is shown."""
    b = weekly_briefing()
    with _briefing_lock:
        cached = _briefing_cache.get(language)
    if narrate and cached is None:
        _admit(request)
    try:
        if not narrate:
            text, written_in = briefing_text.template(briefing_text.gemini_facts(b), language)
            intro = {"text": text, "narrative_source": "template", "narrative_language": written_in, "audited": False,
                     "attempts": 0, "numbers_checked": 0, "usage": None, "error": None}
        else:
            intro = cached or briefing_text.narrate_briefing(b, language, briefing_writer(language))
    except Exception as e:  # noqa: BLE001 - the standard wording itself failed; the items come from code
        raise HTTPException(502, "The briefing intro could not be written. The items are still on the Overview.") from e
    if narrate and cached is None and intro["error"] is None:  # a model outage is not cached, so a reload can try again
        with _briefing_lock:
            _briefing_cache[language] = intro
    return {**b, "language": language, "intro": intro}


# F7 live delivery-note upload
note_reader = upload_note.read_uploaded_note
TOO_BIG = "The photo is over 5 MB. Please send a smaller photo of the note."


async def _read_body(request: Request, max_bytes: int, too_big: str, empty: str) -> bytes:
    """The raw upload, refused (413) as soon as it is over the cap by its header or by what has arrived; kept in memory only."""
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > max_bytes:
        raise HTTPException(413, too_big)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > max_bytes:
            raise HTTPException(413, too_big)
    if not body:
        raise HTTPException(400, empty)
    return bytes(body)


@router.post("/delivery-notes/check")
async def post_delivery_note_check(request: Request):
    """One delivery-note photo as the raw request body (Content-Type image/jpeg, image/png or image/webp, up to 5 MB):
    Gemini reads it, rules R1-R8 and the fuel-log comparison check it. Nothing is saved; no filename is used; the image
    is never logged. Every refusal happens before the model is called and does not count against the limit."""
    mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime not in upload_note.MAGIC:
        raise HTTPException(415, "Only JPEG, PNG or WebP photos can be read. Take a photo of the note and send that.")
    image = await _read_body(request, upload_note.MAX_BYTES, TOO_BIG, "The upload was empty. Choose a photo of a delivery note.")
    if not upload_note.image_type_matches(image, mime):
        raise HTTPException(422, f"The file does not look like a {mime.split('/')[1].upper()} image. Choose a photo of the note.")
    _admit(request)
    try:
        reading = await run_in_threadpool(note_reader, image, mime)
    except Exception as e:  # noqa: BLE001 - any model or network failure; no detail reaches the client
        raise HTTPException(502, "Gemini could not read the note just now. Nothing was saved. Please try again in a minute.") from e
    try:
        result = upload_note.check_uploaded_note(reading["read"])
    except Exception as e:  # noqa: BLE001 - a reading the rules cannot process
        raise HTTPException(502, "The note was read but could not be checked. Nothing was saved. Try a clearer photo.") from e
    return {**result, "read": reading["read"], "usage": reading["usage"], "model_version": reading["model_version"],
            "data_source": upload_note.DATA_SOURCE}


# P2a voice notes
voice_reader = voice_note.read_voice_note
TOO_LONG = "The recording is over 2 MB (about a minute). Please record a shorter note."


@router.post("/voice-notes/read")
async def post_voice_note(request: Request):
    """One short voice note as the raw request body (audio/webm, ogg, mp4/m4a, mpeg or wav, up to 2 MB): Gemini hears
    which machine and what problem, and code checks the note against the fleet list. Nothing is saved; no filename is
    used; the audio is never logged. Every refusal happens before the model is called and does not count against the limit."""
    mime = voice_note.normal_type(request.headers.get("content-type", "").split(";")[0].strip().lower())
    if mime is None:
        raise HTTPException(415, "Only a voice recording (WebM, Ogg, M4A, MP3 or WAV) can be read. Record the note and send that.")
    audio = await _read_body(request, voice_note.MAX_BYTES, TOO_LONG, "The upload was empty. Record a voice note first.")
    if not voice_note.audio_type_matches(audio, mime):
        raise HTTPException(422, "The file does not look like a voice recording of the type it was sent as. Record the note again.")
    _admit(request)
    try:
        reading = await run_in_threadpool(voice_reader, audio, mime)
        result = voice_note.check_voice_note(reading["heard"])
    except Exception as e:  # noqa: BLE001 - any model or network failure; no detail reaches the client
        raise HTTPException(502, "Gemini could not hear the note just now. Nothing was saved. Please try again in a minute.") from e
    return {**result, "usage": reading["usage"], "model_version": reading["model_version"]}
