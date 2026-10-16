"""Follow-up questions (F8 B): one conversation per session id, audited across turns, with time, count and history limits.
Run offline against a scripted model."""
import json

import pytest
from google.adk.models import BaseLlm, LlmResponse
from google.genai import types

from backend.agent import fleet_agent, runs

FIRST = "How much fuel did the fleet use, by site?"
TRACED = "The Arable site (Bavaria) burned 10,814 litres (allocated)."


class Steps(BaseLlm):
    """A stand-in for Gemini that plays its steps in order: ("call", name, args) asks for a tool, ("text", answer) replies."""

    model: str = "steps"
    steps: list = []
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        self.seen.append(llm_request)
        kind, *rest = self.steps.pop(0)
        part = types.Part.from_function_call(name=rest[0], args=rest[1]) if kind == "call" else types.Part(text=rest[0])
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def model(*steps):
    return Steps(steps=list(steps), seen=[])


def first_turn(**kw):
    return fleet_agent.ask(FIRST, model=model(("call", "fleet_summary", {"group_by": "site"}), ("text", TRACED)), **kw)


def texts(request) -> str:
    return " ".join(p.text or "" for c in request.contents for p in c.parts or [])


@pytest.fixture(autouse=True)
def no_conversations(monkeypatch):
    monkeypatch.setattr(fleet_agent, "_conversations", type(fleet_agent._conversations)())


def test_a_question_without_a_session_starts_one():
    r = first_turn()
    assert len(r["session_id"]) == 32 and r["new_session"] is True and r["session_note"] is None


def test_a_follow_up_may_quote_a_number_from_an_earlier_turn_without_calling_a_tool():
    sid = first_turn()["session_id"]
    m = model(("text", "Yes: the Arable site burned 10,814 litres (allocated), the most of any site."))
    r = fleet_agent.ask("Which site used the most?", model=m, session_id=sid)
    assert r["session_id"] == sid and r["new_session"] is False
    assert r["tool_calls"] == [] and r["audit"]["faithful"] and r["attempts"] == 1
    assert FIRST in texts(m.seen[0])    # the model sees the earlier turn


def test_a_follow_up_that_invents_a_number_fails_the_audit():
    sid = first_turn()["session_id"]
    m = model(("text", "That is 31,000 litres (allocated)."), ("text", "That is 32,000 litres (allocated)."))
    r = fleet_agent.ask("And the total?", model=m, session_id=sid)
    assert r["attempts"] == 2 and not r["audit"]["faithful"] and "Check needed" in r["answer"]


def test_a_number_from_another_conversation_does_not_trace():
    first_turn()
    m = model(("text", "The Arable site burned 10,814 litres (allocated)."), ("text", "The Arable site burned 10,814 litres (allocated)."))
    r = fleet_agent.ask("Which site used the most?", model=m)
    assert r["new_session"] and not r["audit"]["faithful"]


def test_an_unknown_session_starts_a_new_one_and_says_so():
    r = first_turn(session_id="0" * 32)
    assert r["new_session"] and r["session_id"] != "0" * 32 and "new conversation" in r["session_note"]


def test_a_session_unused_for_30_minutes_has_ended(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(fleet_agent, "_clock", lambda: now[0])
    sid = first_turn()["session_id"]
    now[0] += fleet_agent.SESSION_TTL_S - 1
    assert first_turn(session_id=sid)["session_id"] == sid      # still alive; its use resets the timer
    now[0] += fleet_agent.SESSION_TTL_S + 1
    r = first_turn(session_id=sid)
    assert r["session_id"] != sid and "new conversation" in r["session_note"]


def test_the_oldest_conversation_is_dropped_beyond_the_cap(monkeypatch):
    monkeypatch.setattr(fleet_agent, "MAX_SESSIONS", 2)
    a, b = first_turn()["session_id"], first_turn()["session_id"]
    first_turn(session_id=a)          # a is now the most recently used
    first_turn()                      # a third conversation pushes out b
    assert set(fleet_agent._conversations) >= {a} and b not in fleet_agent._conversations
    assert len(fleet_agent._conversations) == 2


def test_only_the_last_turns_of_history_are_sent_to_the_model(monkeypatch):
    monkeypatch.setattr(fleet_agent, "MAX_TURNS", 2)
    sid = first_turn()["session_id"]
    fleet_agent.ask("Second question?", model=model(("text", "No figures here.")), session_id=sid)
    m = model(("text", "Still no figures."))
    fleet_agent.ask("Third question?", model=m, session_id=sid)
    sent = texts(m.seen[0])
    assert FIRST not in sent and "Second question?" in sent and "Third question?" in sent


def test_a_recorded_follow_up_carries_the_earlier_tool_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "RUNS", tmp_path)
    sid = first_turn()["session_id"]
    fleet_agent.ask("Which site used the most?", model=model(("text", "The Arable site, 10,814 litres (allocated).")),
                    session_id=sid, record=True, case_id="mt-quote-earlier")
    [saved] = [json.loads(line) for line in (tmp_path / "agent.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved["question"] == "Which site used the most?" and saved["tool_calls"][0]["name"] == "fleet_summary"
