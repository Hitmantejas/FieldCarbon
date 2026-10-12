"""Runs evals/cases.json against the agent tools' output (agent tool-selection is checked once the agent exists)."""
import json
from pathlib import Path

import pytest

from backend.tools.calculate_roi import calculate_roi
from backend.tools.rank_interventions import rank_interventions

CASES = json.loads((Path(__file__).resolve().parents[1] / "evals" / "cases.json").read_text())["cases"]
TOOLS = {"rank_interventions": rank_interventions, "calculate_roi": calculate_roi}


def check(case: dict, output, spec: dict) -> None:
    kind = spec["type"]
    if kind == "every_recommendation_cites_source":
        assert all(item["evidence"] and all(e["title"] and e["link_status"] for e in item["evidence"]) for item in output)
    elif kind == "first_state":
        assert output[0]["state"] == spec["equals"]
    elif kind == "state":
        assert next(i for i in output if i["intervention_id"] == spec["intervention_id"])["state"] == spec["equals"]
    elif kind == "has_range":
        low, high = output[spec["field"] + "_low"], output[spec["field"] + "_high"]
        assert low is not None and high is not None and low <= high
    elif kind == "no_payback":
        assert output["payback_years_low"] is None and output["payback_years_high"] is None
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
