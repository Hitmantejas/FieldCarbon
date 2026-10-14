"""The ask endpoint, with the agent stubbed: no model is called."""
from fastapi.testclient import TestClient

from backend.agent import fleet_agent
from backend.api.main import app

client = TestClient(app)
FAKE = {"question": "q", "answer": "The fleet used 16,492 litres (allocated).", "attempts": 1, "tokens": {"input": 1, "output": 1, "thinking": 0},
        "audit": {"faithful": True, "numbers_checked": 1, "untraced": []},
        "tool_calls": [{"name": "fleet_summary", "args": {"group_by": "site"}, "output": {"rows": ["a very large output"]}}]}


def test_ask_returns_the_answer_the_tools_called_and_the_audit_but_not_the_raw_outputs(monkeypatch):
    monkeypatch.setattr(fleet_agent, "ask", lambda q: FAKE)
    r = client.post("/api/agent/ask", json={"question": "How much fuel?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("The fleet used") and body["audit"]["faithful"]
    assert body["tools_called"] == [{"name": "fleet_summary", "args": {"group_by": "site"}}]
    assert "output" not in str(body["tools_called"])


def test_a_short_or_huge_question_is_refused():
    assert client.post("/api/agent/ask", json={"question": "a"}).status_code == 422
    assert client.post("/api/agent/ask", json={"question": "x" * 1001}).status_code == 422


def test_when_the_model_cannot_be_reached_the_user_gets_a_plain_message(monkeypatch):
    def boom(q):
        raise RuntimeError("credentials")
    monkeypatch.setattr(fleet_agent, "ask", boom)
    r = client.post("/api/agent/ask", json={"question": "How much fuel?"})
    assert r.status_code == 502 and "Vertex AI" in r.json()["detail"] and "credentials" not in r.json()["detail"]
