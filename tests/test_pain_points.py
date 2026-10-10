"""Band rating of farm L/ha against the Iowa State reference range (CLAUDE.md section 7, Rating)."""
import pandas as pd
import pytest

from backend.emissions.pain_points import above_range, not_working_share, rate_operations, reference_range


def farm(op: str, hectares: float, litres: float) -> pd.DataFrame:
    return pd.DataFrame([{"operation_code": op, "area_worked_ha": hectares, "litres_working": litres}])


def rating(op: str, hectares: float, litres: float):
    return rate_operations(farm(op, hectares, litres))[0]


def test_reference_uses_published_range_when_present():
    ref = reference_range("ploughing")
    assert (ref.low, ref.typical, ref.high) == pytest.approx((10.29, 13.10, 17.77))


def test_reference_falls_back_to_published_band_pct():
    ref = reference_range("mulching")  # shredding stalks: 4.21 L/ha, no range, +-35%
    assert (ref.low, ref.typical, ref.high) == pytest.approx((4.21 * 0.65, 4.21, 4.21 * 1.35))


def test_composite_reference_sums_the_listed_rows():
    ref = reference_range("seed_drill_combination")  # seedbed conditioner + grain drill
    assert ref.typical == pytest.approx(8.42 + 2.81)
    assert ref.low == pytest.approx((8.42 + 2.81) * 0.65)
    assert ref.high == pytest.approx((8.42 + 2.81) * 1.35)


def test_operation_without_reference_has_none():
    assert reference_range("transport") is None


@pytest.mark.parametrize("l_per_ha, band", [
    (8.0, "below_typical"),
    (15.0, "typical"),
    (21.3, "above_typical"),   # over 17.77, within +35% of it (23.99)
    (25.0, "well_above"),
])
def test_bands_for_ploughing(l_per_ha, band):
    assert rating("ploughing", 100, l_per_ha * 100).band == band


def test_litres_at_stake_is_a_range():
    r = rating("ploughing", 100, 2130)  # 21.3 L/ha
    assert r.litres_at_stake_low == pytest.approx((21.3 - 17.77) * 100)    # excess over top of range
    assert r.litres_at_stake_high == pytest.approx((21.3 - 13.10) * 100)   # excess over typical


def test_nothing_at_stake_when_not_above_range():
    r = rating("ploughing", 100, 1500)
    assert r.litres_at_stake_low == 0 and r.litres_at_stake_high == 0


def test_too_little_area_is_not_rated():
    assert rating("ploughing", 1.0, 30).band == "insufficient_data"


def test_operation_without_reference_is_not_rated():
    assert rating("transport", 50, 500).band == "no_reference"


def test_rows_of_one_operation_are_pooled_before_rating():
    df = pd.concat([farm("ploughing", 60, 1500), farm("ploughing", 40, 1000)])
    r = rate_operations(df)[0]
    assert r.hectares == 100 and r.litres == 2500 and r.l_per_ha == pytest.approx(25.0)


def test_rating_is_traceable_and_labelled():
    r = rating("ploughing", 100, 1500)
    assert r.label == "allocated"
    assert r.match_quality == "direct"
    assert r.reference.source_ids == ("isu_a3_27",)


def test_not_working_share_counts_only_unproductive_classes():
    s = pd.DataFrame({
        "activity_class": ["field_work", "implement_nonproductive", "road_transport", "idle", "offroad_unassigned"],
        "litres": [60.0, 20.0, 8.0, 2.0, 10.0],
    })
    r = not_working_share(s)
    assert r.litres == 30.0 and r.total_litres == 100.0 and r.share_pct == pytest.approx(30.0)
    assert r.label == "allocated"


def test_rating_explains_itself_in_plain_words():
    r = rating("ploughing", 100, 2130)
    assert "21.3 L/ha" in r.how and "10.3 to 17.8" in r.how and "isu_a3_27" in r.how


def test_unrated_operations_say_why():
    assert "minimum 5" in rating("ploughing", 1.0, 30).how
    assert "No published" in rating("transport", 50, 500).how


def test_above_range_summary_adds_up_only_the_pain_points():
    df = pd.concat([farm("ploughing", 100, 2130), farm("mowing", 50, 100), farm("fertilizing", 50, 40)])
    s = above_range(rate_operations(df))
    assert s.count == 1
    assert s.litres_low == pytest.approx((21.3 - 17.77) * 100)
    assert s.litres_high == pytest.approx((21.3 - 13.10) * 100)
