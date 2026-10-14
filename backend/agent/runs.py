"""Recorded agent runs, scored by the eval harness (evals/run_all.py).

A run is one question answered by the agent: the tools it called (name, arguments, output) and the final
answer. The agent writes each run with `record_run`; one JSON object per line in evals/runs/*.jsonl.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path(__file__).resolve().parents[2] / "evals" / "runs"


def record_run(case_id: str | None, question: str, tool_calls: list[dict], answer: str, model: str,
               agent_version: str, file: str = "agent.jsonl", sample: bool = False, tokens: dict | None = None) -> dict:
    """Append one run. `tool_calls`: [{"name": ..., "args": {...}, "output": <tool result>}, ...].
    `sample=True` marks a hand-written run used to test the harness, never counted as agent results.
    `tokens`: what Vertex AI reported for the whole run ({"input", "output", "thinking"}), the basis for its cost."""
    run = {"case_id": case_id, "question": question, "tool_calls": tool_calls, "answer": answer, "model": model,
           "agent_version": agent_version, "sample": sample, "tokens": tokens,
           "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / file).open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False, default=str) + "\n")
    return run


def load_runs(folder: Path = RUNS) -> list[dict]:
    runs = []
    for path in sorted(folder.glob("*.jsonl")):
        runs += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return runs
