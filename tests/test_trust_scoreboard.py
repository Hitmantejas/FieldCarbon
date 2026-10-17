import json

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools import trust_scoreboard as ts

client = TestClient(app)


def test_the_scoreboard_reads_the_eval_results_and_every_check_has_a_status():
    s = ts.trust_scoreboard()
    assert s["available"] and s["updated"]
    groups = {c["group"] for c in s["checks"]}
    assert groups == {"The numbers", "Finding problems", "The analyst", "Reading documents", "Where we are less sure"}
    assert all(c["status"] in {"pass", "partial", "not_run"} and c["question"] and c["result"] and c["detail"] for c in s["checks"])
    assert len(s["limits"]) >= 4


def test_the_scoreboard_matches_the_summary_file():
    raw = json.loads(ts.SUMMARY.read_text(encoding="utf-8"))
    by_q = {c["question"]: c for c in ts.trust_scoreboard()["checks"]}
    t = raw["tool_cases"]
    assert by_q["Do the tools give the right answers?"]["result"] == f"{t['passed']} of {t['cases']} test questions pass"
    rc = raw["other"]["range_coverage"]
    c = by_q["Do receipts alone give the right range?"]
    assert c["result"].startswith(f"{rc['operations_inside']} of {rc['operations']} job types")
    assert c["status"] == ("pass" if rc["operations_inside"] == rc["operations"] else "partial")  # an honest limit is never shown as a pass


def test_a_score_below_full_marks_is_shown_as_partial(tmp_path, monkeypatch):
    raw = json.loads(ts.SUMMARY.read_text(encoding="utf-8"))
    raw["agent_runs"]["agent"]["faithfulness"] = 0.9
    f = tmp_path / "summary.json"
    f.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(ts, "SUMMARY", f)
    c = next(c for c in ts.trust_scoreboard()["checks"] if c["question"].startswith("Can every number"))
    assert c["status"] == "partial" and "90%" in c["result"]


def test_without_results_it_says_how_to_create_them(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "SUMMARY", tmp_path / "missing.json")
    s = ts.trust_scoreboard()
    assert not s["available"] and "run_all" in s["message"] and s["checks"] == []


def test_the_api_serves_the_scoreboard():
    r = client.get("/api/fleet/trust")
    assert r.status_code == 200 and r.json()["available"]


@pytest.mark.parametrize("word", ["verified", "guarantee"])
def test_the_wording_never_overclaims(word):
    assert word not in json.dumps(ts.trust_scoreboard()).lower()
