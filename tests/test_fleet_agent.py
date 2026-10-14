"""The analyst agent, run offline against a scripted model: tool calls, audit, one rewrite, and recording."""
import json

import pytest
from google.adk.models import BaseLlm, LlmResponse
from google.genai import types

from backend.agent import fleet_agent, runs
from backend.agent.tools import AGENT_TOOLS


class Scripted(BaseLlm):
    """A stand-in for Gemini: first asks for the given tool calls, then replies with each scripted answer in turn."""

    model: str = "scripted"
    calls: list = []
    answers: list = []
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        self.seen.append(llm_request)
        last = llm_request.contents[-1]
        has_result = any(p.function_response for p in last.parts or [])
        asked_again = last.role == "user" and not any(p.function_response for p in last.parts or []) and len(llm_request.contents) > 1
        if not has_result and not asked_again:
            parts = [types.Part.from_function_call(name=n, args=a) for n, a in self.calls]
        else:
            parts = [types.Part(text=self.answers.pop(0))]
        yield LlmResponse(content=types.Content(role="model", parts=parts))


def run(answers, calls=(("fleet_summary", {"group_by": "site"}),), **kw):
    return fleet_agent.ask("How much fuel did the fleet use, by site?", model=Scripted(calls=list(calls), answers=list(answers), seen=[]), **kw)


def test_the_agent_offers_every_tool_and_the_rules_to_the_model():
    m = Scripted(calls=[("fleet_summary", {})], answers=["Done."], seen=[])
    fleet_agent.ask("hi", model=m)
    req = m.seen[0]
    assert {t.__name__ for t in AGENT_TOOLS} <= set(req.tools_dict)
    assert "never calculate" in req.config.system_instruction.lower() or "You never calculate" in req.config.system_instruction
    assert "operators" in req.config.system_instruction


def test_a_faithful_answer_passes_the_audit_with_the_tool_calls_recorded():
    r = run(["The Arable site (Bavaria) burned 10,814 litres (allocated), 65.6% of the fleet's fuel."])
    assert r["audit"]["faithful"] and r["attempts"] == 1 and "Check needed" not in r["answer"]
    assert r["tool_calls"][0]["name"] == "fleet_summary" and r["tool_calls"][0]["output"]["rows"]


def test_an_invented_number_is_rewritten_once_and_then_passes():
    r = run(["The fleet used 31,000 litres.", "The fleet used 16,492 litres (allocated)."])
    assert r["attempts"] == 2 and r["audit"]["faithful"] and "31,000" not in r["answer"]


def test_an_answer_that_stays_unfaithful_carries_a_visible_note_and_a_failed_audit():
    r = run(["The fleet used 31,000 litres.", "The fleet used 32,000 litres."])
    assert not r["audit"]["faithful"] and "Check needed" in r["answer"] and "32,000" in r["audit"]["untraced"][0]


def test_retry_can_be_switched_off():
    assert run(["The fleet used 31,000 litres."], retry=False)["attempts"] == 1


def test_a_recorded_run_is_scored_by_the_harness_and_not_marked_as_a_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "RUNS", tmp_path)
    monkeypatch.setattr(fleet_agent, "record_run", lambda *a, **k: runs.record_run(*a, **k))
    run(["The fleet used 16,492 litres (allocated)."], record=True, case_id="fleet-summary")
    saved = [json.loads(line) for line in (tmp_path / "agent.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved[0]["case_id"] == "fleet-summary" and saved[0]["sample"] is False
    assert saved[0]["tool_calls"][0]["output"]["rows"]
    assert set(saved[0]["tokens"]) == {"input", "output", "thinking"}  # the basis for the cost per question
