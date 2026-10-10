"""Farm totals and breakdowns: figures carry labels, ranges and a traceable 'how'."""
import pandas as pd
import pytest

from backend.emissions.farm_summary import breakdown, fuel_price_range, summarise

ROWS = pd.DataFrame([
    # tractor, class, operation, label, field, hours, litres
    ("tractor_1", "field_work", "ploughing", "measured", "field_001", 2.0, 40.0),
    ("tractor_1", "field_work", "ploughing", "measured", None, 1.0, 10.0),
    ("tractor_2", "implement_nonproductive", "ploughing", "allocated", "field_001", 1.0, 20.0),
    ("tractor_2", "idle", None, "allocated", None, 3.0, 10.0),
    ("tractor_2", "data_gap", None, "excluded", None, 5.0, 0.0),
], columns=["tractor_id", "activity_class", "operation_code", "attribution_label", "field_id", "hours", "litres"])


def test_price_range_spans_all_months_and_is_sourced():
    p = fuel_price_range()
    assert p.low == pytest.approx(0.749) and p.high == pytest.approx(1.176)
    assert p.source_id == "defra_ukammg"


def test_totals_are_measured_and_traceable():
    s = summarise(ROWS)
    assert s.litres.value == 80.0 and s.litres.label == "measured"
    assert s.co2e_kg.value == pytest.approx(80 * 3.38206)
    assert "3.38206" in s.co2e_kg.how
    assert s.cost_gbp.low == pytest.approx(80 * 0.749) and s.cost_gbp.high == pytest.approx(80 * 1.176)
    assert s.cost_gbp.label == "estimated"


def test_operation_breakdown_separates_non_working_time():
    rows = {r.key: r for r in breakdown(ROWS, "operation")}
    assert rows["ploughing"].litres.value == 50.0
    assert rows["implement_nonproductive"].litres.value == 20.0
    assert rows["idle"].litres.value == 10.0
    assert "data_gap" not in rows  # zero litres: excluded time is reported elsewhere


def test_breakdown_label_is_the_weakest_of_its_inputs():
    rows = {r.key: r for r in breakdown(ROWS, "tractor")}
    assert rows["tractor_1"].litres.label == "measured"
    assert rows["tractor_2"].litres.label == "allocated"


def test_field_breakdown_is_always_allocated_and_keeps_unassigned():
    rows = {r.key: r for r in breakdown(ROWS, "field")}
    assert rows["field_001"].litres.label == "allocated"
    assert rows["unassigned"].litres.value == 20.0


def test_shares_sum_to_100_and_sorted_by_litres():
    rows = breakdown(ROWS, "operation")
    assert sum(r.share_pct for r in rows) == pytest.approx(100.0)
    assert [r.litres.value for r in rows] == sorted((r.litres.value for r in rows), reverse=True)


def test_unknown_grouping_is_rejected():
    with pytest.raises(ValueError):
        breakdown(ROWS, "colour")
