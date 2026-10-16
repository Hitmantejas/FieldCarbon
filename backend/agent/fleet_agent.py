"""The fleet analyst: a Google ADK agent on Gemini (Vertex AI) that turns a question into calls to the deterministic tools.

Gemini plans which tools to call and explains their results in plain English. Every figure comes from a tool
(CLAUDE.md principle 1). Before an answer leaves `ask()`, the auditor checks that each number traces to a tool output,
and coverage checks that each figure has its label and each idea its source; an answer that fails is rewritten once with
the problems named, and if a number still does not trace it carries a visible note. `ask()` can also record the run for
the eval harness (evals/run_all.py).
"""
from __future__ import annotations

import asyncio
import os
import uuid

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from backend.agent.coverage import uncited_ideas, unlabelled_sentences, unrounded_numbers
from backend.agent.faithfulness import audit, guard
from backend.agent.runs import record_run
from backend.agent.tools import AGENT_TOOLS

APP = "fieldcarbon"
AGENT_VERSION = "analyst-v3"  # v2: one rewrite also covers ideas without a source and figures without a label; v3: and unrounded figures
MODEL = os.environ.get("FIELDCARBON_GEMINI_MODEL", "gemini-3.5-flash")

INSTRUCTION = """You are FieldCarbon's fleet analyst. You help the fleet manager and the sustainability lead of an agricultural \
contractor understand fuel use and emissions across sites, machines, jobs, fields and client farms. The company year is \
May 2025 to April 2026. All data is demo data.

How to work
- Call the tools to answer. You never calculate, round differently, add up, subtract or work out percentages yourself.
  Use a number only if a tool returned it, written as the tool gives it (you may round as a person would, like \
10,814 litres for 10,813.7). If the answer needs a number no tool gave, say it is not available.
- Pick the fewest tools that answer the question. Fuel, CO2e and cost totals: fleet_summary. Per client: emissions_per_client. \
How far to trust the data: data_quality. Fuel that does not add up, double entries, night fuel: reconcile_fuel. Delivery notes \
against the fuel log: check_delivery_notes. Odd jobs or recorders: detect_anomalies. Machines burning more than similar machines: \
benchmark_peers. Tonnes of CO2e emitted, avoidable or proven, and progress to a reduction goal: carbon_ledger. \
What to change to save fuel: fleet_opportunities. A change the user wants to try: what_if. Individual jobs: \
fleet_jobs. A report or client statement: fleet_report.
- Round the way a person would: whole litres, whole pounds, tonnes with one decimal (29,819 kg is 29.8 tonnes). Never print long decimals.
  Write thousands with a comma in every language (16,492 litres), so every figure reads the same way.
  Never write a minus sign: say "extra", "more", "less" or "a higher fuel bill" in words.
- Say the confidence label next to every figure, in the same sentence, also in bullet points and comparisons: measured, \
allocated or estimated, for example "10,814 litres (allocated)". Give ranges as ranges, never as one number. Savings are \
estimates, never guarantees.
- Differences between machines and findings are things to investigate, not proof of a fault, waste or loss. Say so.
- Recommend only what fleet_opportunities returns, and name the research source and the strength of evidence for it, using the \
source title exactly. Name the source every time you name an idea, also when the same idea comes up again for another site. \
Ideas overlap, so never add their savings together.
- Never name, rank or compare operators. If asked, say FieldCarbon does not report on individual people.
- If a tool returns an error, fix the arguments and try again. If the data cannot answer, say what is missing.

How to answer
- Reply in the language of the question. Plain, short sentences. Lead with the answer, then at most four short bullet points.
- Write for a manager, not an analyst: litres, hectares, tonnes of CO2, pounds. No tool names, ids or jargon in the answer.
- Finish with one practical next step when there is one. Mention the Reports screen when someone asks for a report."""


def build_agent(model=None) -> Agent:
    return Agent(name="fleet_analyst", model=model or _vertex_model(), instruction=INSTRUCTION, tools=AGENT_TOOLS,
                 generate_content_config=types.GenerateContentConfig(temperature=0))


def _vertex_model() -> str:
    """The model name, with ADK pointed at Vertex AI (credentials come from the environment, never from a key)."""
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("FIELDCARBON_PROJECT", "ai-hackathon-india"))
    # Decided 2026-10-14: gemini-3.5-flash is offered on "global", not on "us-central1".
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.environ.get("FIELDCARBON_GEMINI_LOCATION", "global"))
    return MODEL


class Turn:
    """What one model turn produced: the final text, the tool calls and their outputs, and the tokens used."""

    def __init__(self) -> None:
        self.text = ""
        self.calls: list[dict] = []
        self.tokens = {"input": 0, "output": 0, "thinking": 0}

    def add(self, event) -> None:
        pending = {}
        for c in event.get_function_calls():
            call = {"name": c.name, "args": dict(c.args or {}), "output": None}
            self.calls.append(call)
            pending[c.id or c.name] = call
        for r in event.get_function_responses():
            call = pending.get(r.id or r.name) or next((x for x in reversed(self.calls) if x["name"] == r.name and x["output"] is None), None)
            if call is not None:
                call["output"] = r.response
        u = event.usage_metadata
        if u:
            self.tokens["input"] += u.prompt_token_count or 0
            self.tokens["output"] += u.candidates_token_count or 0
            self.tokens["thinking"] += u.thoughts_token_count or 0
        if event.is_final_response() and event.content and event.content.parts:
            self.text = "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False)).strip()


async def _turn(runner: Runner, user_id: str, session_id: str, message: str) -> Turn:
    turn = Turn()
    content = types.Content(role="user", parts=[types.Part(text=message)])
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        turn.add(event)
    return turn


async def _ask(agent: Agent, question: str, retry: bool) -> dict:
    sessions = InMemorySessionService()
    runner = Runner(app_name=APP, agent=agent, session_service=sessions)
    user, sid = "analyst-user", uuid.uuid4().hex
    await sessions.create_session(app_name=APP, user_id=user, session_id=sid)

    turn = await _turn(runner, user, sid, question)
    calls, answer, tokens, attempts = list(turn.calls), turn.text, dict(turn.tokens), 1
    verdict = _verdict(answer, calls, question)
    gaps = _gaps(answer, calls)
    if (not verdict.faithful or any(gaps.values())) and retry:
        again = await _turn(runner, user, sid, rewrite_request(verdict.unmatched, **gaps))
        all_calls = calls + again.calls
        tokens = {k: tokens[k] + again.tokens[k] for k in tokens}
        attempts = 2
        second = _verdict(again.text, all_calls, question) if again.text else None
        if second is not None and (second.faithful or not verdict.faithful):  # never trade a traced answer for an untraced one
            answer, verdict = again.text, second
        calls = all_calls
        gaps = _gaps(answer, calls)
    if not verdict.faithful:
        _, note = guard(answer, [c["output"] for c in calls], question)
        answer = f"{answer}\n\n{note}"
    return {"question": question, "answer": answer, "tool_calls": calls, "attempts": attempts,
            "audit": {"faithful": verdict.faithful, "numbers_checked": verdict.checked, "untraced": [n.text for n in verdict.unmatched],
                      "uncited_ideas": [g["name"] for g in gaps["uncited"]], "unlabelled_sentences": len(gaps["unlabelled"]),
                      "unrounded": gaps["unrounded"]},
            "tokens": tokens}


def _gaps(answer: str, calls: list[dict]) -> dict:
    outputs = [c["output"] for c in calls]
    return {"uncited": uncited_ideas(answer, outputs), "unlabelled": unlabelled_sentences(answer), "unrounded": unrounded_numbers(answer)}


def rewrite_request(unmatched, uncited=(), unlabelled=(), unrounded=()) -> str:
    """The one retry message. A number whose size is in the tools but whose saving/increase is turned round is named
    as such, so the model fixes the words instead of hunting for a number it already has. Ideas named without their
    source, sentences with a figure but no confidence label, and figures with needless decimals are named too."""
    invented = ", ".join(dict.fromkeys(n.text for n in unmatched if not n.wrong_direction))
    flipped = ", ".join(dict.fromkeys(n.text for n in unmatched if n.wrong_direction))
    parts = []
    if invented:
        parts.append(f"These numbers in your answer did not come from the tools: {invented}. Rewrite them using only numbers "
                     "the tool results contain, written as they appear. If a number is not available, say so instead of working it out.")
    if flipped:
        parts.append(f"These numbers are in the tool results, but your answer gives them the opposite direction (a saving where "
                     f"the tools show an increase, or the other way round): {flipped}. Keep the numbers and describe the direction "
                     "the tools give.")
    if uncited:
        named = "; ".join(f'{g["name"]} (source: {" / ".join(g["titles"][:2])})' for g in uncited)
        parts.append(f"These ideas are named without their research source: {named}. Name the source title next to each idea, "
                     "every time it appears, including for a second site.")
    if unlabelled:
        quoted = " | ".join(s[:120] for s in unlabelled[:4])
        parts.append(f"These sentences give a figure without its confidence label: {quoted}. Add measured, allocated or "
                     "estimated in the same sentence, as the tool results give it.")
    if unrounded:
        parts.append(f"These figures have more decimals than a person would write: {', '.join(unrounded)}. Round them as a person "
                     "would (whole litres, whole pounds, tonnes with one decimal), with a comma for thousands in every language (16,492).")
    return " ".join(parts) + " Rewrite the whole answer."


def _verdict(answer: str, calls: list[dict], question: str):
    return audit(answer, [c["output"] for c in calls], question)


def ask(question: str, model=None, retry: bool = True, record: bool = False, case_id: str | None = None,
        record_file: str = "agent.jsonl") -> dict:
    """Answer one question. `model` is a model name or an ADK model object (tests pass a scripted one)."""
    agent = build_agent(model)
    result = asyncio.run(_ask(agent, question, retry))
    result["model"] = model if isinstance(model, str) or model is None else type(model).__name__
    if record:
        record_run(case_id, question, [{"name": c["name"], "args": c["args"], "output": c["output"]} for c in result["tool_calls"]],
                   result["answer"], result["model"] or MODEL, AGENT_VERSION, record_file, tokens=result["tokens"])
    return result
