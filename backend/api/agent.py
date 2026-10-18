import json
import queue
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agent import fleet_agent
from backend.api.limits import AskLimiter, Refused, caller_of

router = APIRouter(prefix="/api/agent")
limiter = AskLimiter.from_env()
UNREACHABLE = "The analyst could not be reached. Check the Vertex AI login and try again."


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    session_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")  # from an earlier answer, to ask a follow-up


def _admit(request: Request) -> None:
    caller = caller_of(request.headers.get("x-forwarded-for"), request.client.host if request.client else None)
    try:  # counted before the model is called: a failed call may still have spent tokens
        limiter.admit(caller)
    except Refused as e:
        raise HTTPException(429, e.message, headers={"Retry-After": str(e.retry_after_s)}) from e


def _reply(r: dict) -> dict:
    return {"question": r["question"], "answer": r["answer"], "attempts": r["attempts"], "audit": r["audit"], "tokens": r["tokens"],
            "tools_called": [{"name": c["name"], "args": c["args"]} for c in r["tool_calls"]],
            "session_id": r["session_id"], "new_session": r["new_session"], "session_note": r["session_note"]}


@router.post("/ask")
def ask(body: Question, request: Request):
    """Ask the fleet analyst one question, or a follow-up with the session_id of an earlier answer (an ended conversation
    starts a new one and the reply says so). Tool outputs stay on the server; the reply carries the answer, which tools
    were called, and whether every number in the answer traced back to a tool."""
    _admit(request)
    try:
        r = fleet_agent.ask(body.question.strip(), session_id=body.session_id)
    except Exception as e:  # noqa: BLE001 - the model endpoint failing is an answer for the user, not a crash
        raise HTTPException(502, UNREACHABLE) from e
    return _reply(r)


@router.post("/ask/stream")
def ask_stream(body: Question, request: Request):
    """The same question and answer as /ask, as server-sent events: one event per step the analyst takes (tool call, tool
    result, audit, rewrite), then a last `answer` event with the reply (or an `error` event). Tool outputs stay on the server."""
    _admit(request)
    steps: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            r = fleet_agent.ask(body.question.strip(), session_id=body.session_id, on_step=steps.put)
            steps.put({"step": "answer", **_reply(r)})
        except Exception:  # noqa: BLE001 - reported to the user as an event, as /ask does with a 502
            steps.put({"step": "error", "message": UNREACHABLE})
        steps.put(None)

    threading.Thread(target=work, daemon=True).start()

    def events():
        while (item := steps.get()) is not None:
            yield "data: " + json.dumps(item) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
