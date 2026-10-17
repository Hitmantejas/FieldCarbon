"""Synthetic, labelled records around the real jobs: calendar, operators, clients, fuel depots, maintenance.

Everything here is operational data with no public source. It never touches evidence, coefficients or
costs, and real litres are never changed. A fixed seed makes every run identical.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from backend.fleet.real import AGG, tum_jobs, tumosan_jobs, vineyard_jobs

COMPANY_START = pd.Timestamp("2025-05-01")
COMPANY_END = pd.Timestamp("2026-04-30 23:59:59")
DAY_START_H, DAY_END_H = 7.5, 18.0

# Calendar months (1-12) in which an operation is normally done, with relative weights.
SEASON = {
    "ploughing": {9: 3, 10: 4, 11: 3, 3: 1}, "cultivating_deep": {8: 2, 9: 4, 10: 3},
    "cultivating_shallow": {9: 3, 10: 3, 3: 1, 4: 1}, "disc_harrowing": {9: 3, 10: 3, 3: 1},
    "power_harrowing": {3: 2, 4: 3, 9: 2, 10: 2}, "rotary_tilling": {9: 2, 10: 2, 3: 2, 4: 2},
    "seedbed_combination": {3: 2, 4: 3, 9: 2, 10: 3}, "seed_drill_combination": {9: 3, 10: 4, 3: 2, 4: 3},
    "precision_seeding": {4: 3, 5: 2, 3: 1}, "mulching": {8: 2, 9: 2, 10: 2, 11: 2}, "fertilizing": {3: 3, 4: 3, 5: 3},
    "spraying": {4: 3, 5: 3, 6: 3, 10: 1}, "mowing": {5: 3, 6: 4, 7: 3, 8: 2}, "swathing": {6: 3, 7: 3, 8: 3},
    "transport": {m: 1 for m in range(1, 13)},
}
SITE_OPERATORS = {"S1": 8, "S2": 6, "S3": 2}
SITE_CLIENTS = {"S1": 8, "S2": 5, "S3": 3}
DEPOTS = {"S1": (3000, 1500), "S2": (1500, 750), "S3": (500, 250)}  # capacity, opening stock (litres)
SUPPLIERS = ("Supplier A (demo)", "Supplier B (demo)")
EVENTS = ("Tyre repair", "Hydraulic hose replaced", "Air filter replaced", "Fuel filter replaced", "Battery replaced",
          "Brake adjustment")


def _rng(seed: int, key: str) -> np.random.RandomState:
    return np.random.RandomState((seed + zlib.crc32(key.encode())) % (2 ** 31))


def _year_of(month: int) -> int:
    return 2025 if month >= 5 else 2026


def _pick_day(op: str, rng: np.random.RandomState) -> pd.Timestamp:
    weights = SEASON.get(op, {m: 1 for m in range(1, 13)})
    months = sorted(weights)
    month = int(rng.choice(months, p=np.array([weights[m] for m in months], float) / sum(weights.values())))
    days = [d for d in pd.date_range(pd.Timestamp(_year_of(month), month, 1), periods=31, freq="D")
            if d.month == month and d.weekday() < 6]
    return days[rng.randint(len(days))]


def schedule(jobs: pd.DataFrame, seed: int) -> pd.Series:
    """A start time for every job: in season, Mon-Sat, 07:30-18:00, one job after another on each machine."""
    start = pd.Series(pd.NaT, index=jobs.index, dtype="datetime64[ns]")
    for machine, group in jobs.groupby("machine_id", sort=True):
        rng = _rng(seed, machine)
        targets = sorted((_pick_day(op, rng), i) for i, op in zip(group.index, group.operation_code))
        cursor = None
        for day, i in targets:
            t = day + pd.Timedelta(hours=DAY_START_H)
            if cursor is not None and cursor > t:
                t = cursor
            hours = float(jobs.at[i, "hours"])
            while t.weekday() == 6 or t.hour + t.minute / 60 + hours > DAY_END_H:
                t = t.normalize() + pd.Timedelta(days=1, hours=DAY_START_H)
            start[i] = t
            cursor = t + pd.Timedelta(hours=hours + 0.25)
    return start


def _operators() -> pd.DataFrame:
    rows, n = [], 0
    for site, count in SITE_OPERATORS.items():
        for _ in range(count):
            n += 1
            rows.append({"operator_id": f"OP-{n:02d}", "site_id": site, "role": "tractor operator", "is_synthetic": True})
    return pd.DataFrame(rows)


def _assign_operators(jobs: pd.DataFrame, operators: pd.DataFrame, seed: int) -> pd.Series:
    """One operator per machine per day: the machine's usual operator three days in four."""
    out = pd.Series(index=jobs.index, dtype="object")
    for site, ops in operators.groupby("site_id"):
        ids = list(ops.operator_id)
        machines = sorted(jobs[jobs.site_id == site].machine_id.unique())
        usual = {m: ids[k % len(ids)] for k, m in enumerate(machines)}
        chosen: dict[tuple, str] = {}
        for i, row in jobs[jobs.site_id == site].sort_values("start_ts").iterrows():
            key = (row.machine_id, row.start_ts.date())
            if key not in chosen:
                rng = _rng(seed, f"{key[0]}-{key[1]}")
                chosen[key] = usual[row.machine_id] if rng.rand() < 0.75 else ids[rng.randint(len(ids))]
            out[i] = chosen[key]
    return out


def _fields_and_clients(jobs: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    s1 = pd.read_csv(AGG / "farm_a_fields.csv")
    area = {f"S1-{r.field_id}": r.hull_area_ha for r in s1.itertuples()}
    rows = []
    for site in ("S1", "S2", "S3"):
        j = jobs[(jobs.site_id == site) & jobs.field_id.notna()]
        ids = sorted(j.field_id.unique())
        if site == "S1":
            areas, method = [area.get(f, np.nan) for f in ids], "GPS hull (allocated)"
        else:
            by = j.groupby("field_id").area_ha.max()
            areas, method = [by[f] for f in ids], "largest single-job area (allocated)"
        rows += [{"field_id": f, "site_id": site, "area_ha": a, "area_method": method} for f, a in zip(ids, areas)]
    fields = pd.DataFrame(rows)

    clients, k = [], 0
    for site, count in SITE_CLIENTS.items():
        for _ in range(count):
            k += 1
            clients.append({"client_id": f"C{k:02d}", "name": f"Client farm {k:02d}", "site_id": site, "is_synthetic": True})
    clients = pd.DataFrame(clients)
    assigned = []
    for site, group in fields.groupby("site_id", sort=True):
        ids = list(clients[clients.site_id == site].client_id)
        order = _rng(seed, f"clients-{site}").permutation(len(group))
        assigned += [(f, ids[o % len(ids)]) for f, o in zip(group.field_id, order)]
    fields["client_id"] = fields.field_id.map(dict(assigned))
    return fields, clients


def _other_monthly(jobs: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    """Fuel burned outside jobs, spread over months in proportion to each machine's job litres."""
    rows = []
    months = pd.period_range("2025-05", "2026-04", freq="M")
    for r in other.itertuples():
        mj = jobs[jobs.machine_id == r.machine_id]
        share = mj.groupby(mj.start_ts.dt.to_period("M")).litres.sum().reindex(months, fill_value=0)
        share = share / share.sum() if share.sum() > 0 else pd.Series(1 / len(months), index=months)
        rows += [{"machine_id": r.machine_id, "month": str(m), "activity_class": r.activity_class,
                  "hours": r.hours * w, "litres": r.litres * w} for m, w in share.items() if w > 0]
    return pd.DataFrame(rows)


def _daily_burn(jobs: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    jobs = jobs.assign(day=jobs.start_ts.dt.normalize())
    daily = jobs.groupby(["machine_id", "day"], as_index=False).agg(litres=("litres", "sum"), first=("start_ts", "min"))
    extra = other.groupby(["machine_id", "month"]).litres.sum()
    daily["month"] = daily.day.dt.to_period("M").astype(str)
    days = daily.groupby(["machine_id", "month"]).day.transform("count")
    daily["litres"] += [extra.get((m, mo), 0.0) / n for m, mo, n in zip(daily.machine_id, daily.month, days)]
    return daily


def _prices() -> pd.Series:
    p = pd.read_csv(AGG.parents[0] / "reference" / "ref_fuel_prices.csv", parse_dates=["price_month"])
    return p.set_index(p.price_month.dt.to_period("M")).price_per_litre


def _fuel_flows(daily: pd.DataFrame, operator_of: dict, machines: pd.DataFrame, seed: int):
    """Dispenses from each site's depot, tanker deliveries, month-end dip readings and the planted problems."""
    prices = _prices()
    site_of = dict(zip(machines.machine_id, machines.site_id))
    rng = _rng(seed, "dispenses")
    disp = []
    for r in daily.sort_values(["day", "machine_id"]).itertuples():
        ts = max(r.first - pd.Timedelta(minutes=20), r.day + pd.Timedelta(hours=5.5))
        disp.append({"depot_id": f"{site_of[r.machine_id]}-D1", "machine_id": r.machine_id,
                     "operator_id": operator_of.get((r.machine_id, r.day.date())), "ts": ts,
                     "litres": round(r.litres * rng.uniform(0.99, 1.03), 1)})
    disp = pd.DataFrame(disp)

    truth = []
    # A1: one machine takes about a fifth more fuel than it burns in one month, on six nights.
    machine, month = "S1-T4", pd.Period("2025-10", freq="M")
    base = disp[(disp.machine_id == machine) & (disp.ts.dt.to_period("M") == month)]
    night_days = sorted(pd.Timestamp(d) for d in _rng(seed, "a1").choice(pd.date_range("2025-10-01", "2025-10-31", freq="D"), 6, replace=False))
    extra = 0.20 * base.litres.sum() / 6
    night = pd.DataFrame([{"depot_id": "S1-D1", "machine_id": machine, "operator_id": operator_of.get((machine, d.date())),
                           "ts": d + pd.Timedelta(hours=22, minutes=int(30 + 10 * k)), "litres": round(extra, 1)}
                          for k, d in enumerate(night_days)])
    disp = pd.concat([disp, night], ignore_index=True).sort_values("ts", ignore_index=True)
    disp["dispense_id"] = [f"DSP-{i + 1:05d}" for i in range(len(disp))]
    truth.append({"anomaly_id": "A1", "kind": "over_dispense", "site_id": "S1", "machine_id": machine, "when": str(month),
                  "description": "About 20% more fuel dispensed than burned, on six nights outside shift hours",
                  "expected_signal": "dispensed / burned >= 1.15 for the machine-month; night-time dispenses",
                  "true_cause": "night_fuel_outside_shift"})

    # Depot stock: the tank is refilled when it runs low. A2 is a withdrawal that is never logged.
    dep_rows, deliveries, dips = [], [], []
    leak_day, leak_litres = pd.Timestamp("2026-01-17 23:10"), 900.0
    for site, (capacity, opening) in DEPOTS.items():
        depot = f"{site}-D1"
        dep_rows.append({"depot_id": depot, "site_id": site, "capacity_l": capacity, "opening_stock_l": opening,
                         "opening_date": COMPANY_START.date()})
        stock, n_del = float(opening), 0
        events = [(t, "dispense", l) for t, l in zip(disp[disp.depot_id == depot].ts, disp[disp.depot_id == depot].litres)]
        if site == "S1":
            events.append((leak_day, "leak", leak_litres))
        month_ends = {m.end_time.normalize(): m for m in pd.period_range("2025-05", "2026-04", freq="M")}
        events += [(d + pd.Timedelta(hours=23, minutes=59), "dip", 0.0) for d in month_ends]
        for t, kind, litres in sorted(events, key=lambda e: (e[0], e[1])):
            if kind == "dip":
                dips.append({"depot_id": depot, "date": t.normalize().date(),
                             "dip_litres": round(max(stock, 0) * (1 + _rng(seed, f"dip{depot}{t}").normal(0, 0.003)), 0)})
                continue
            if stock - litres < 0.2 * capacity and kind == "dispense":
                drop = max(300.0, round((0.8 * capacity - stock) / 100) * 100)
                when = (t.normalize() - pd.Timedelta(days=1 if t.weekday() else 2)) + pd.Timedelta(hours=6, minutes=int(rng.randint(60)))
                when = max(when, COMPANY_START)
                price = prices[when.to_period("M")] * float(np.clip(_rng(seed, f"p{depot}{n_del}").normal(1, 0.012), 0.975, 1.025))
                n_del += 1
                deliveries.append({"delivery_id": f"{site}-DL-{n_del:03d}", "depot_id": depot, "ts": when,
                                   "supplier": SUPPLIERS[n_del % 2], "doc_no": f"DN-{site}-{n_del:04d}",
                                   "litres": drop, "unit_price_gbp": round(float(price), 4)})
                stock += drop
            stock -= litres
    deliveries = pd.DataFrame(deliveries).sort_values("ts", ignore_index=True)
    truth.append({"anomaly_id": "A2", "kind": "unlogged_withdrawal", "site_id": "S1", "machine_id": "", "when": str(leak_day.date()),
                  "description": f"{leak_litres:.0f} L left the S1 depot without being logged",
                  "expected_signal": "book stock (deliveries minus dispenses) exceeds the dip reading by about 900 L",
                  "true_cause": "unlogged_withdrawal"})

    # A3: the same delivery note entered twice at S2.
    s2 = deliveries[deliveries.depot_id == "S2-D1"]
    dup = s2.iloc[len(s2) // 2].copy()
    dup["delivery_id"] = dup.delivery_id + "-dup"
    deliveries = pd.concat([deliveries, dup.to_frame().T], ignore_index=True).sort_values("ts", ignore_index=True)
    truth.append({"anomaly_id": "A3", "kind": "duplicate_delivery_note", "site_id": "S2", "machine_id": "",
                  "when": str(dup.ts.date()), "description": f"Delivery note entered twice: {dup.doc_no}",
                  "expected_signal": "two delivery rows with the same supplier, document number, date and litres",
                  "true_cause": "same_note_entered_twice"})
    return disp, deliveries, pd.DataFrame(dep_rows), pd.DataFrame(dips), pd.DataFrame(truth)


def _maintenance(jobs: pd.DataFrame, seed: int) -> pd.DataFrame:
    rows, n = [], 0
    for machine, g in jobs.sort_values("start_ts").groupby("machine_id"):
        cum = g.hours.cumsum().to_numpy()
        starts = g.start_ts.to_numpy()
        for mark in range(250, int(cum[-1]) + 1, 250):
            i = int(np.searchsorted(cum, mark))
            n += 1
            rows.append({"machine_id": machine, "date": pd.Timestamp(starts[i]).date(), "event_type": "Service (250 h)",
                         "job_hours_at_event": round(float(cum[i]), 1), "note": "Scheduled service at 250 hours"})
        rng = _rng(seed, f"maint-{machine}")
        for i in sorted(rng.choice(len(g), size=min(3, len(g)), replace=False)):
            rows.append({"machine_id": machine, "date": pd.Timestamp(starts[i]).date(), "event_type": EVENTS[rng.randint(len(EVENTS))],
                         "job_hours_at_event": round(float(cum[i]), 1), "note": "Routine repair logged by the workshop"})
    out = pd.DataFrame(rows).sort_values(["date", "machine_id"], ignore_index=True)
    out.insert(0, "event_id", [f"MNT-{i + 1:04d}" for i in range(len(out))])
    return out


def _static_tables() -> dict[str, pd.DataFrame]:
    sites = pd.DataFrame([
        {"site_id": "S1", "name": "Arable site (Bavaria)", "country": "DE", "data_kind": "raw telemetry", "source_id": "tum_alc_data"},
        {"site_id": "S2", "name": "Vineyard site (Tuscany)", "country": "IT", "data_kind": "per-operation summary", "source_id": "vineyard_ops"},
        {"site_id": "S3", "name": "Tillage site (Konya Plain)", "country": "TR", "data_kind": "raw telemetry, tillage only", "source_id": "tumosan_tillage"},
    ])
    machines = pd.DataFrame(
        [{"machine_id": f"S1-T{i}", "site_id": "S1", "display_name": f"Tractor {i}, {kw} kW", "rated_kw": kw, "fuel_type": "gas_oil"}
         for i, kw in enumerate((77, 104, 140, 163, 174), 1)]
        + [{"machine_id": f"S2-T{i}", "site_id": "S2", "display_name": f"Vineyard tractor {i}, 75 kW", "rated_kw": 75, "fuel_type": "gas_oil"} for i in range(1, 7)]
        + [{"machine_id": "S3-T1", "site_id": "S3", "display_name": "Tractor, 77 kW (105 hp)", "rated_kw": 77, "fuel_type": "gas_oil"}])
    ref = pd.read_csv(AGG.parents[0] / "reference" / "ref_operations.csv")
    arable = ref[["operation_code", "display_name", "category"]].assign(site_kind="arable")
    names = {"vy_ridging": "Ridging", "vy_light_ridging": "Light ridging", "vy_unridging": "Unridging",
             "vy_sward_soil_tillage": "Sward and soil tillage", "vy_soil_tillage": "Soil tillage", "vy_mulching": "Mulching (vineyard)",
             "vy_shoot_thinning": "Shoot thinning", "vy_shoot_removing": "Shoot removing", "vy_leaf_removing": "Leaf removing",
             "vy_prepruning": "Prepruning", "vy_crop_protection_single_row": "Crop protection, single row",
             "vy_crop_protection_multi_row": "Crop protection, multi row", "vy_harvest": "Harvest", "vy_fertilising": "Fertilising (vineyard)"}
    cats = {"vy_ridging": "soil_work", "vy_light_ridging": "soil_work", "vy_unridging": "soil_work", "vy_sward_soil_tillage": "soil_work",
            "vy_soil_tillage": "soil_work", "vy_mulching": "vegetation", "vy_shoot_thinning": "canopy", "vy_shoot_removing": "canopy",
            "vy_leaf_removing": "canopy", "vy_prepruning": "canopy", "vy_crop_protection_single_row": "crop_protection",
            "vy_crop_protection_multi_row": "crop_protection", "vy_harvest": "harvest", "vy_fertilising": "crop_care"}
    vine = pd.DataFrame([{"operation_code": c, "display_name": n, "category": cats[c], "site_kind": "vineyard"} for c, n in names.items()])
    return {"sites": sites, "machines": machines, "operations": pd.concat([arable, vine], ignore_index=True)}


def build_fleet(seed: int = 2026) -> dict[str, pd.DataFrame]:
    s1, other = tum_jobs()
    s2, s3 = vineyard_jobs(), tumosan_jobs()
    jobs = pd.concat([s1, s2, s3], ignore_index=True)

    jobs["start_ts"] = pd.NaT
    jobs["date_basis"] = "assigned"
    arable = jobs.site_id != "S2"
    jobs.loc[arable, "start_ts"] = schedule(jobs[arable], seed)
    shifted = jobs.site_id == "S2"
    jobs.loc[shifted, "start_ts"] = jobs.loc[shifted, "date_real"] + pd.DateOffset(years=4)
    jobs.loc[shifted, "date_basis"] = "real+4y"
    jobs["start_ts"] = pd.to_datetime(jobs.start_ts)

    operators = _operators()
    jobs["operator_id"] = _assign_operators(jobs, operators, seed)
    fields, clients = _fields_and_clients(jobs, seed)
    jobs["client_id"] = jobs.field_id.map(dict(zip(fields.field_id, fields.client_id)))
    jobs["synthetic_columns"] = np.where(arable, "operator_id,client_id,start_ts", "operator_id,client_id")

    other_monthly = _other_monthly(jobs, other)
    daily = _daily_burn(jobs, other_monthly)
    operator_of = {(r.machine_id, r.start_ts.date()): r.operator_id for r in jobs.itertuples()}
    tables = _static_tables()
    disp, deliveries, depots, dips, truth = _fuel_flows(daily, operator_of, tables["machines"], seed)

    jobs = jobs.sort_values(["start_ts", "machine_id"], ignore_index=True)
    cols = ["job_id", "site_id", "machine_id", "operator_id", "client_id", "field_id", "operation_code", "start_ts", "hours",
            "litres", "area_ha", "mean_load_pct", "idle_ratio", "sessions", "litres_label", "area_label", "source_id",
            "date_basis", "date_real", "synthetic_columns"]
    return {**tables, "clients": clients, "fields": fields, "operators": operators, "jobs": jobs[cols],
            "other_activity": other_monthly, "depots": depots, "fuel_deliveries": deliveries, "fuel_dispenses": disp,
            "depot_stock_readings": dips, "maintenance_events": _maintenance(jobs, seed), "ground_truth_anomalies": truth}
