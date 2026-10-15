"""Fleet tools, batch 1: summary, per-client emissions, data quality and fuel reconciliation."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.tools.data_quality import data_quality
from backend.tools.emissions_per_client import emissions_per_client
from backend.tools.fleet_summary import fleet_summary
from backend.tools.reconcile_fuel import reconcile_fuel

client = TestClient(app)
REAL_TOTAL = 10813.69 + 5333.0 + 346.0
INTERNAL_ID = re.compile(r"\b[a-z]{2,}_[a-z0-9]+(?:_[a-z0-9]+)*\b")


def figures(node):
    if isinstance(node, dict):
        if "label" in node and "how" in node and "source_ids" in node:
            yield node
        for value in node.values():
            yield from figures(value)
    elif isinstance(node, list):
        for value in node:
            yield from figures(value)


def by_key(result):
    return {r["key"]: r for r in result["rows"]}


# ---- fleet_summary ---------------------------------------------------------------------------------------
def test_fleet_totals_tie_to_the_real_litres():
    r = fleet_summary("site")
    assert sum(x["litres"]["value"] for x in r["rows"]) == pytest.approx(REAL_TOTAL, abs=3)
    assert r["totals"]["litres"]["value"] == pytest.approx(REAL_TOTAL, abs=3)


@pytest.mark.parametrize("kwargs", [{"group_by": "site"}, {"group_by": "machine", "site_id": "S2"}])
def test_totals_carry_jobs_hours_and_area_summed_over_the_rows(kwargs):
    r = fleet_summary(**kwargs)  # the Overview screen reads these; missing ones showed "NaN jobs over NaN engine hours"
    t = r["totals"]
    assert t["jobs"] == sum(x["jobs"] for x in r["rows"]) > 0
    assert t["hours"] == pytest.approx(sum(x["hours"] for x in r["rows"])) and t["hours"] > 0
    assert t["area_ha"] == pytest.approx(sum(x["area_ha"] for x in r["rows"]))
    assert isinstance(t["jobs"], int) and isinstance(t["hours"], float)

def test_site_rows_carry_the_weakest_label_of_their_inputs():
    rows = by_key(fleet_summary("site"))
    assert rows["S1"]["litres"]["label"] == "allocated"      # S1 includes fuel burned outside jobs, shared out by rule
    assert rows["S2"]["litres"]["label"] == rows["S3"]["litres"]["label"] == "measured"


def test_vineyard_fuel_stays_measured_but_says_it_comes_from_the_tank_level():
    r = fleet_summary("site")
    rows = by_key(r)
    s2, s3 = rows["S2"]["litres"]["how"], rows["S3"]["litres"]["how"]
    assert "tank levels" in s2 and "fuel-flow sensor" in s2 and "own fuel data" not in s2
    assert "tank level" not in s3 and "own fuel data" in s3
    assert "Vineyard fuel is" in r["totals"]["litres"]["how"]          # the fleet total includes the vineyard
    assert "Vineyard" not in by_key(fleet_summary("site", site_id="S1"))["S1"]["litres"]["how"]


def test_month_view_covers_the_company_year_and_adds_up():
    r = fleet_summary("month")
    assert [x["key"] for x in r["rows"]] == [f"2025-{m:02d}" for m in range(5, 13)] + [f"2026-{m:02d}" for m in range(1, 5)]
    assert sum(x["litres"]["value"] for x in r["rows"]) == pytest.approx(REAL_TOTAL, abs=3)


def test_machines_and_operations_use_readable_names():
    names = {x["name"] for x in fleet_summary("machine")["rows"]}
    assert "Tractor 4, 163 kW" in names
    ops = {x["name"] for x in fleet_summary("operation")["rows"]}
    assert "Ploughing" in ops and "Ridging" in ops and "Idling" in ops


def test_filters_narrow_the_rows_and_operator_is_only_a_filter():
    only = fleet_summary("operation", site_id="S2")
    assert all(x["key"].startswith("vy_") for x in only["rows"])
    one = fleet_summary("site", operator_id="OP-01")
    assert 0 < one["totals"]["litres"]["value"] < REAL_TOTAL / 4


def test_emissions_use_the_uk_factor_and_cite_it():
    r = fleet_summary("site")
    t = r["totals"]
    assert t["co2e_kg"]["value"] == pytest.approx(t["litres"]["value"] * 3.38206, rel=1e-4)
    assert "uk_ghg_2025" in t["co2e_kg"]["source_ids"]


def test_cost_uses_the_invoice_prices_in_the_data_not_one_fixed_price():
    t = fleet_summary("site")["totals"]
    assert 0.70 < t["cost_gbp"]["value"] / t["litres"]["value"] < 1.2
    assert t["cost_gbp"]["label"] in {"measured", "allocated"}


def test_every_figure_has_a_label_sources_and_plain_bullets():
    for result in (fleet_summary("machine"), emissions_per_client(), data_quality()):
        for f in figures(result):
            assert f["label"] in {"measured", "allocated", "estimated"} and f["source_ids"], f
            assert all(line.startswith("- ") for line in f["how"].split("\n")) and "**" in f["how"], f["how"]
            assert not INTERNAL_ID.search(f["how"]), f["how"]


def test_unknown_grouping_is_rejected():
    with pytest.raises(ValueError):
        fleet_summary("colour")


# ---- emissions_per_client --------------------------------------------------------------------------------
def test_client_rows_overhead_and_unmatched_jobs_add_up_to_the_fleet_total():
    r = emissions_per_client()
    parts = sum(x["litres"]["value"] for x in r["rows"]) + r["overhead"]["litres"]["value"] + r["unmatched_jobs"]["litres"]["value"]
    assert parts == pytest.approx(REAL_TOTAL, abs=3) and parts == pytest.approx(r["total"]["value"], abs=0.1)
    assert len(r["rows"]) == 16 and all(x["client_id"] != "unassigned" for x in r["rows"])


def test_overhead_is_fuel_outside_jobs_split_by_use_and_unmatched_jobs_are_small():
    r = emissions_per_client()
    assert r["overhead"]["litres"]["value"] > 3900 and r["overhead"]["litres"]["label"] == "allocated"
    assert sum(b["litres"]["value"] for b in r["overhead"]["breakdown"]) == pytest.approx(r["overhead"]["litres"]["value"], abs=0.1)
    assert {b["key"] for b in r["overhead"]["breakdown"]} <= {"other_idle", "other_implement_nonproductive", "other_offroad_unassigned", "other_road_transport"}
    assert r["unmatched_jobs"]["jobs"] > 0 and r["unmatched_jobs"]["litres"]["value"] < 0.1 * r["overhead"]["litres"]["value"]


def test_one_client_by_month():
    r = emissions_per_client(client_id="C09")
    assert [x["client_id"] for x in r["months"]] == ["C09"] * len(r["months"])
    assert sum(m["litres"]["value"] for m in r["months"]) == pytest.approx(r["rows"][0]["litres"]["value"], abs=0.1)
    assert r["overhead"] is None


# ---- data_quality ----------------------------------------------------------------------------------------
def test_data_quality_reports_labels_unassigned_fuel_and_frozen_hours():
    q = data_quality()
    assert q["frozen_hours"]["value"] == pytest.approx(95.66, abs=0.1)
    assert 0.5 < q["measured_share_pct"]["value"] / 100 < 0.95
    assert q["unassigned_litres"]["value"] > 3900
    assert q["jobs_without_area"]["value"] >= 1


# ---- reconcile_fuel --------------------------------------------------------------------------------------
def finding(result, kind, **match):
    return [f for f in result["findings"] if f["kind"] == kind and all(f.get(k) == v for k, v in match.items())]


def test_reconciliation_finds_the_machine_that_was_given_more_fuel_than_it_burned():
    f = finding(reconcile_fuel(), "machine_over_dispense", machine_id="S1-T4", month="2025-10")
    assert len(f) == 1 and f[0]["ratio"] >= 1.15 and f[0]["night_dispenses"] >= 4


def test_reconciliation_finds_the_unlogged_stock_loss_at_the_depot():
    f = finding(reconcile_fuel(), "stock_gap", depot_id="S1-D1")
    assert len(f) == 1 and f[0]["month"] == "2026-01" and f[0]["litres"]["value"] == pytest.approx(900, abs=60)


def test_reconciliation_finds_the_duplicate_delivery_note_and_does_not_blame_the_depot_for_it():
    r = reconcile_fuel()
    dup = finding(r, "duplicate_delivery_note", depot_id="S2-D1")
    assert len(dup) == 1 and dup[0]["litres"]["value"] > 0
    assert not finding(r, "stock_gap", depot_id="S2-D1")      # the duplicate is removed before comparing stock


def test_reconciliation_raises_almost_no_false_alarms():
    r = reconcile_fuel()
    assert len(r["findings"]) <= 4          # three planted problems, at most one extra


def test_night_dispenses_are_attached_to_the_planted_machine_only():
    r = reconcile_fuel()
    assert {f["machine_id"] for f in r["findings"] if f.get("night_dispenses")} == {"S1-T4"}


def test_reconciliation_text_is_plain_and_uses_display_names():
    for f in reconcile_fuel()["findings"]:
        assert "Tractor" in f["title"] or "depot" in f["title"].lower() or "note" in f["title"].lower(), f["title"]
        assert not INTERNAL_ID.search(f["title"]) and not INTERNAL_ID.search(f["litres"]["how"])


def test_reconciliation_never_reads_the_answer_file():
    source = (Path(__file__).resolve().parents[1] / "backend" / "tools" / "reconcile_fuel.py").read_text(encoding="utf-8")
    assert "ground_truth" not in source


# ---- API ---------------------------------------------------------------------------------------------------
def test_fleet_api_endpoints():
    assert client.get("/api/fleet/summary?group_by=site").json()["rows"]
    assert client.get("/api/fleet/summary?group_by=month&site_id=S2").status_code == 200
    assert client.get("/api/fleet/summary?group_by=colour").status_code == 422
    assert client.get("/api/fleet/clients").json()["rows"]
    assert client.get("/api/fleet/data-quality").json()["frozen_hours"]["value"] > 0
    assert len(client.get("/api/fleet/reconciliation").json()["findings"]) >= 3


def test_the_detection_eval_finds_all_three_planted_problems_with_no_false_alarms():
    from evals.fleet_detection import score

    s = score()
    assert s["planted"] == 3 and s["found"] == 3 and s["recall"] == 1.0 and s["false_alarms"] == 0
    litres = {r["anomaly_id"]: r["found_litres"] for r in s["results"]}
    assert litres["A2"] == pytest.approx(900, abs=60)


def test_machine_rows_name_their_site_and_site_rows_say_what_kind_of_data_they_have():
    machines = fleet_summary("machine")["rows"]
    assert all(r["site_id"] == r["key"][:2] for r in machines)
    kinds = {r["key"]: r["data_kind"] for r in fleet_summary("site")["rows"]}
    assert kinds == {"S1": "raw telemetry", "S2": "per-operation summary", "S3": "raw telemetry, tillage only"}


def test_a_stock_gap_is_described_against_the_books_not_as_missing_fuel():
    gaps = [f["title"] for f in reconcile_fuel()["findings"] if f["kind"].startswith("stock")]
    assert gaps and all("than the books show" in t and "missing" not in t for t in gaps)
