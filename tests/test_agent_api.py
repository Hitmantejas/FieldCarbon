"""The ask endpoint, with the agent stubbed: no model is called."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.agent import fleet_agent
from backend.api import agent as agent_api
from backend.api.limits import AskLimiter, caller_of
from backend.api.main import app

client = TestClient(app)
NOON = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc).timestamp()


class Clock:
    def __init__(self, t=NOON):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    """Each test starts with an empty limiter (5 a minute, 8 a day) on a clock it controls."""
    clock = Clock()
    monkeypatch.setattr(agent_api, "limiter", AskLimiter(per_minute=5, per_day=8, clock=clock))
    return clock


def ask(ip="1.1.1.1"):
    return client.post("/api/agent/ask", json={"question": "How much fuel?"}, headers={"X-Forwarded-For": ip})
FAKE = {"question": "q", "answer": "The fleet used 16,492 litres (allocated).", "attempts": 1, "tokens": {"input": 1, "output": 1, "thinking": 0},
        "audit": {"faithful": True, "numbers_checked": 1, "untraced": []},
        "tool_calls": [{"name": "fleet_summary", "args": {"group_by": "site"}, "output": {"rows": ["a very large output"]}}],
        "session_id": "a" * 32, "new_session": True, "session_note": None}


def test_ask_returns_the_answer_the_tools_called_and_the_audit_but_not_the_raw_outputs(monkeypatch):
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None: FAKE)
    r = client.post("/api/agent/ask", json={"question": "How much fuel?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("The fleet used") and body["audit"]["faithful"]
    assert body["tools_called"] == [{"name": "fleet_summary", "args": {"group_by": "site"}}]
    assert "output" not in str(body["tools_called"])


def test_a_short_or_huge_question_is_refused():
    assert client.post("/api/agent/ask", json={"question": "a"}).status_code == 422
    assert client.post("/api/agent/ask", json={"question": "x" * 1001}).status_code == 422


def test_a_follow_up_passes_its_session_id_and_gets_it_back(monkeypatch):
    seen = []
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None: seen.append(session_id) or {**FAKE, "session_id": session_id, "new_session": False})
    r = client.post("/api/agent/ask", json={"question": "And by client?", "session_id": "b" * 32})
    assert r.status_code == 200 and seen == ["b" * 32]
    assert r.json()["session_id"] == "b" * 32 and r.json()["new_session"] is False and r.json()["session_note"] is None


def test_a_first_question_gets_a_new_session_id(monkeypatch):
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None: FAKE)
    body = client.post("/api/agent/ask", json={"question": "How much fuel?"}).json()
    assert body["session_id"] == "a" * 32 and body["new_session"] is True


def test_a_malformed_session_id_is_refused():
    for bad in ("short", "A" * 32, "g" * 32, "a" * 33, "../" + "a" * 29):
        assert client.post("/api/agent/ask", json={"question": "How much fuel?", "session_id": bad}).status_code == 422


def test_when_the_model_cannot_be_reached_the_user_gets_a_plain_message(monkeypatch):
    def boom(q, session_id=None):
        raise RuntimeError("credentials")
    monkeypatch.setattr(fleet_agent, "ask", boom)
    r = client.post("/api/agent/ask", json={"question": "How much fuel?"})
    assert r.status_code == 502 and "Vertex AI" in r.json()["detail"] and "credentials" not in r.json()["detail"]


# ---- limits ----------------------------------------------------------------------------------------------
def test_a_sixth_question_in_a_minute_is_refused_but_another_caller_is_not(monkeypatch, fresh_limiter):
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None: FAKE)
    assert [ask().status_code for _ in range(5)] == [200] * 5
    r = ask()
    assert r.status_code == 429 and "5 questions a minute" in r.json()["detail"]
    assert 1 <= int(r.headers["Retry-After"]) <= 61
    assert ask("2.2.2.2").status_code == 200
    fresh_limiter.t += 61
    assert ask().status_code == 200


def test_the_daily_cap_covers_every_caller_and_resets_the_next_utc_day(monkeypatch, fresh_limiter):
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None: FAKE)
    assert all(ask(f"10.0.0.{i}").status_code == 200 for i in range(8))
    r = ask("10.0.0.99")
    assert r.status_code == 429 and "daily limit" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) == 12 * 3600 + 1      # noon to midnight UTC
    fresh_limiter.t += 12 * 3600
    assert ask("10.0.0.99").status_code == 200


def test_a_failed_model_call_still_counts_and_a_rejected_question_does_not(monkeypatch):
    def boom(q, session_id=None):
        raise RuntimeError("down")
    monkeypatch.setattr(fleet_agent, "ask", boom)
    assert [ask().status_code for _ in range(5)] == [502] * 5
    assert ask().status_code == 429
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None: FAKE)
    for _ in range(10):
        assert client.post("/api/agent/ask", json={"question": "a"}, headers={"X-Forwarded-For": "3.3.3.3"}).status_code == 422
    assert ask("3.3.3.3").status_code == 200


def test_the_caller_is_the_address_cloud_run_appended_last():
    assert caller_of("6.6.6.6, 9.9.9.9", "127.0.0.1") == "9.9.9.9"
    assert caller_of(None, "127.0.0.1") == "127.0.0.1"
    assert caller_of("", None) == "unknown"


def test_behind_our_own_proxy_the_caller_is_the_address_before_it(monkeypatch):
    monkeypatch.setenv("FIELDCARBON_TRUSTED_PROXIES", "1")
    assert caller_of("6.6.6.6, 1.1.1.1, 10.0.0.9", "127.0.0.1") == "1.1.1.1"  # a forged first entry is ignored
    assert caller_of("1.1.1.1", "127.0.0.1") == "1.1.1.1"  # fewer entries than hops: the earliest one
    monkeypatch.setenv("FIELDCARBON_TRUSTED_PROXIES", "-1")
    with pytest.raises(ValueError, match="FIELDCARBON_TRUSTED_PROXIES"):
        caller_of("1.1.1.1", None)


def test_limits_come_from_env_vars_and_bad_values_are_rejected(monkeypatch):
    monkeypatch.setenv("FIELDCARBON_ASK_PER_MINUTE", "2")
    monkeypatch.setenv("FIELDCARBON_ASK_PER_DAY", "50")
    lim = AskLimiter.from_env()
    assert (lim.per_minute, lim.per_day) == (2, 50)
    for bad in ("0", "-1", "lots"):
        monkeypatch.setenv("FIELDCARBON_ASK_PER_DAY", bad)
        with pytest.raises(ValueError, match="FIELDCARBON_ASK_PER_DAY"):
            AskLimiter.from_env()


def test_the_reply_lists_each_checked_number_with_its_tool_and_label(monkeypatch):
    nums = [{"text": "16,492 litres", "tool": "fleet_summary", "label": "allocated"}]
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None: {**FAKE, "audit": {**FAKE["audit"], "numbers": nums}})
    assert client.post("/api/agent/ask", json={"question": "How much fuel?"}).json()["audit"]["numbers"] == nums


# ---- the streamed ask ------------------------------------------------------------------------------------
def _events(response):
    import json
    return [json.loads(line[6:]) for line in response.text.split("\n\n") if line.startswith("data: ")]


def test_the_stream_sends_each_step_then_the_answer(monkeypatch):
    def staged(q, session_id=None, on_step=None):
        on_step({"step": "tool_call", "name": "fleet_summary", "args": {"group_by": "site"}})
        on_step({"step": "tool_result", "name": "fleet_summary", "error": False, "ms": 12})
        return FAKE
    monkeypatch.setattr(fleet_agent, "ask", staged)
    r = client.post("/api/agent/ask/stream", json={"question": "How much fuel?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r)
    assert [e["step"] for e in events] == ["tool_call", "tool_result", "answer"]
    assert events[-1]["answer"].startswith("The fleet used") and "output" not in str(events[-1]["tools_called"])


def test_a_failing_model_ends_the_stream_with_an_error_event(monkeypatch):
    def broken(q, session_id=None, on_step=None):
        raise RuntimeError("vertex down")
    monkeypatch.setattr(fleet_agent, "ask", broken)
    events = _events(client.post("/api/agent/ask/stream", json={"question": "How much fuel?"}))
    assert events == [{"step": "error", "message": agent_api.UNREACHABLE}]


def test_the_stream_counts_against_the_same_limit(monkeypatch):
    monkeypatch.setattr(fleet_agent, "ask", lambda q, session_id=None, on_step=None: FAKE)
    codes = [client.post("/api/agent/ask/stream", json={"question": "How much fuel?"}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code
             for _ in range(6)]
    assert codes == [200] * 5 + [429]
