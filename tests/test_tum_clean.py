import numpy as np
import pandas as pd
import pytest

from tum_clean import (Params, StreamState, clean_chunk, clean_stream, derive_time, field_file_summary,
                       implement_class, load_worktype_map, rename_and_null_sentinels, split_trailing_run,
                       tractor_from_model)

WT = load_worktype_map()


def td(seconds):
    return [str(pd.Timedelta(seconds=s)) for s in seconds]


def raw_frame(seconds, fuel=10.0, work="not working", implement=None, status="Driving Off-Road",
              speed=1.0, rpm=1200.0, model="Fendt 211", lat=None):
    n = len(seconds)
    rep = lambda v: v if isinstance(v, list) else [v] * n
    return pd.DataFrame({
        "Time_(s)": td(seconds),
        "EngSpeed_(RPM)": rep(rpm),
        "EngPercentLoadAtCurrentSpeed_(%)": [50.0] * n,
        "EngFuelRate_(L/h)": rep(fuel),
        "SpeedOverGround_(m/s)": rep(speed),
        "Latitude_(°)": rep(lat) if lat is not None else [48.0 + 1e-6 * i for i in range(n)],  # moving
        "Longitude_(°)": [11.0] * n,
        "Altitude_(m)": [500.0] * n,
        "RearPTOOutputShaftSpeed_(RPM)": [0.0] * n,
        "RearDraft_(N)": [0.0] * n,
        "WorkType_[-]": rep(work),
        "Tractor_Model_[-]": [model] * n,
        "Implement_Model_[-]": rep(implement),
        "Implement_Width_(m)": [3.0 if implement else np.nan] * n,
        "Status_[-]": rep(status),
    })


def test_sentinels_become_null():
    raw = raw_frame([0, 0.1])
    raw["EngFuelRate_(L/h)"] = [3276.75, 5.0]
    raw["RearDraft_(N)"] = [335350.0, -100.0]
    df = rename_and_null_sentinels(raw)
    assert np.isnan(df["fuel_rate_lph"].iloc[0]) and df["fuel_rate_lph"].iloc[1] == 5.0
    assert np.isnan(df["rear_draft_n"].iloc[0]) and df["rear_draft_n"].iloc[1] == -100.0


def test_fuel_integration_caps_gaps_and_splits_sessions():
    # 10 Hz for 1 s, a 0.5 s dropout (capped at 0.5 < 1.0), then a 120 s gap (new session).
    secs = [round(0.1 * i, 1) for i in range(11)] + [1.5, 121.5, 121.6]
    df = derive_time(rename_and_null_sentinels(raw_frame(secs, fuel=36.0)), StreamState(), Params())
    assert df["session_id"].tolist() == [0] * 12 + [1, 1]
    assert df["dt_s"].iloc[0] == 0 and df["dt_s"].iloc[12] == 0
    assert df["dt_s"].sum() == pytest.approx(1.0 + 0.5 + 0.1)
    assert df["fuel_l"].sum() == pytest.approx(36.0 * 1.6 / 3600.0)


def test_dt_cap_applies():
    df = derive_time(rename_and_null_sentinels(raw_frame([0, 5, 10], fuel=36.0)), StreamState(), Params(dt_cap_s=1.0))
    assert df["session_id"].tolist() == [0, 0, 0]
    assert df["dt_s"].tolist() == [0.0, 1.0, 1.0]


def test_chunked_equals_whole():
    secs = [round(0.1 * i, 1) for i in range(50)] + [100 + 0.1 * i for i in range(50)]
    work = ["not working"] * 10 + ["Power harrowing"] * 20 + ["not working"] * 70
    impl = ["Lemken Zirkon"] * 60 + [None] * 40
    raw = raw_frame(secs, work=work, implement=impl)
    whole = clean_chunk(raw, StreamState(), WT)
    state, parts = StreamState(), []
    for start in range(0, len(raw), 7):
        parts.append(clean_chunk(raw.iloc[start:start + 7].reset_index(drop=True), state, WT))
    chunked = pd.concat(parts, ignore_index=True)
    pd.testing.assert_frame_equal(whole, chunked)


def test_classification_rules():
    secs = [round(0.1 * i, 1) for i in range(7)]
    raw = raw_frame(
        secs,
        work=["Power harrowing", "not working", "not working", "not working", "not working", "not working", "not working"],
        implement=["Lemken Zirkon", "Lemken Zirkon", None, None, None, None, "Mystery 9000"],
        status=["Driving Off-Road", "Driving Off-Road", "Driving On-Road", "Driving Off-Road",
                "Driving Off-Road", "Driving Off-Road", "Driving Off-Road"],
        speed=[1.0, 1.0, 5.0, 0.0, 2.0, 1.0, 1.0],
        rpm=[1200.0, 1200.0, 1200.0, 900.0, 1200.0, 0.0, 1200.0],
        fuel=[10.0, 10.0, 10.0, 10.0, 10.0, 0.0, 10.0],
    )
    df = clean_chunk(raw, StreamState(), WT)
    assert df["activity_class"].tolist() == ["field_work", "implement_nonproductive", "road_transport", "idle",
                                             "offroad_unassigned", "engine_off", "implement_nonproductive"]
    assert df["operation_code"].tolist()[:4] == ["power_harrowing", "power_harrowing", "transport", "idle"]
    assert pd.isna(df["operation_code"].iloc[4])
    assert df["implement_class"].iloc[6] == "implement_unknown"
    assert df["attribution_label"].tolist() == ["measured", "allocated", "allocated", "allocated", "allocated",
                                                "measured", "allocated"]
    assert "tractor_model" not in df and "implement_model" not in df
    assert (df["tractor_id"] == "tractor_1").all()


def test_nonproductive_takes_last_labelled_op_of_session():
    # Zirkon is used for seed-drill combinations too; the session's last labelled op wins over the default.
    secs = [round(0.1 * i, 1) for i in range(3)]
    raw = raw_frame(secs, work=["not working", "Seed drill combination", "not working"],
                    implement=["Lemken Zirkon"] * 3)
    df = clean_chunk(raw, StreamState(), WT)
    assert df["operation_code"].tolist() == ["power_harrowing", "seed_drill_combination", "seed_drill_combination"]


def test_unknown_worktype_is_flagged_not_dropped():
    df = clean_chunk(raw_frame([0, 0.1], work="Bale wrapping"), StreamState(), WT)
    assert df["operation_code"].iloc[0] == "unmapped:Bale wrapping"


def test_brand_mapping():
    assert tractor_from_model("Fendt 722 Vario Gen6") == ("tractor_4", 163.0)
    with pytest.raises(ValueError):
        tractor_from_model("Other 100")
    assert implement_class("Amazone D9 4000 Super & Lemken Zirkon")[0] == "seed_drill_combination"
    assert implement_class("Lemken Zirkon") == ("power_harrow", "power_harrowing")
    assert implement_class(np.nan) == (None, None)


def test_field_file_area():
    # 100 s working at 2 m/s with a 3 m implement = 600 m2; 10 s turning excluded from area.
    secs = [round(0.1 * i, 1) for i in range(1101)]
    status = ["working"] * 1001 + ["turning"] * 100
    s = field_file_summary(raw_frame(secs, fuel=18.0, implement="Lemken Zirkon", status=status, speed=2.0))
    assert s["area_worked_ha"] == pytest.approx(0.06)
    assert s["hours_working"] == pytest.approx(100 / 3600)
    assert s["litres_total"] == pytest.approx(18.0 * 110 / 3600)


def test_wheel_speed_fallback_when_gnss_speed_missing():
    raw = raw_frame([0, 0.1], speed=2.0).drop(columns=["SpeedOverGround_(m/s)", "RearDraft_(N)"])
    raw["WheelBasedMachineSpeed_(m/s)"] = [1.5, 65.535]
    df = rename_and_null_sentinels(raw)
    assert df["speed_mps"].iloc[0] == 1.5 and np.isnan(df["speed_mps"].iloc[1])
    assert (df["speed_source"] == "wheel").all()
    assert df["rear_draft_n"].isna().all()
    assert (rename_and_null_sentinels(raw_frame([0]))["speed_source"] == "gnss").all()


def test_generic_implement_names():
    assert implement_class("Mulcher") == ("mulcher", "mulching")
    assert implement_class("Rotary tiller") == ("rotary_tiller", "rotary_tilling")
    assert implement_class("Lemken Europal 8 with 5 ploughshares") == ("plough", "ploughing")


def test_non_numeric_text_in_numeric_columns_becomes_null():
    raw = raw_frame([0, 0.1], implement="Rauch Axis")
    raw["Implement_Width_(m)"] = ["unknown", "15"]
    df = rename_and_null_sentinels(raw)
    assert np.isnan(df["implement_width_m"].iloc[0]) and df["implement_width_m"].iloc[1] == 15.0


# --- frozen (carried-forward) data, engine-off rule, streaming -------------------------------------

def frozen_case():
    """60 s normal, 90 s frozen (0 rpm, 35.55 L/h, 3.36 m/s, fixed GPS), 30 s normal, 70 s parked."""
    secs = [round(0.1 * i, 1) for i in range(2500)]
    n1, n2, n3 = 600, 900, 300
    n4 = 2500 - n1 - n2 - n3
    rpm = [1200.0] * n1 + [0.0] * n2 + [1300.0] * n3 + [0.0] * n4
    fuel = [20.0] * n1 + [35.55] * n2 + [22.0] * n3 + [0.0] * n4
    speed = [2.0] * n1 + [3.36] * n2 + [2.0] * n3 + [0.0] * n4
    lat = ([48.0 + 1e-6 * i for i in range(n1)] + [48.5] * n2
           + [48.6 + 1e-6 * i for i in range(n3)] + [48.7] * n4)
    return raw_frame(secs, fuel=fuel, speed=speed, rpm=rpm, lat=lat)


def test_frozen_run_is_excluded_and_parked_tractor_is_engine_off():
    df = clean_chunk(frozen_case(), StreamState(), WT)
    gap = df["activity_class"] == "data_gap"
    assert gap.sum() == 900 and gap.iloc[600:1500].all()
    assert (df.loc[gap, "fuel_l"] == 0).all() and (df.loc[gap, "attribution_label"] == "excluded").all()
    assert df.loc[gap, "operation_code"].isna().all()
    assert (df["activity_class"].iloc[1800:] == "engine_off").all()      # all zeros: genuinely parked
    expected = (20.0 * 59.9 + 22.0 * 30.0) / 3600     # only the two normal segments carry fuel
    assert df["fuel_l"].sum() == pytest.approx(expected, rel=1e-3)


def test_short_identical_run_is_not_frozen():
    secs = [round(0.1 * i, 1) for i in range(300)]    # 30 s identical, below the 60 s threshold
    df = clean_chunk(raw_frame(secs, lat=48.0), StreamState(), WT)
    assert not (df["activity_class"] == "data_gap").any()


def test_zero_rpm_with_fuel_flow_is_not_engine_off():
    secs = [round(0.1 * i, 1) for i in range(5)]
    df = clean_chunk(raw_frame(secs, rpm=0.0, fuel=[5.0, 6.0, 5.5, 6.1, 5.2]), StreamState(), WT)
    assert not (df["activity_class"] == "engine_off").any()
    assert df["fuel_l"].sum() > 0


def test_split_trailing_run():
    raw = frozen_case()
    head, tail = split_trailing_run(raw.iloc[:1000])
    assert len(head) == 600 and len(tail) == 400
    head, tail = split_trailing_run(raw.iloc[600:1000])
    assert len(head) == 0 and len(tail) == 400


@pytest.mark.parametrize("chunk", [97, 450, 1000])
def test_stream_with_frozen_run_across_chunks_equals_whole(chunk):
    raw = frozen_case()
    whole = pd.concat(list(clean_stream([raw], WT)), ignore_index=True)
    chunks = (raw.iloc[i:i + chunk].reset_index(drop=True) for i in range(0, len(raw), chunk))
    streamed = pd.concat(list(clean_stream(chunks, WT)), ignore_index=True)
    pd.testing.assert_frame_equal(whole, streamed)
    assert (streamed["activity_class"] == "data_gap").sum() == 900


def test_generic_names_tractor_4():
    assert implement_class("Cultivator") == ("cultivator", "cultivating_shallow")
    assert implement_class("Disc harrow") == ("disc_harrow", "disc_harrowing")
    assert implement_class("Kerner Komet K420") == ("cultivator", "cultivating_deep")
