"""The fleet report: one traceable document for the company, or one client's statement."""
import json

import pytest

from backend.fleet import data
from backend.tools.fleet_report import fleet_report

REAL_TOTAL = float(data.ledger().litres.sum())


def test_company_report_totals_tie_to_the_real_fuel_and_the_parts_add_up():
    r = fleet_report()
    assert r["totals"]["litres"]["value"] == pytest.approx(REAL_TOTAL, abs=1)
    assert sum(s["litres"]["value"] for s in r["by_site"]) == pytest.approx(REAL_TOTAL, abs=1)
    parts = sum(c["litres"]["value"] for c in r["by_client"]) + r["overhead"]["litres"]["value"] + r["unmatched_jobs"]["litres"]["value"]
    assert parts == pytest.approx(REAL_TOTAL, abs=1)


def test_report_is_traceable_but_never_called_verified_and_has_no_unassigned_client():
    r = fleet_report()
    text = json.dumps({k: v for k, v in r.items() if k != "sources"}, default=str).lower()
    assert "traceable" in text and "not been checked by an outside auditor" in text
    assert "verified" not in text
    assert all(c["name"] != "Unassigned" for c in r["by_client"])


def test_every_cited_source_is_listed_with_its_link_status():
    r = fleet_report()
    listed = {s["source_id"] for s in r["sources"]}
    for fig in (r["totals"]["litres"], r["totals"]["co2e_kg"], r["overhead"]["litres"]):
        assert set(fig["source_ids"]) <= listed
    assert all("link_status" in s for s in r["sources"])


def test_report_names_the_findings_ideas_limits_and_label_meanings():
    r = fleet_report()
    assert r["findings"] and r["ideas"] and r["limits"]
    assert [x["label"] for x in r["labels"]] == ["measured", "allocated", "estimated"]
    assert all(i["litres_saved"]["label"] == "estimated" for i in r["ideas"] if i["litres_saved"])
    assert any("frozen" in line.lower() for line in r["limits"])


def test_client_statement_covers_one_client_by_month_and_leaves_company_findings_out():
    r = fleet_report(client_id="C09")
    assert r["meta"]["client"] == "Client farm 09"
    assert r["totals"]["litres"]["value"] == pytest.approx(sum(m["litres"]["value"] for m in r["months"]), abs=0.1)
    assert "by_client" not in r and "findings" not in r and "ideas" not in r
    assert r["sources"] and r["method"]


def test_demo_data_is_flagged_and_dated():
    m = fleet_report()["meta"]
    assert m["demo_data"] is True and "1 May 2025" in m["period"] and m["generated_at"]
