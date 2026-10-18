"""Detection stress test: how big must a problem be before the detectors see it, and what do they say on unmodified data?

The planted-problem eval (fleet_detection) has three fixed cases, all large. This one injects faults of graded size at
random places, many times, into copies of the fleet tables, and reports detection rate per size with a 95% interval.
Where the detector misses by design (below its threshold, a mistyped note) the table says so; thresholds are not tuned
to this eval. Job-outlier faults go into the real job fuel records (TUM, vineyard, Tumosan), so the noise around them is real.

Run: python -m evals.detection_stress          (a few minutes)
"""
from __future__ import annotations

import json
from collections import Counter
from contextlib import contextmanager
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from backend.fleet import data
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.reconcile_fuel import reconcile_fuel

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results" / "detection_stress.json"
SEED = 2026
TRIALS = 40
FLOOR_LITRES = 50  # reconcile_fuel ignores machine-months with less extra than this, however large the share
OVER_DISPENSE_PCT = (5, 10, 15, 20, 30, 50)
WITHDRAWAL_LITRES = (50, 100, 150, 250, 500, 900)
JOB_EXTRA_PCT = (20, 30, 50, 75, 100, 200)


@contextmanager
def tables(**frames: pd.DataFrame):
    """Run with some fleet tables swapped for modified copies; the ledger is rebuilt from them."""
    originals = {name: getattr(data, name) for name in (*frames, "ledger")}
    try:
        for name, frame in frames.items():
            setattr(data, name, lambda frame=frame: frame)
        ledger = originals["ledger"].__wrapped__()
        data.ledger = lambda: ledger
        yield
    finally:
        for name, original in originals.items():
            setattr(data, name, original)


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p, denom = hits / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def _key(finding: dict) -> tuple:
    return tuple(finding.get(k) for k in ("kind", "machine_id", "depot_id", "month", "job_id", "doc_no"))


class Tally:
    """Hits, findings the fault did not cause, and baseline findings the fault hid (masking), over repeated trials."""

    def __init__(self, baseline: list[dict]):
        self.baseline = {_key(f) for f in baseline}
        self.n = self.hits = self.new = self.lost = 0
        self.eligible = self.eligible_hits = 0
        self.litres: list[float] = []

    def add(self, found: list[dict], mine: bool, litres: float, eligible: bool = True) -> None:
        keys = {_key(f) for f in found}
        self.n += 1
        self.hits += mine
        self.eligible += eligible
        self.eligible_hits += mine and eligible
        self.litres.append(litres)
        self.new += len(keys - self.baseline) - mine
        self.lost += len(self.baseline - keys)

    def row(self, size) -> dict:
        low, high = wilson(self.hits, self.n)
        return {"size": size, "trials": self.n, "detected": self.hits, "rate": round(self.hits / self.n, 3),
                "interval_95": [low, high], "median_litres": round(float(np.median(self.litres)), 0),
                "new_unrelated_findings_per_trial": round(self.new / self.n, 2),
                "baseline_findings_hidden_per_trial": round(self.lost / self.n, 2)}


def _quiet_machine_months(findings: list[dict], min_burned: float = 100.0) -> list[tuple[str, str]]:
    """Machine-months with real burn that the detector does not already flag, so a hit or miss is about the injected fault."""
    flagged = {(f["machine_id"], f["month"]) for f in findings}
    burned = data.ledger().groupby(["machine_id", "month"]).litres.sum()
    return [k for k, v in burned.items() if v >= min_burned and k not in flagged]


def over_dispense(rng: np.random.Generator) -> list[dict]:
    """Extra fuel handed to one machine in one month; the depot dip falls by the same litres, as it would in reality."""
    baseline = reconcile_fuel()["findings"]
    pool = _quiet_machine_months(baseline)
    disp, dips = data.dispenses(), data.stock_readings()
    month = disp.ts.dt.to_period("M").astype(str)
    rows = []
    for pct in OVER_DISPENSE_PCT:
        tally = Tally(baseline)
        for _ in range(TRIALS):
            machine, mo = pool[rng.integers(len(pool))]
            hit = (disp.machine_id == machine) & (month == mo)
            added = float(disp.litres[hit].sum() * pct / 100)
            changed = disp.assign(litres=np.where(hit, disp.litres * (1 + pct / 100), disp.litres))
            depot = disp.depot_id[hit].iloc[0]
            lowered = dips.assign(dip_litres=np.where((dips.depot_id == depot) & (dips.date >= disp.ts[hit].min().normalize()),
                                                      dips.dip_litres - added, dips.dip_litres))
            with tables(dispenses=changed, stock_readings=lowered):
                found = reconcile_fuel()["findings"]
            mine = any(f["kind"] == "machine_over_dispense" and f["machine_id"] == machine and f["month"] == mo for f in found)
            tally.add(found, mine, added, eligible=added >= FLOOR_LITRES and pct >= 10)
        rows.append({**tally.row(pct), "eligible_trials": tally.eligible, "eligible_detected": tally.eligible_hits})
    return rows


def unlogged_withdrawal(rng: np.random.Generator) -> list[dict]:
    """Fuel leaves a depot without a record: every later dip reading is lower by that amount."""
    baseline = reconcile_fuel()["findings"]
    seen = {(f["depot_id"], f["month"]) for f in baseline}
    dips = data.stock_readings()
    pool = dips[[(d, str(t.to_period("M"))) not in seen for d, t in zip(dips.depot_id, dips.date)]]
    rows = []
    for litres in WITHDRAWAL_LITRES:
        tally = Tally(baseline)
        for _ in range(TRIALS):
            reading = pool.iloc[rng.integers(len(pool))]
            lowered = dips.assign(dip_litres=np.where((dips.depot_id == reading.depot_id) & (dips.date >= reading.date),
                                                      dips.dip_litres - litres, dips.dip_litres))
            with tables(stock_readings=lowered):
                found = reconcile_fuel()["findings"]
            mine = any(f["kind"] == "stock_gap" and f["depot_id"] == reading.depot_id
                       and f["month"] == str(reading.date.to_period("M")) for f in found)
            tally.add(found, mine, litres)
        rows.append(tally.row(litres))
    return rows


def duplicate_note(rng: np.random.Generator) -> list[dict]:
    """The same delivery note entered twice: exactly, and with the litres mistyped by 1%."""
    baseline = reconcile_fuel()["findings"]
    deliveries = data.deliveries()
    pool = deliveries[~deliveries.doc_no.isin({f["doc_no"] for f in baseline if f["kind"] == "duplicate_delivery_note"})]
    rows = []
    for name, typo in (("exact copy", 1.0), ("litres mistyped by 1%", 1.01)):
        tally, elsewhere = Tally(baseline), 0
        for _ in range(TRIALS):
            original = pool.iloc[rng.integers(len(pool))]
            twin = original.copy()
            twin["litres"] = round(original.litres * typo, 1)
            doubled = pd.concat([deliveries, twin.to_frame().T], ignore_index=True).astype(deliveries.dtypes)
            with tables(deliveries=doubled):
                found = reconcile_fuel()["findings"]
            mine = any(f["kind"] == "duplicate_delivery_note" and f["doc_no"] == original.doc_no for f in found)
            tally.add(found, mine, float(twin.litres))
            elsewhere += any(f["depot_id"] == original.depot_id and f["kind"] != "duplicate_delivery_note"
                             and f["month"] == str(original.ts.to_period("M")) and _key(f) not in tally.baseline for f in found)
        rows.append({**tally.row(name), "caught_by_another_finding": elsewhere})
    return rows


def job_extra_fuel(rng: np.random.Generator) -> list[dict]:
    """One real job recorded with extra fuel; the detector compares it with other jobs of the same kind at the same site."""
    jobs = data.jobs()
    baseline = [f for f in detect_anomalies()["findings"] if f["kind"] == "job_outlier"]
    flagged = {f["job_id"] for f in baseline}
    comparable = jobs.groupby(["site_id", "operation_code"]).job_id.transform("size") >= 8
    pool = jobs[(jobs.hours >= 0.3) & (jobs.litres > 0) & comparable & ~jobs.job_id.isin(flagged)]
    rows = []
    for pct in JOB_EXTRA_PCT:
        tally = Tally(baseline)
        for _ in range(TRIALS):
            job = pool.iloc[rng.integers(len(pool))]
            changed = jobs.assign(litres=np.where(jobs.job_id == job.job_id, jobs.litres * (1 + pct / 100), jobs.litres))
            with tables(jobs=changed):
                found = [f for f in detect_anomalies()["findings"] if f["kind"] == "job_outlier"]
            mine = any(f["job_id"] == job.job_id and f["direction"] == "more" for f in found)
            tally.add(found, mine, job.litres * pct / 100)
        rows.append(tally.row(pct))
    return rows


def unmodified_data() -> dict:
    """What the detectors flag on the tables as they are. Without ground truth these are leads to check, not errors."""
    jobs = data.jobs()
    outliers = [f for f in detect_anomalies()["findings"] if f["kind"] == "job_outlier"]
    return {"jobs": len(jobs), "job_outliers_flagged": len(outliers),
            "per_100_jobs": round(100 * len(outliers) / len(jobs), 2),
            "by_site": dict(Counter(f["site_id"] for f in outliers)),
            "direction": dict(Counter(f["direction"] for f in outliers)),
            "note": "The three reconcile findings in these tables are the planted problems A1 to A3. Job outliers have no "
                    "ground truth: they are leads, and some will be ordinary variation."}


def score(trials: int | None = None) -> dict:
    global TRIALS
    TRIALS = trials or TRIALS
    rng = np.random.default_rng(SEED)
    return {
        "seed": SEED, "trials_per_size": TRIALS,
        "unmodified_data": unmodified_data(),
        "over_dispense_pct": over_dispense(rng),
        "unlogged_withdrawal_litres": unlogged_withdrawal(rng),
        "duplicate_note": duplicate_note(rng),
        "job_extra_fuel_pct": job_extra_fuel(rng),
        "reading_it": "size is the injected fault; rate is the share of trials where the detector named that machine, depot or "
                      "job. new_unrelated is findings that were not in the unmodified run; hidden is findings from the "
                      "unmodified run that the fault made disappear (one big job moves the median the others are judged "
                      "against). A rate near 0 below a threshold is the detector working as designed, not a miss to hide.",
    }


if __name__ == "__main__":
    result = score()
    RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for key in ("over_dispense_pct", "unlogged_withdrawal_litres", "duplicate_note", "job_extra_fuel_pct"):
        print(f"\n{key}")
        for r in result[key]:
            print(f"  {str(r['size']):>22}  {r['detected']:>3}/{r['trials']:<3} {100 * r['rate']:5.1f}%  CI {r['interval_95']}  "
                  f"new {r['new_unrelated_findings_per_trial']}  hidden {r['baseline_findings_hidden_per_trial']}"
                  + (f"  eligible {r['eligible_detected']}/{r['eligible_trials']}" if "eligible_trials" in r else ""))
    print("\n", json.dumps(result["unmodified_data"], indent=2))
