"""Runs evals/cases.json against the agent tools' output (agent tool-selection is checked once the agent exists)."""
import json
from pathlib import Path

import pytest

from backend.tools.calculate_roi import calculate_roi
from backend.tools.rank_interventions import rank_interventions
from backend.tools.benchmark_peers import benchmark_peers
from backend.tools.data_quality import data_quality
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.fleet_jobs import fleet_jobs
from backend.tools.fleet_report import fleet_report
from backend.tools.fleet_opportunities import fleet_opportunities
from backend.tools.what_if import what_if
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_summary import fleet_summary
from backend.tools.generate_report import generate_report
from backend.tools.reconcile_fuel import reconcile_fuel
from backend.tools.set_goal import set_goal
from backend.tools.what_would_improve import what_would_improve

CASES = json.loads((Path(__file__).resolve().parents[1] / "evals" / "cases.json").read_text())["cases"]
TOOLS = {"rank_interventions": rank_interventions, "calculate_roi": calculate_roi, "set_goal": set_goal,
         "what_would_improve": what_would_improve, "generate_report": generate_report,
         "fleet_summary": fleet_summary, "emissions_per_client": emissions_per_client, "reconcile_fuel": reconcile_fuel,
         "data_quality": data_quality, "benchmark_peers": benchmark_peers, "detect_anomalies": detect_anomalies,
         "fleet_jobs": fleet_jobs, "fleet_report": fleet_report, "fleet_opportunities": fleet_opportunities, "what_if": what_if}


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
    elif kind == "cost_note":
        assert output["cost_note"] == spec["equals"]
    else:
        raise AssertionError(f"unknown check {kind}")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_case(case):
    assert set(case["expected_tools"]) <= set(TOOLS)
    output = TOOLS[case["expected_tools"][0]](**case["arguments"])
    for spec in case["checks"]:
        check(case, output, spec)


def test_every_tool_has_at_least_one_eval_case():
    covered = {t for c in CASES for t in c["expected_tools"]}
    assert covered == set(TOOLS)
