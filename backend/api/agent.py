from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent import fleet_agent

router = APIRouter(prefix="/api/agent")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@router.post("/ask")
def ask(body: Question):
    """Ask the fleet analyst one question. Tool outputs stay on the server; the reply carries the answer, which tools
    were called, and whether every number in the answer traced back to a tool."""
    try:
        r = fleet_agent.ask(body.question.strip())
    except Exception as e:  # noqa: BLE001 - the model endpoint failing is an answer for the user, not a crash
        raise HTTPException(502, "The analyst could not be reached. Check the Vertex AI login and try again.") from e
    return {"question": r["question"], "answer": r["answer"], "attempts": r["attempts"], "audit": r["audit"], "tokens": r["tokens"],
            "tools_called": [{"name": c["name"], "args": c["args"]} for c in r["tool_calls"]]}
