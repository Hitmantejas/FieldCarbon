"""Recording live agent runs: a run that fails part-way never touches the answers already recorded."""
import json

import pytest

from evals import run_agent

CASES = [{"id": "fleet-a", "question": "qa", "expected_tools": []}, {"id": "fleet-b", "question": "qb", "expected_tools": []},
         {"id": "mt-c", "earlier_turns": ["c1", "c2"], "question": "qc", "expected_tools": ["fleet_summary"]}]


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    monkeypatch.setattr(run_agent, "RUNS", tmp_path)
    monkeypatch.setattr(run_agent, "questions", lambda only=None: [c for c in CASES if not only or c["id"] in only])
    fail_on, asked = set(), []

    def ask(question, record=False, case_id=None, record_file=None, session_id=None):
        if case_id in fail_on:
            raise RuntimeError("Vertex AI unavailable")
        asked.append((question, session_id, record))
        if record:
            with (tmp_path / record_file).open("a", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": case_id, "answer": "new"}) + "\n")
        calls = [{"name": "fleet_summary"}] if question == "c1" else []
        return {"tokens": {"input": 1, "output": 1, "thinking": 0}, "tool_calls": calls, "audit": {"faithful": True}, "attempts": 1,
                "session_id": session_id or f"sid-{question}"}
    monkeypatch.setattr(run_agent.fleet_agent, "ask", ask)
    old = "".join(json.dumps({"case_id": c["id"], "answer": "old"}) + "\n" for c in CASES)
    (tmp_path / "agent.jsonl").write_text(old, encoding="utf-8")
    return tmp_path, old, fail_on, asked


def answers(path):
    return {r["case_id"]: r["answer"] for r in map(json.loads, (path / "agent.jsonl").read_text(encoding="utf-8").splitlines())}


def test_a_run_that_fails_part_way_leaves_the_recorded_answers_as_they_were(recorder):
    path, old, fail_on, _ = recorder
    fail_on.add("fleet-b")
    with pytest.raises(RuntimeError):
        run_agent.main()
    assert (path / "agent.jsonl").read_text(encoding="utf-8") == old


def test_a_run_of_some_cases_replaces_only_those(recorder):
    path, *_ = recorder
    run_agent.main(["fleet-b"])
    assert answers(path) == {"fleet-a": "old", "fleet-b": "new", "mt-c": "old"} and not (path / "agent.jsonl.partial").exists()


def test_a_full_run_replaces_every_answer(recorder):
    path, *_ = recorder
    run_agent.main()
    assert answers(path) == {"fleet-a": "new", "fleet-b": "new", "mt-c": "new"}


def test_a_multi_turn_case_asks_its_earlier_turns_in_one_conversation_and_records_only_the_last(recorder, capsys):
    path, *_, asked = recorder
    run_agent.main(["mt-c"])
    assert asked == [("c1", None, False), ("c2", "sid-c1", False), ("qc", "sid-c1", True)]
    assert answers(path)["mt-c"] == "new" and "tools=ok" in capsys.readouterr().out   # a tool called in an earlier turn counts


def test_the_agent_flag_not_the_id_decides_which_cases_are_asked(monkeypatch):
    monkeypatch.setattr(run_agent, "CASES", [{"id": "refuse-x", "agent": True, "question": "q", "expected_tools": []},
                                             {"id": "fleet-tool-only", "question": "q", "expected_tools": ["fleet_summary"]}])
    assert [c["id"] for c in run_agent.questions()] == ["refuse-x"]


def test_every_agent_case_has_a_question_and_a_tool_list():
    asked = run_agent.questions()
    assert len(asked) >= 21 and all(c["question"].strip() and isinstance(c["expected_tools"], list) for c in asked)
