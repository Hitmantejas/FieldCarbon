"""F5 P1: possible causes for job outliers, heavy non-work fuel and frozen recorders, plus the maintenance loader."""
from __future__ import annotations

import pandas as pd
import pytest

from backend.fleet import data
from backend.tools import diagnose_anomaly as dx
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.finding_id import DIAGNOSABLE_KINDS

STATUSES = {"supported", "not_supported", "cannot_test"}


def _ctx(**kw) -> dx.Context:
    base = dict(
        dispenses=pd.DataFrame(columns=["depot_id", "machine_id", "ts", "litres", "month"]), burned={},
        night=pd.DataFrame(columns=["machine_id", "ts", "litres", "month"]),
        frozen=pd.DataFrame(columns=["machine_id", "month", "hours"]),
        depot_rows=[], deliveries=pd.DataFrame(columns=["depot_id", "ts", "supplier", "doc_no", "litres"]),
        note_counts=None, site_sources={"S9": "test_source"}, stock_tolerance_l=100.0)
    return dx.Context(**{**base, **kw})


def _fig(value, unit="L", label="measured"):
    return {"value": value, "unit": unit, "label": label, "how": "test", "source_ids": ["test_source"], "low": None, "high": None}


# --- the maintenance loader -------------------------------------------------------------------------------------------

def test_maintenance_loader_reads_dates_and_every_row():
    m = data.maintenance()
    assert len(m) == 36 and pd.api.types.is_datetime64_any_dtype(m.date)
    assert {"event_id", "machine_id", "date", "event_type"} <= set(m.columns)
    assert m.machine_id.isin(data.machines().index).all()


# --- job_outlier ------------------------------------------------------------------------------------------------------

def _jobs(target_load=50.0, target_idle=None, n=9, start="2025-06-20 08:00"):
    """Eight ordinary jobs (load 50%, idle 0.2) and the outlier J9 on machine S9-T1."""
    rows = [dict(job_id=f"J{k}", site_id="S9", machine_id="S9-T2", operation_code="ploughing", start_ts=pd.Timestamp("2025-06-01"),
                 hours=2.0, litres=40.0, mean_load_pct=50.0, idle_ratio=0.2, date_basis="real") for k in range(1, n)]
    rows.append(dict(job_id="J9", site_id="S9", machine_id="S9-T1", operation_code="ploughing", start_ts=pd.Timestamp(start),
                     hours=2.0, litres=60.0, mean_load_pct=target_load, idle_ratio=target_idle, date_basis="real"))
    return pd.DataFrame(rows)


def _outlier(direction="more", dev=50.0):
    return {"kind": "job_outlier", "site_id": "S9", "machine_id": "S9-T1", "month": "2025-06", "job_id": "J9",
            "direction": direction, "difference_pct": dev if direction == "more" else -dev, "litres": _fig(20.0)}


def test_high_engine_load_is_supported_when_load_rises_at_least_half_as_much_as_fuel():
    f = _outlier(dev=50.0)  # 50% more fuel per hour
    assert dx.high_engine_load(f, _ctx(jobs=_jobs(target_load=65.0)))["status"] == "supported"      # load +30% >= 25%
    assert dx.high_engine_load(f, _ctx(jobs=_jobs(target_load=55.0)))["status"] == "not_supported"  # load +10%
    assert dx.high_engine_load(f, _ctx(jobs=_jobs(target_load=35.0)))["status"] == "not_supported"  # wrong direction
    r = dx.high_engine_load(f, _ctx(jobs=_jobs(target_load=65.0)))
    assert r["evidence"]["value"] == 65.0 and r["evidence"]["unit"] == "%" and r["explains_pct"] is None


def test_high_engine_load_cannot_be_tested_without_a_load_reading():
    assert dx.high_engine_load(_outlier(), _ctx(jobs=_jobs(target_load=float("nan"))))["status"] == "cannot_test"


def test_idling_explains_only_a_job_that_burned_less_per_hour():
    less = _outlier("less", 40.0)
    assert dx.long_idling(less, _ctx(jobs=_jobs(target_idle=0.35)))["status"] == "supported"        # +15 points
    assert dx.long_idling(less, _ctx(jobs=_jobs(target_idle=0.25)))["status"] == "not_supported"    # +5 points
    assert dx.long_idling(_outlier("more"), _ctx(jobs=_jobs(target_idle=0.6)))["status"] == "not_supported"
    assert dx.long_idling(less, _ctx(jobs=_jobs(target_idle=None)))["status"] == "cannot_test"      # no idle data (S1)


def test_a_frozen_recorder_in_the_job_month_cannot_be_placed_in_the_job():
    f = _outlier()
    none = dx.recorder_froze_during_job(f, _ctx(jobs=_jobs()))
    assert none["status"] == "not_supported" and none["evidence"]["value"] == 0
    frozen = pd.DataFrame([{"machine_id": "S9-T1", "month": "2025-06", "hours": 4.0}])
    some = dx.recorder_froze_during_job(f, _ctx(jobs=_jobs(), frozen=frozen))
    assert some["status"] == "cannot_test" and some["evidence"]["value"] == 4.0


def test_recent_maintenance_looks_back_thirty_days_before_the_job():
    def m(day):
        return pd.DataFrame([{"event_id": "M1", "machine_id": "S9-T1", "date": pd.Timestamp(day), "event_type": "Fuel filter replaced"}])
    f = _outlier()
    near = dx.recent_maintenance(f, _ctx(jobs=_jobs(), maintenance=m("2025-06-01")))
    assert near["status"] == "supported" and near["evidence"]["value"] == 19 and near["evidence"]["unit"] == "days"
    assert dx.recent_maintenance(f, _ctx(jobs=_jobs(), maintenance=m("2025-04-01")))["status"] == "not_supported"
    after = dx.recent_maintenance(f, _ctx(jobs=_jobs(), maintenance=m("2025-07-01")))
    assert after["status"] == "not_supported" and after["evidence"] is None


# --- high_non_work_share ----------------------------------------------------------------------------------------------

def _ledger():
    """Three S9 machines: T1 burns 200 L more road fuel than the middle machine; idling and tool-not-working are typical."""
    rows = []
    for m, road in (("S9-T1", 300.0), ("S9-T2", 100.0), ("S9-T3", 100.0)):
        rows += [dict(site_id="S9", machine_id=m, operation_code="ploughing", litres=1000.0),
                 dict(site_id="S9", machine_id=m, operation_code="other_road_transport", litres=road),
                 dict(site_id="S9", machine_id=m, operation_code="other_idle", litres=50.0),
                 dict(site_id="S9", machine_id=m, operation_code="other_implement_nonproductive", litres=50.0)]
    return pd.DataFrame(rows)


def test_the_category_carrying_the_excess_is_supported():
    f = {"kind": "high_non_work_share", "site_id": "S9", "machine_id": "S9-T1", "litres": _fig(150.0, label="allocated")}
    ctx = _ctx(ledger=_ledger())
    road, idle = dx.non_work_road_transport(f, ctx), dx.non_work_idle(f, ctx)
    assert road["status"] == "supported" and road["evidence"]["label"] == "allocated" and road["explains_pct"] == 100.0
    assert idle["status"] == "not_supported" and idle["evidence"]["value"] < 0


# --- data_gap ---------------------------------------------------------------------------------------------------------

def _frozen(rows):
    return pd.DataFrame(rows, columns=["machine_id", "month", "hours"])


def test_a_gap_in_one_month_is_a_one_off_and_not_recurring():
    f = {"kind": "data_gap", "site_id": "S9", "machine_id": "S9-T1", "litres": _fig(10.0, "h")}
    ctx = _ctx(frozen=_frozen([("S9-T1", "2025-06", 8.0), ("S9-T1", "2025-07", 2.0), ("S9-T1", "2025-08", 0.5)]))
    one, again = dx.gap_in_one_period(f, ctx), dx.gap_recurs(f, ctx)
    assert one["status"] == "supported" and one["explains_pct"] == 80.0  # the 0.5 h month is below the finding's floor
    assert again["status"] == "not_supported" and again["evidence"]["value"] == 2


def test_a_gap_in_three_months_recurs():
    f = {"kind": "data_gap", "site_id": "S9", "machine_id": "S9-T1", "litres": _fig(9.0, "h")}
    ctx = _ctx(frozen=_frozen([("S9-T1", m, 3.0) for m in ("2025-06", "2025-08", "2025-11")]))
    assert dx.gap_recurs(f, ctx)["status"] == "supported"
    assert dx.gap_in_one_period(f, ctx)["status"] == "not_supported"


def test_a_site_wide_problem_needs_other_machines_frozen_in_the_same_months():
    f = {"kind": "data_gap", "site_id": "S9", "machine_id": "S9-T1", "litres": _fig(6.0, "h")}
    mine = [("S9-T1", "2025-06", 3.0), ("S9-T1", "2025-08", 3.0)]
    shared = dx.site_wide_logging_problem(f, _ctx(frozen=_frozen(mine + [("S9-T2", "2025-06", 2.0)])))
    assert shared["status"] == "supported" and shared["evidence"]["value"] == 1
    alone = dx.site_wide_logging_problem(f, _ctx(frozen=_frozen(mine + [("S8-T2", "2025-06", 2.0)])))  # other site
    assert alone["status"] == "not_supported"
    thin = dx.site_wide_logging_problem(f, _ctx(frozen=_frozen([("S9-T1", "2025-06", 0.5)])))
    assert thin["status"] == "cannot_test"


# --- on the real data -------------------------------------------------------------------------------------------------

def test_every_anomaly_kind_can_now_be_diagnosed():
    assert {"job_outlier", "high_non_work_share", "data_gap"} <= DIAGNOSABLE_KINDS
    assert all(f["diagnosable"] for f in detect_anomalies()["findings"])


@pytest.mark.parametrize("kind", ["job_outlier", "high_non_work_share", "data_gap"])
def test_real_findings_of_each_new_kind_give_sourced_labelled_results(kind):
    found = [f for f in detect_anomalies()["findings"] if f["kind"] == kind]
    if not found:
        pytest.skip(f"no {kind} finding in this data")
    for f in found:
        d = dx.diagnose_anomaly(f["id"])
        assert [h["id"] for h in d["hypotheses"]] and {h["status"] for h in d["hypotheses"]} <= STATUSES
        assert d["hypotheses"] == dx.order(d["hypotheses"])
        for h in d["hypotheses"]:
            if h["evidence"] is not None:
                assert h["evidence"]["source_ids"] and h["evidence"]["label"] in {"measured", "allocated"}
                assert h["evidence_measures"]
