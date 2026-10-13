"""The fleet tables written to data/fleet: ties to real totals, labelled synthetic parts, planted problems."""
import re
from pathlib import Path

import pandas as pd
import pytest

FLEET = Path(__file__).resolve().parents[1] / "data" / "fleet"
START, END = pd.Timestamp("2025-05-01"), pd.Timestamp("2026-04-30 23:59:59")
pytestmark = pytest.mark.skipif(not (FLEET / "jobs.csv").exists(), reason="run python -m backend.fleet.build first")


def table(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(FLEET / f"{name}.csv", **kw)


def jobs() -> pd.DataFrame:
    return table("jobs", parse_dates=["start_ts", "date_real"])


def test_every_table_is_present_with_its_key_columns():
    expected = {
        "sites": ["site_id", "name", "country", "data_kind", "source_id"],
        "machines": ["machine_id", "site_id", "display_name", "rated_kw", "fuel_type"],
        "operations": ["operation_code", "display_name", "category", "site_kind"],
        "clients": ["client_id", "name", "site_id", "is_synthetic"],
        "fields": ["field_id", "site_id", "client_id", "area_ha", "area_method"],
        "operators": ["operator_id", "site_id", "role", "is_synthetic"],
        "jobs": ["job_id", "site_id", "machine_id", "operator_id", "client_id", "field_id", "operation_code", "start_ts",
                 "hours", "litres", "area_ha", "litres_label", "area_label", "date_basis", "synthetic_columns"],
        "other_activity": ["machine_id", "month", "activity_class", "hours", "litres"],
        "depots": ["depot_id", "site_id", "capacity_l", "opening_stock_l"],
        "fuel_deliveries": ["delivery_id", "depot_id", "ts", "supplier", "doc_no", "litres", "unit_price_gbp"],
        "fuel_dispenses": ["dispense_id", "depot_id", "machine_id", "operator_id", "ts", "litres"],
        "depot_stock_readings": ["depot_id", "date", "dip_litres"],
        "maintenance_events": ["event_id", "machine_id", "date", "event_type", "job_hours_at_event", "note"],
        "ground_truth_anomalies": ["anomaly_id", "kind", "site_id", "machine_id", "when", "description", "expected_signal"],
    }
    for name, cols in expected.items():
        assert set(cols) <= set(table(name).columns), name


def test_real_litres_are_untouched_and_tie_to_the_sources():
    j = jobs()
    other = table("other_activity")
    s1 = j[j.site_id == "S1"].litres.sum() + other[other.machine_id.str.startswith("S1")].litres.sum()
    assert s1 == pytest.approx(10813.69, abs=0.5)
    assert j[j.site_id == "S2"].litres.sum() == pytest.approx(5333.0, abs=1.0)
    assert j[j.site_id == "S3"].litres.sum() == pytest.approx(346.0, abs=5.0)


def test_all_jobs_fall_in_the_company_year():
    j = jobs()
    assert j.start_ts.min() >= START and (j.start_ts + pd.to_timedelta(j.hours, unit="h")).max() <= END


def test_vineyard_dates_are_the_real_dates_shifted_exactly_four_years():
    v = jobs().query("site_id == 'S2'")
    assert ((v.date_real + pd.DateOffset(years=4)) == v.start_ts).all()
    assert set(v.date_basis) == {"real+4y"}


def test_other_sites_are_scheduled_without_overlap_on_each_machine():
    j = jobs().query("site_id != 'S2'").sort_values(["machine_id", "start_ts"])
    end = j.start_ts + pd.to_timedelta(j.hours, unit="h")
    nxt = j.groupby("machine_id").start_ts.shift(-1)
    assert (nxt.isna() | (nxt >= end)).all()
    assert set(j.date_basis) == {"assigned"}


def test_operators_are_pseudonyms_with_nothing_else_attached():
    ops = table("operators")
    assert list(ops.columns) == ["operator_id", "site_id", "role", "is_synthetic"]
    assert ops.operator_id.str.fullmatch(r"OP-\d\d").all() and ops.is_synthetic.all()
    j = jobs().merge(ops, on="operator_id", suffixes=("", "_op"))
    assert len(j) == len(jobs()) and (j.site_id == j.site_id_op).all()


def test_synthetic_columns_are_declared_on_every_job():
    j = jobs()
    assert j.synthetic_columns.str.contains("operator_id").all() and j.synthetic_columns.str.contains("client_id").all()
    assert j[j.site_id != "S2"].synthetic_columns.str.contains("start_ts").all()
    assert not j[j.site_id == "S2"].synthetic_columns.str.contains("start_ts").any()


def test_clients_own_fields_and_jobs_follow_their_field():
    f, c, j = table("fields"), table("clients"), jobs()
    assert set(f.client_id) <= set(c.client_id)
    m = j.merge(f[["field_id", "client_id"]], on="field_id", how="left", suffixes=("", "_f"))
    assert (m.client_id.fillna("none") == m.client_id_f.fillna("none")).all()
    assert j[j.field_id.isna()].client_id.isna().all()


def monthly(frame: pd.DataFrame, col: str) -> pd.Series:
    return frame.groupby(["machine_id", frame[col].dt.to_period("M")]).litres.sum()


def test_dispensed_fuel_follows_burned_fuel_except_for_the_planted_machine_month():
    j, other, disp = jobs(), table("other_activity"), table("fuel_dispenses", parse_dates=["ts"])
    burned = monthly(j, "start_ts").add(
        other.assign(m=pd.PeriodIndex(other.month, freq="M")).groupby(["machine_id", "m"]).litres.sum().rename_axis(["machine_id", "start_ts"]),
        fill_value=0)
    given = monthly(disp, "ts")
    ratio = (given / burned).dropna()
    truth = table("ground_truth_anomalies").query("kind == 'over_dispense'").iloc[0]
    planted = (truth.machine_id, pd.Period(truth["when"], freq="M"))
    assert ratio.loc[planted] >= 1.15
    normal = ratio.drop(planted)
    assert normal.between(0.95, 1.06).all(), normal[~normal.between(0.95, 1.06)]


def test_planted_over_dispense_happens_at_night_on_that_machine_only():
    disp = table("fuel_dispenses", parse_dates=["ts"])
    night = disp[(disp.ts.dt.hour >= 22) | (disp.ts.dt.hour < 5)]
    truth = table("ground_truth_anomalies").query("kind == 'over_dispense'").iloc[0]
    assert len(night) >= 4 and set(night.machine_id) == {truth.machine_id}


def test_planted_stock_loss_shows_as_a_gap_between_book_and_dip_stock():
    d, disp, dips, depots = table("fuel_deliveries", parse_dates=["ts"]), table("fuel_dispenses", parse_dates=["ts"]), table("depot_stock_readings", parse_dates=["date"]), table("depots")
    truth = table("ground_truth_anomalies").query("kind == 'unlogged_withdrawal'").iloc[0]
    depot = f"{truth.site_id}-D1"
    opening = depots.set_index("depot_id").opening_stock_l[depot]
    after = pd.Timestamp(truth["when"]) + pd.Timedelta(days=20)
    book = opening + d[(d.depot_id == depot) & (d.ts <= after)].litres.sum() - disp[(disp.depot_id == depot) & (disp.ts <= after)].litres.sum()
    dip = dips[(dips.depot_id == depot) & (dips.date <= after)].sort_values("date").iloc[-1].dip_litres
    assert book - dip >= 800


def test_planted_duplicate_delivery_note_exists_once_as_a_pair():
    d = table("fuel_deliveries")
    truth = table("ground_truth_anomalies").query("kind == 'duplicate_delivery_note'").iloc[0]
    rows = d[d.doc_no == truth.description.split()[-1]]
    assert len(rows) == 2 and rows.litres.nunique() == 1


def test_delivery_prices_follow_the_real_defra_series_within_three_percent():
    d, p = table("fuel_deliveries", parse_dates=["ts"]), table("../reference/ref_fuel_prices", parse_dates=["price_month"])
    price = p.set_index(p.price_month.dt.to_period("M")).price_per_litre
    ratio = d.unit_price_gbp.values / price.reindex(d.ts.dt.to_period("M")).values
    assert ((ratio > 0.97) & (ratio < 1.03)).all()


def test_depot_readings_stay_inside_the_tank():
    dips, depots = table("depot_stock_readings"), table("depots").set_index("depot_id")
    assert (dips.dip_litres >= 0).all()
    assert (dips.dip_litres <= dips.depot_id.map(depots.capacity_l) * 1.01).all()


def test_maintenance_events_are_in_the_year_and_hours_rise_per_machine():
    m = table("maintenance_events", parse_dates=["date"])
    assert m.date.between(START, END).all()
    assert (m.sort_values("date").groupby("machine_id").job_hours_at_event.diff().dropna() >= 0).all()


def test_no_coordinates_anywhere():
    bad = re.compile(r"lat|lon|gps|coord", re.I)
    for path in FLEET.glob("*.csv"):
        assert not [c for c in pd.read_csv(path, nrows=1).columns if bad.search(c)], path.name


def test_the_build_is_deterministic(tmp_path):
    from backend.fleet.build import write
    from backend.fleet.real import RAW

    if not ((RAW / "vineyard" / "Dataset.csv").exists() and (RAW / "tumosan" / "extracted").exists()):
        pytest.skip("raw datasets not downloaded")
    write(tmp_path / "a")
    write(tmp_path / "b")
    for path in (tmp_path / "a").glob("*.csv"):
        assert path.read_bytes() == (tmp_path / "b" / path.name).read_bytes(), path.name
    assert (tmp_path / "a" / "jobs.csv").read_bytes() == (FLEET / "jobs.csv").read_bytes()  # and matches what is committed
