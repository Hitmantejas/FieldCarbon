"""The tools the analyst agent may call: same names as the eval cases, read-only, compact, and never about operators."""
import inspect
import json

import pytest

from backend.agent import tools
from backend.agent.faithfulness import audit
from evals.checks import CASES, TOOLS


def test_agent_tools_keep_the_names_the_eval_cases_expect():
    names = {t.__name__ for t in tools.AGENT_TOOLS}
    expected = {name for c in CASES if c.get("agent") for name in c["expected_tools"]}
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
    assert first["evidence"] and all({"title", "region", "source_id"} <= e.keys() for e in first["evidence"])  # year is left out when unknown
    assert all("derivation" not in e and "baseline" not in e for e in first["evidence"])


def test_numbers_in_a_tool_output_pass_the_auditor():
    out = tools.fleet_summary(group_by="site")
    assert audit("The fleet burned 16,492 litres in total.", [out]).faithful
    assert not audit("The fleet burned 18,000 litres in total.", [out]).faithful


def figures(node):
    if isinstance(node, dict):
        if "label" in node and "source_ids" in node:
            yield node
        for v in node.values():
            yield from figures(v)
    elif isinstance(node, list):
        for v in node:
            yield from figures(v)


def all_floats(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from all_floats(v)
    elif isinstance(node, list):
        for v in node:
            yield from all_floats(v)
    elif isinstance(node, float):
        yield node


@pytest.mark.parametrize("name,kwargs", [("fleet_summary", {"group_by": "machine"}), ("emissions_per_client", {}),
                                         ("benchmark_peers", {}), ("fleet_opportunities", {}), ("fleet_jobs", {"limit": 10})])
def test_compact_outputs_keep_every_label_and_source_and_round_the_numbers(name, kwargs):
    out = tools.BY_NAME[name](**kwargs)
    figs = list(figures(out))
    assert figs and all(f["label"] in {"measured", "allocated", "estimated"} and f["source_ids"] for f in figs)
    assert all(abs(x) < 1 or round(x, 2) == x for x in all_floats(out))
    assert '"low": null' not in json.dumps(out)


def test_compact_totals_match_the_full_tool_and_keep_their_explanations():
    full, small = TOOLS["fleet_summary"]("client"), tools.fleet_summary(group_by="client")
    assert small["totals"]["litres"]["value"] == pytest.approx(full["totals"]["litres"]["value"], abs=0.01)
    assert all("how" in small["totals"][k] for k in ("litres", "co2e_kg", "cost_gbp"))
    row = small["rows"][0]   # F8 6c: rows keep label and sources, not the explanation (the screens show it)
    assert "how" not in json.dumps(small["rows"]) and row["litres"]["label"] and row["litres"]["source_ids"]


def test_list_explanations_and_link_bookkeeping_are_left_out_for_the_model():
    opp = tools.fleet_opportunities()
    assert '"how"' not in json.dumps(opp["ideas"]) and "link_status" not in json.dumps(opp)
    ev = [e for i in opp["ideas"] for e in i["evidence"]]
    assert all(e["title"] and e["source_id"] for e in ev)                     # what the citation check needs
    assert all(e.get("is_manufacturer", True) is True for e in ev)            # kept only when it matters
    assert all("how" in tools.data_quality()[k] for k in ("measured_share_pct", "unassigned_litres"))   # top-level: kept


def test_a_diagnosis_keeps_the_reasoning_behind_each_cause():
    fid = next(f["id"] for f in tools.reconcile_fuel()["findings"] if f.get("diagnosable"))
    assert all("how" in h["evidence"] for h in tools.diagnose_anomaly(fid)["hypotheses"] if h.get("evidence"))


@pytest.mark.parametrize("group_by", ["field", "operation"])
def test_long_groupings_are_capped_and_say_how_many_rows_are_left_out(group_by):
    full, small = TOOLS["fleet_summary"](group_by), tools.fleet_summary(group_by=group_by)
    assert len(small["rows"]) == tools.MAX_ROWS and small["rows_not_shown"] == len(full["rows"]) - tools.MAX_ROWS
    assert [r["key"] for r in small["rows"]] == [r["key"] for r in full["rows"][:tools.MAX_ROWS]]   # largest first
    assert small["totals"]["litres"]["value"] == pytest.approx(full["totals"]["litres"]["value"], abs=0.01)
    assert len(json.dumps(small)) < 20_000


def test_peers_explain_only_the_machines_above_their_peers():
    peers = [p for g in tools.benchmark_peers()["groups"] for p in g["peers"]]
    assert any(p["above_peers"] for p in peers)
    for p in peers:
        assert "label" in p["l_per_ha"] and ("how" in p["l_per_ha"]) == p["above_peers"]
        assert ("litres_at_stake" in p) == p["above_peers"]


def test_each_idea_lists_each_source_once():
    for idea in tools.fleet_opportunities()["ideas"]:
        ids = [e["source_id"] for e in idea["evidence"]]
        assert ids and len(ids) == len(set(ids))
