"""Runs evals/cases.json against the agent tools' output (agent tool-selection is checked once the agent exists)."""
import pytest

from evals.checks import CASES, TOOLS, run_case


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_case(case):
    assert set(case["expected_tools"]) <= set(TOOLS)
    run_case(case)


def test_every_tool_has_at_least_one_eval_case():
    covered = {t for c in CASES for t in c["expected_tools"]}
    assert covered == set(TOOLS)
