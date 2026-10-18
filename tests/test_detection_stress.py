import numpy as np
import pandas as pd

from backend.fleet import data
from backend.tools.reconcile_fuel import reconcile_fuel
from evals import detection_stress as ds


def test_wilson_interval_is_wide_for_few_trials_and_stays_inside_zero_to_one():
    assert ds.wilson(0, 40)[0] == 0.0 and ds.wilson(40, 40)[1] == 1.0
    low, high = ds.wilson(20, 40)
    assert low < 0.5 < high and high - low > 0.25
    assert ds.wilson(5, 10)[1] - ds.wilson(5, 10)[0] > ds.wilson(50, 100)[1] - ds.wilson(50, 100)[0]


def test_swapped_tables_are_restored_and_the_ledger_follows_the_jobs():
    before = data.ledger().litres.sum()
    doubled = data.jobs().assign(litres=lambda d: d.litres * 2)
    with ds.tables(jobs=doubled):
        assert data.ledger().litres.sum() > before
    assert data.ledger().litres.sum() == before
    assert data.jobs() is not doubled


def test_tables_are_restored_even_when_the_run_fails():
    try:
        with ds.tables(jobs=data.jobs().head(5)):
            raise RuntimeError
    except RuntimeError:
        pass
    assert len(data.jobs()) > 5


def test_tally_separates_new_findings_from_hidden_baseline_findings():
    baseline = [{"kind": "job_outlier", "job_id": "J1"}, {"kind": "job_outlier", "job_id": "J2"}]
    tally = ds.Tally(baseline)
    found = [{"kind": "job_outlier", "job_id": "J1"}, {"kind": "job_outlier", "job_id": "J3"},
             {"kind": "job_outlier", "job_id": "J4"}]  # J3 is the injected one, J4 is new, J2 was hidden
    tally.add(found, mine=True, litres=40.0)
    row = tally.row(50)
    assert (row["detected"], row["new_unrelated_findings_per_trial"], row["baseline_findings_hidden_per_trial"]) == (1, 1.0, 1.0)


def test_a_large_unlogged_withdrawal_is_found():
    dips = data.stock_readings()
    row = dips.iloc[1]
    lowered = dips.assign(dip_litres=np.where((dips.depot_id == row.depot_id) & (dips.date >= row.date), dips.dip_litres - 900, dips.dip_litres))
    with ds.tables(stock_readings=lowered):
        found = reconcile_fuel()["findings"]
    assert any(f["kind"] == "stock_gap" and f["depot_id"] == row.depot_id and f["month"] == str(row.date.to_period("M")) for f in found)


def test_a_one_per_cent_typo_hides_a_duplicate_note_from_the_exact_match():
    deliveries = data.deliveries()
    planted = reconcile_fuel()["findings"]
    skip = {f["doc_no"] for f in planted if f["kind"] == "duplicate_delivery_note"}
    original = deliveries[~deliveries.doc_no.isin(skip)].iloc[0]
    twin = original.copy()
    twin["litres"] = round(original.litres * 1.01, 1)
    doubled = pd.concat([deliveries, twin.to_frame().T], ignore_index=True).astype(deliveries.dtypes)
    with ds.tables(deliveries=doubled):
        found = reconcile_fuel()["findings"]
    assert not any(f["kind"] == "duplicate_delivery_note" and f["doc_no"] == original.doc_no for f in found)
