"""Eval cases (evals/cases.json): the agent tools and the checks run on their output, and the answer checks run on
recorded agent answers (refusals, wording, no invented numbers).

Shared by tests/test_evals.py and the harness (evals/run_all.py)."""
import json
import re
from pathlib import Path

import pytest

from backend.agent.faithfulness import audit
from backend.tools.calculate_roi import calculate_roi
from backend.tools.contracts import LABELS
from backend.tools.check_delivery_notes import check_delivery_notes
from backend.tools.client_statement import client_statement
from backend.tools.rank_interventions import rank_interventions
from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.data_quality import data_quality
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.diagnose_anomaly import diagnose_anomaly
from backend.tools.fleet_jobs import fleet_jobs
from backend.tools.fleet_report import fleet_report
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.what_if import what_if
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_summary import fleet_summary
from backend.tools.generate_report import generate_report
from backend.tools.reconcile_fuel import reconcile_fuel
from backend.tools.set_goal import set_goal
from backend.tools.upload_note import check_demo_note
from backend.tools.weekly_briefing import weekly_briefing
from backend.tools.what_would_improve import what_would_improve

CASES = json.loads((Path(__file__).resolve().parents[1] / "evals" / "cases.json").read_text(encoding="utf-8"))["cases"]
TOOLS = {"rank_interventions": rank_interventions, "calculate_roi": calculate_roi, "set_goal": set_goal,
         "what_would_improve": what_would_improve, "generate_report": generate_report,
         "fleet_summary": fleet_summary, "emissions_per_client": emissions_per_client, "reconcile_fuel": reconcile_fuel,
         "data_quality": data_quality, "benchmark_peers": benchmark_peers, "detect_anomalies": detect_anomalies,
         "fleet_jobs": fleet_jobs, "fleet_report": fleet_report, "fleet_opportunities": fleet_opportunities, "what_if": what_if,
         "check_delivery_notes": check_delivery_notes, "client_statement": client_statement,
         "check_uploaded_note": check_demo_note, "diagnose_anomaly": diagnose_anomaly, "weekly_briefing": weekly_briefing}


def figures(node):
    if isinstance(node, dict):
        if "label" in node and "how" in node and "source_ids" in node:
            yield node
        for value in node.values():
            yield from figures(value)
    elif isinstance(node, list):
        for value in node:
            yield from figures(value)


def check(case: dict, output, spec: dict) -> None:
    kind = spec["type"]
    if kind == "every_recommendation_cites_source":
        assert all(item["evidence"] and all(e["title"] and e["link_status"] for e in item["evidence"]) for item in output)
    elif kind == "first_state":
        assert output[0]["state"] == spec["equals"]
    elif kind == "state":
        assert next(i for i in output if i["intervention_id"] == spec["intervention_id"])["state"] == spec["equals"]
    elif kind == "has_range":
        fig = output["figures"][spec["field"]]
        assert fig is not None and fig["source_ids"] and fig["low"] <= fig["high"]
    elif kind == "no_payback":
        assert output["figures"]["payback_years"] is None
    elif kind == "verdict":
        assert next(i for i in output["ideas"] if i["intervention_id"] == spec["intervention_id"])["verdict"] == spec["equals"]
    elif kind == "target_is_sourced":
        assert output["target_co2e"]["source_ids"] and output["target_co2e"]["label"] == "measured"
    elif kind == "top_question":
        assert output["top"] == spec["equals"]
    elif kind == "question_count":
        assert len(output["questions"]) == spec["equals"]
    elif kind == "report_traceable":
        assert output["sources"] and "traceable" in output["meta"]["statement"]
        assert all(f["source_ids"] and f["label"] for f in figures(output))
    elif kind == "fleet_total_litres":
        assert sum(r["litres"]["value"] for r in output["rows"]) == pytest.approx(spec["approx"], abs=spec["abs"])
    elif kind == "row_count":
        assert len(output["rows"]) == spec["equals"]
    elif kind == "every_figure_sourced":
        assert all(f["source_ids"] and f["label"] for f in figures(output))
    elif kind == "finds":
        want = {k: v for k, v in spec.items() if k != "type"}
        assert any(all(f.get(k) == v for k, v in want.items()) for f in output["findings"]), want
    elif kind == "finding_count_at_most":
        assert len(output["findings"]) <= spec["n"]
    elif kind == "groups_at_least":
        assert len(output["groups"]) >= spec["n"]
    elif kind == "idea_state":
        assert next(i for i in output["ideas"] if i["intervention_id"] == spec["intervention_id"])["state"] == spec["equals"]
    elif kind == "scenario_litres":
        assert output["is_scenario"] and output["litres_saved"]["value"] == pytest.approx(spec["approx"], abs=spec["abs"])
    elif kind == "statement_matches_client":
        row = emissions_per_client(output["client_id"])["rows"][0]
        assert all(output["totals"][k]["value"] == row[k]["value"] for k in ("litres", "co2e_kg", "cost_gbp"))
        assert all(f["source_ids"] and f["label"] for f in figures(output))
        assert LABELS.index(output["co2e_per_ha"]["label"]) >= LABELS.index("allocated")
    elif kind == "cost_note":
        assert output["cost_note"] == spec["equals"]
    elif kind == "note_verdict":
        assert output["verdict"] == spec["equals"], output["verdict"]
        assert all(f["figure"] is None or (f["figure"]["source_ids"] and f["figure"]["label"]) for f in output["findings"])
    elif kind == "diagnosis_top":
        top = output["hypotheses"][0]
        assert top["status"] == "supported" and top["id"] == spec["equals"], (top["id"], top["status"])
        assert all(h["evidence"] is None or (h["evidence"]["source_ids"] and h["evidence"]["label"]) for h in output["hypotheses"])
    elif kind == "diagnosis_status":
        h = next(h for h in output["hypotheses"] if h["id"] == spec["hypothesis"])
        assert h["status"] == spec["equals"], (h["id"], h["status"])
    elif kind == "briefing_items":
        items = output["items"]
        assert [i["family"] for i in items] == spec["families"] and items[0]["id"] == spec["first"], [i["id"] for i in items]
        assert all(i["next_step"] and i["would_improve"] and i["figure"]["label"] in LABELS for i in items)
    else:
        raise AssertionError(f"unknown check {kind}")


ANSWER_CHECKS = ("forbidden_regex", "tool_not_called", "must_mention_any", "no_new_numbers")


def answer_check(spec: dict, answer: str, called: set[str], outputs: list, question: str = "") -> str | None:
    """One answer check on a recorded agent run: None when the answer passes, otherwise what failed."""
    kind = spec["type"]
    if kind == "forbidden_regex":
        m = re.search(spec["pattern"], answer)
        return None if m is None else f"forbidden text: {m.group(0)}"
    if kind == "tool_not_called":
        return None if spec["tool"] not in called else f"called {spec['tool']}"
    if kind == "must_mention_any":
        low = answer.lower()
        return None if any(p.lower() in low for p in spec["phrases"]) else f"mentions none of: {', '.join(spec['phrases'])}"
    if kind == "no_new_numbers":
        a = audit(answer, outputs, question)
        return None if a.faithful else f"untraced numbers: {', '.join(n.text for n in a.unmatched)}"
    raise AssertionError(f"unknown answer check {kind}")


def run_case(case: dict):
    """Run the case's first expected tool with its arguments and apply every check (raises on failure). A case with
    `expect_error` passes only if the tool refuses with that message, and so returns no figures. A case with no
    expected tool (a question the analyst should refuse) has only answer checks, scored on recorded runs."""
    if not case["expected_tools"]:
        assert not case["checks"], case["id"]
        return None
    tool = TOOLS[case["expected_tools"][0]]
    if case.get("expect_error"):
        with pytest.raises(ValueError, match=case["expect_error"]):
            tool(**case["arguments"])
        return None
    output = tool(**case["arguments"])
    for spec in case["checks"]:
        check(case, output, spec)
    return output
