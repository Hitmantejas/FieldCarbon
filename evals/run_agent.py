"""Ask the live analyst every eval question and record the runs for the harness.

  python -m evals.run_agent            -> evals/runs/agent.jsonl (replaced; with case ids, only those), then `python -m evals.run_all` scores it

Makes real calls to Gemini on Vertex AI, about 6,000 tokens a question. Pass case ids to run only those.
A multi-turn case asks its `earlier_turns` first in one conversation; only the last question (`question`) is recorded,
with every tool output of the conversation, since its answer may repeat an earlier figure.
"""
from __future__ import annotations

import json
import sys
import time

from backend.agent import fleet_agent
from backend.agent.runs import RUNS
from evals.checks import CASES

FILE = "agent.jsonl"


def questions(only: list[str] | None = None) -> list[dict]:
    asked = [c for c in CASES if c.get("agent") and c.get("question")]
    return [c for c in asked if not only or c["id"] in only]


def ask_case(case: dict, record_file: str) -> tuple[dict, set[str], dict]:
    """Ask a case (its earlier turns first, in one conversation); returns the last answer, every tool called and all tokens."""
    sid, called, used = None, set(), {"input": 0, "output": 0, "thinking": 0}
    for q in case.get("earlier_turns", []):
        r = fleet_agent.ask(q, session_id=sid)
        sid, called, used = r["session_id"], called | {c["name"] for c in r["tool_calls"]}, {k: used[k] + r["tokens"][k] for k in used}
    r = fleet_agent.ask(case["question"], record=True, case_id=case["id"], record_file=record_file, session_id=sid)
    return r, called | {c["name"] for c in r["tool_calls"]}, {k: used[k] + r["tokens"][k] for k in used}


def main(only: list[str] | None = None) -> None:
    cases = questions(only)
    path, partial = RUNS / FILE, RUNS / f"{FILE}.partial"   # .partial is not *.jsonl, so the harness never scores it
    RUNS.mkdir(parents=True, exist_ok=True)
    partial.unlink(missing_ok=True)
    used = {"input": 0, "output": 0, "thinking": 0}
    for i, case in enumerate(cases, 1):
        start = time.time()
        r, called, spent = ask_case(case, partial.name)
        used = {k: used[k] + spent[k] for k in used}
        print(f"{i:>2}/{len(cases)} {case['id']:<22} {time.time() - start:4.0f}s tools={'ok' if set(case['expected_tools']) <= called else 'MISSED'} "
              f"faithful={r['audit']['faithful']} attempts={r['attempts']}", flush=True)
    # Only now, with every question answered, replace the recorded runs: a failed run leaves the old ones as they were.
    new = partial.read_text(encoding="utf-8").splitlines() if partial.exists() else []
    old = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [l for l in old if only and json.loads(l)["case_id"] not in only]   # a partial run replaces only its own cases
    path.write_text("".join(f"{l}\n" for l in kept + new), encoding="utf-8")
    partial.unlink(missing_ok=True)
    print("tokens", used)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
