"""Real-data loaders for the three fleet sites: litres, hours and areas must tie to the sources."""
import pandas as pd
import pytest

from backend.fleet.real import MAX_JOB_HOURS, RAW, tum_jobs, tumosan_jobs, vineyard_jobs

needs_vineyard = pytest.mark.skipif(not (RAW / "vineyard" / "Dataset.csv").exists(), reason="vineyard CSV not downloaded")
needs_tumosan = pytest.mark.skipif(not (RAW / "tumosan" / "extracted").exists(), reason="Tumosan files not extracted")


def test_tum_jobs_and_other_fuel_tie_to_the_farm_a_total():
    jobs, other = tum_jobs()
    assert jobs.litres.sum() + other.litres.sum() == pytest.approx(10813.69, abs=0.5)
    assert other[other.activity_class == "data_gap"].litres.sum() == 0   # frozen-logger hours carry no fuel
    assert set(other.activity_class) <= {"idle", "implement_nonproductive", "offroad_unassigned", "road_transport", "data_gap"}


def test_tum_jobs_are_real_groups_split_into_working_days():
    jobs, _ = tum_jobs()
    assert jobs.hours.max() <= MAX_JOB_HOURS + 1e-9
    assert jobs.hours.sum() == pytest.approx(pd.read_csv("data/aggregated/farm_a_operations_summary.csv")
                                             .query("activity_class == 'field_work' and operation_code == operation_code").hours.sum(), abs=0.01)
    assert jobs.job_id.is_unique and jobs.machine_id.str.startswith("S1-T").all()
    assert set(jobs.litres_label) == {"measured"} and jobs.field_id.notna().mean() > 0.85


def test_tum_ploughing_litres_per_hectare_agree_with_the_pain_point_figure():
    jobs, _ = tum_jobs()
    p = jobs[jobs.operation_code == "ploughing"]
    assert 15 < p.litres.sum() / p.area_ha.sum() < 28   # the pain-point screen shows 21.3 L/ha


@needs_vineyard
def test_vineyard_jobs_match_the_published_dataset():
    jobs = vineyard_jobs()
    assert len(jobs) == 374
    assert jobs.litres.sum() == pytest.approx(5333.0, abs=1.0)
    assert jobs.hours.sum() == pytest.approx(716.9, abs=0.2)
    assert jobs.area_ha.sum() == pytest.approx(796.1, abs=0.2)
    assert set(jobs.machine_id) == {f"S2-T{i}" for i in range(1, 7)}
    assert set(jobs.litres_label) == {"measured"} and set(jobs.area_label) == {"allocated"}
    assert jobs.date_real.min() == pd.Timestamp("2021-05-03 00:00") or jobs.date_real.min() < pd.Timestamp("2021-05-04")


@needs_vineyard
def test_every_vineyard_activity_has_an_operation_code():
    jobs = vineyard_jobs()
    assert jobs.operation_code.notna().all() and jobs.operation_code.str.startswith("vy_").all()
    assert jobs.operation_code.nunique() == 14


@needs_tumosan
def test_tumosan_sessions_are_ten_real_jobs_with_estimated_area():
    jobs = tumosan_jobs()
    assert len(jobs) == 10 and jobs.machine_id.eq("S3-T1").all()
    assert jobs.hours.sum() == pytest.approx(24.7, abs=0.1)
    assert jobs.litres.sum() == pytest.approx(346.0, abs=5.0)
    assert (jobs.operation_code == "ploughing").sum() == 8 and (jobs.operation_code == "rotary_tilling").sum() == 2
    assert (jobs.area_ha > 0).all() and set(jobs.area_label) == {"allocated"}


@needs_tumosan
def test_tumosan_litres_per_hectare_are_plausible_for_ploughing():
    jobs = tumosan_jobs()
    plough = jobs[jobs.operation_code == "ploughing"]
    assert 5 < plough.litres.sum() / plough.area_ha.sum() < 60
