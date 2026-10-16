from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.agent import fleet_agent
from backend.api.limits import AskLimiter, Refused, caller_of

router = APIRouter(prefix="/api/agent")
limiter = AskLimiter.from_env()


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    session_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")  # from an earlier answer, to ask a follow-up


@router.post("/ask")
def ask(body: Question, request: Request):
    """Ask the fleet analyst one question, or a follow-up with the session_id of an earlier answer (an ended conversation
    starts a new one and the reply says so). Tool outputs stay on the server; the reply carries the answer, which tools
    were called, and whether every number in the answer traced back to a tool."""
    caller = caller_of(request.headers.get("x-forwarded-for"), request.client.host if request.client else None)
    try:  # counted before the model is called: a failed call may still have spent tokens
        limiter.admit(caller)
    except Refused as e:
        raise HTTPException(429, e.message, headers={"Retry-After": str(e.retry_after_s)}) from e
    try:
        r = fleet_agent.ask(body.question.strip(), session_id=body.session_id)
    except Exception as e:  # noqa: BLE001 - the model endpoint failing is an answer for the user, not a crash
        raise HTTPException(502, "The analyst could not be reached. Check the Vertex AI login and try again.") from e
    return {"question": r["question"], "answer": r["answer"], "attempts": r["attempts"], "audit": r["audit"], "tokens": r["tokens"],
            "tools_called": [{"name": c["name"], "args": c["args"]} for c in r["tool_calls"]],
            "session_id": r["session_id"], "new_session": r["new_session"], "session_note": r["session_note"]}
