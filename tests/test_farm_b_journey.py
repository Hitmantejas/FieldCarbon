"""Farm B (receipts + profile) through plan, goal, sharpen, report and the API. Offline."""
import json

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools.generate_report import generate_report
from backend.tools.rank_interventions import rank_interventions
from backend.tools.set_goal import set_goal
from backend.tools.what_would_improve import what_would_improve

client = TestClient(app)


def by_id(items):
    return {i["intervention_id"]: i for i in items}


def figures(node):
    if isinstance(node, dict):
        if {"label", "how", "source_ids"} <= node.keys():
            yield node
        for v in node.values():
            yield from figures(v)
    elif isinstance(node, list):
        for v in node:
            yield from figures(v)


def test_no_farm_b_output_cites_the_telemetry():
    outputs = [rank_interventions("b"), set_goal(None, "b"), what_would_improve(None, "b"), generate_report(None, "b")]
    for out in outputs:
        for f in figures(out):
            assert "tum_alc_data" not in f["source_ids"], f["how"][:80]
    assert "tum_alc_data" not in {s["source_id"] for s in generate_report(None, "b")["sources"]}


def test_unknown_engine_load_is_needs_info_not_a_wrong_no():
    gutd = by_id(rank_interventions("b"))["shift_up_throttle_down"]
    assert gutd["state"] == "needs_info" and tuple(gutd["missing_inputs"]) == ("engine_load",)
    assert "part load" in gutd["how"]
    assert by_id(rank_interventions("a"))["shift_up_throttle_down"]["state"] == "feasible"  # Farm A unchanged


def test_farm_b_savings_cover_both_ends_of_the_split_and_say_so():
    b = by_id(rank_interventions("b"))
    till = b["reduced_tillage"]
    assert till["state"] == "feasible" and "job split" in till["how"]
    fig = till["figures"]["litres_saved"]
    assert f"{fig['low']:,.0f} to {fig['high']:,.0f} litres" in till["how"]  # the text quotes the merged range
    for i in b.values():
        width = lambda f: f["high"] - f["low"]  # noqa: E731
        a = by_id(rank_interventions("a"))[i["intervention_id"]]["figures"]["litres_saved"]
        if i["figures"]["litres_saved"] and a and i["intervention_id"] != "hvo_switch":
            assert width(i["figures"]["litres_saved"]) >= width(a) * 0.5  # an estimated split is not narrower in kind


def test_goal_for_farm_b_uses_receipts_and_a_default_suggestion():
    g = set_goal(None, "b")
    assert g["suggested_pct"] == g["target_pct"] == 10
    assert "receipts do not show fuel per job" in g["suggested_how"]
    assert g["target_co2e"]["source_ids"][0] == "farm_b_receipts" and g["target_co2e"]["label"] == "measured"


def test_sharpen_for_farm_b_names_the_logbook_and_engine_data():
    s = what_would_improve(None, "b")
    text = " ".join(s["still_uncertain"])
    assert "logbook" in text and "Engine data" in text
    assert "do not know what you pay" not in text  # the receipts show what was paid
    assert s["top"] in ("tyre_pressure_checked", "has_ctis", "ballast_type")


def test_report_for_farm_b():
    r = generate_report(None, "b")
    assert r["meta"]["farm"] == "Farm B" and r["totals"]["engine_hours"] is None
    assert r["pain_points"] == [] and "Not available" in r["pain_points_note"]
    assert r["totals"]["cost_gbp"]["label"] == "measured" and "receipts" in r["method"]
    assert all(i["figures"]["litres_saved"] is None or i["figures"]["litres_saved"]["label"] == "estimated"
               for i in r["plan"]["ideas"])


def test_farm_b_api_endpoints():
    pain = client.get("/api/farms/b/pain-points").json()
    assert pain["available"] is False and pain["ratings"] == [] and pain["not_working"]["label"] == "estimated"
    for path in ("interventions", "goal?target_pct=20", "sharpen", "report", "interventions?tyre_pressure_checked=false"):
        assert client.get(f"/api/farms/b/{path}").status_code == 200, path
    assert client.get("/api/farms/z/goal").status_code == 404
    json.dumps(client.get("/api/farms/b/report").json())  # serialisable, no NaN
