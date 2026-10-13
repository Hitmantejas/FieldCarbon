"""Jobs and fields: the job list with its figures, and fuel grouped by field."""
import pytest

from backend.fleet import data
from backend.tools.fleet_jobs import fleet_jobs
from backend.tools.fleet_summary import fleet_summary

JOB_LITRES = float(data.jobs().litres.sum())


def test_the_job_list_counts_every_job_and_pages_through_them():
    r = fleet_jobs(limit=25)
    assert r["total_jobs"] == 713 and len(r["rows"]) == 25
    assert fleet_jobs(limit=25, offset=700)["rows"][0]["job_id"] != r["rows"][0]["job_id"]
    assert len(fleet_jobs(limit=25, offset=700)["rows"]) == 13


def test_all_pages_add_up_to_the_real_job_litres():
    r = fleet_jobs(limit=1000)
    assert sum(j["litres"]["value"] for j in r["rows"]) == pytest.approx(JOB_LITRES, abs=0.5)
    assert r["totals"]["litres"]["value"] == pytest.approx(JOB_LITRES, abs=0.5)


def test_filters_narrow_the_list_and_the_totals_together():
    r = fleet_jobs(site_id="S3", limit=100)
    assert r["total_jobs"] == 10 and {j["site_id"] for j in r["rows"]} == {"S3"}
    r = fleet_jobs(client_id="C09", month="2025-07", limit=100)
    assert r["rows"] and all(j["client_id"] == "C09" and j["month"] == "2025-07" for j in r["rows"])
    assert r["totals"]["litres"]["value"] == pytest.approx(sum(j["litres"]["value"] for j in r["rows"]), abs=0.01)


def test_each_job_has_readable_names_a_date_and_labelled_sourced_figures():
    j = fleet_jobs(limit=1)["rows"][0]
    assert j["machine"].startswith(("Tractor", "Vineyard tractor", "Tümosan")) or j["machine"]
    assert j["operation"] and j["date"][:4] in ("2025", "2026")
    for key in ("litres", "co2e_kg"):
        assert j[key]["label"] in ("measured", "allocated", "estimated") and j[key]["source_ids"]
    assert j["litres"]["label"] == "measured"


def test_litres_per_hectare_is_allocated_because_the_area_is_worked_out():
    rows = fleet_jobs(limit=1000)["rows"]
    with_area = [j for j in rows if j["l_per_ha"]]
    assert with_area and all(j["l_per_ha"]["label"] == "allocated" for j in with_area)
    assert all(j["l_per_ha"] is None for j in rows if not j["area_ha"])


def test_sorting_by_litres_puts_the_biggest_job_first():
    rows = fleet_jobs(sort="litres", limit=5)["rows"]
    assert [j["litres"]["value"] for j in rows] == sorted((j["litres"]["value"] for j in rows), reverse=True)


def test_jobs_without_a_matched_field_say_so_instead_of_inventing_one():
    r = fleet_jobs(site_id="S1", limit=1000)
    assert any(j["field"] is None for j in r["rows"])


def test_unknown_sort_is_rejected():
    with pytest.raises(ValueError):
        fleet_jobs(sort="operator")


def test_fuel_by_field_covers_job_fuel_only_and_names_fields():
    rows = fleet_summary("field")["rows"]
    assert len(rows) == 117
    assert sum(r["litres"]["value"] for r in rows) == pytest.approx(JOB_LITRES - float(data.jobs()[data.jobs().field_id.isna()].litres.sum()), abs=0.5)
    assert all(r["name"].startswith("Field ") for r in rows)


def test_arable_fields_are_allocated_because_their_outlines_are_our_own_matching():
    rows = fleet_summary("field")["rows"]
    arable = [r for r in rows if r["key"].startswith("S1-")]
    assert arable and all(r["litres"]["label"] == "allocated" for r in arable)
    assert all("outlines" in r["litres"]["how"] for r in arable)
