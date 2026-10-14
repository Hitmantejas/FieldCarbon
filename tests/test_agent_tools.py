"""The tools the analyst agent may call: same names as the eval cases, read-only, compact, and never about operators."""
import inspect
import json

import pytest

from backend.agent import tools
from backend.agent.faithfulness import audit
from evals.checks import CASES, TOOLS


def test_agent_tools_keep_the_names_the_eval_cases_expect():
    names = {t.__name__ for t in tools.AGENT_TOOLS}
    expected = {name for c in CASES if c["id"].startswith(("plain-", "fleet-")) for name in c["expected_tools"]}
    assert expected <= names
    assert names <= set(TOOLS)


def test_no_agent_tool_can_filter_or_rank_by_operator():
    for t in tools.AGENT_TOOLS:
        assert "operator" not in " ".join(inspect.signature(t).parameters)


def test_every_tool_has_a_plain_docstring_for_the_model():
    assert all((t.__doc__ or "").strip() and len(t.__doc__) > 40 for t in tools.AGENT_TOOLS)


def test_outputs_are_plain_json():
    for call in (tools.fleet_summary(), tools.data_quality(), tools.reconcile_fuel(), tools.detect_anomalies(),
                 tools.check_delivery_notes(), tools.benchmark_peers(), tools.fleet_opportunities(site_id="S1")):
        json.dumps(call)


def test_a_bad_argument_comes_back_as_an_error_the_model_can_read_not_a_crash():
    r = tools.fleet_summary(group_by="colour")
    assert "error" in r and "colour" in r["error"]
    assert "error" in tools.what_if(change="hvo", amount_pct=500)


def test_jobs_are_capped_so_one_call_cannot_flood_the_model():
    assert len(tools.fleet_jobs(limit=500)["rows"]) == tools.MAX_JOBS


def test_reconciliation_keeps_the_findings_and_only_the_rows_that_need_a_look():
    full, small = TOOLS["reconcile_fuel"](), tools.reconcile_fuel()
    assert len(small["findings"]) == len(full["findings"])
    assert len(small["depots"]["rows"]) < len(full["depots"]["rows"])
    assert all(r["flagged"] for r in small["machine_months"]["rows"])


def test_opportunities_keep_names_sources_and_figures_without_the_long_evidence_rows():
    ideas = tools.fleet_opportunities(site_id="S1")["ideas"]
    first = ideas[0]
    assert first["name"] and first["figures"]["litres_saved"]["label"] == "estimated"
    assert first["evidence"] and all({"title", "region", "year", "source_id", "link_status"} <= e.keys() for e in first["evidence"])
    assert all("derivation" not in e and "baseline" not in e for e in first["evidence"])


def test_numbers_in_a_tool_output_pass_the_auditor():
    out = tools.fleet_summary(group_by="site")
    assert audit("The fleet burned 16,492 litres in total.", [out]).faithful
    assert not audit("The fleet burned 18,000 litres in total.", [out]).faithful
