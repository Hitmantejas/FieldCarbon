"""The shareable report: traceable figures, sources for everything cited, no claims of outside checking."""
import json
import re

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools.generate_report import generate_report

client = TestClient(app)


def figures(node):
    """Every figure-shaped dict (has a confidence label) anywhere in the report."""
    if isinstance(node, dict):
        if "label" in node and "how" in node and "source_ids" in node:
            yield node
        for value in node.values():
            yield from figures(value)
    elif isinstance(node, list):
        for value in node:
            yield from figures(value)


def test_report_has_the_expected_sections_and_a_timestamp():
    r = generate_report(10)
    assert {"meta", "totals", "where_it_went", "pain_points", "plan", "answers", "limits", "labels", "method",
            "sources", "attribution"} <= set(r)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*", r["meta"]["generated_at"])
    assert r["meta"]["demo_data"] is True and "traceable" in r["meta"]["statement"]


def test_totals_match_the_farm_summary():
    t = generate_report(10)["totals"]
    assert t["litres"]["value"] == client.get("/api/farms/a/summary").json()["litres"]["value"]
    assert t["litres"]["label"] == "measured" and t["cost_gbp"]["label"] == "estimated"
    assert t["engine_hours"] > 0 and t["excluded_hours"] > 0


def test_every_figure_in_the_report_has_a_label_sources_and_a_bullet_explanation():
    found = list(figures(generate_report(10)))
    assert len(found) > 20
    for f in found:
        assert f["label"] in {"measured", "allocated", "estimated"} and f["source_ids"], f
        assert all(line.startswith("- ") for line in f["how"].split("\n")), f["how"]


def test_every_source_a_figure_cites_is_listed_with_its_link_status():
    r = generate_report(10)
    cited = {s for f in figures(r) for s in f["source_ids"]}
    listed = {s["source_id"]: s for s in r["sources"]}
    assert cited <= set(listed)
    assert all("link_status" in s for s in listed.values())


def test_plan_lists_only_ideas_that_suit_the_farm_and_follows_the_answers():
    ideas = {i["intervention_id"] for i in generate_report(10)["plan"]["ideas"]}
    assert "electric_tractor" not in ideas and "correct_tyre_pressure" not in ideas   # not answered yet
    after = generate_report(10, known={"tyre_pressure_checked": False})
    assert "correct_tyre_pressure" in {i["intervention_id"] for i in after["plan"]["ideas"]}
    assert after["answers"] == {"tyre_pressure_checked": False}
    assert after["plan"]["waiting"] == 2


def test_the_report_never_claims_to_be_verified():
    r = generate_report(10)
    text = json.dumps({k: v for k, v in r.items() if k != "sources"}).lower()
    assert "verified" not in text


def test_pain_points_in_the_report_are_the_jobs_above_typical():
    jobs = generate_report(10)["pain_points"]
    assert jobs and all(j["band"] in {"above_typical", "well_above"} for j in jobs)


def test_api_endpoint_takes_goal_and_answers():
    body = client.get("/api/farms/a/report?target_pct=20&has_ctis=false").json()
    assert body["plan"]["goal"]["target_pct"] == 20
    assert client.get("/api/farms/a/report?target_pct=0").status_code == 422
    assert client.get("/api/farms/z/report").status_code == 404
