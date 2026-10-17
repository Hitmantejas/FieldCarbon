"""Anomaly diagnosis (F5): for one finding, a fixed menu of possible causes, each tested against the data by code.

Gemini suggests; code tests; a person decides. A test says only whether the data supports a cause, does not support
it, or cannot test it with our data; it never names one cause as the answer. Statuses and their order are decided
here. Gemini (backend/agent/diagnosis_text.py) may only explain them and add up to two untested ideas.

The thresholds below were fixed from the plan before looking at the planted problems, each with its reason, and are
not tuned to make the answer come out right. If two causes are supported, both are shown.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass

import pandas as pd

from backend.emissions.text import bullets, month_name
from backend.fleet import data
from backend.tools.check_delivery_notes import SOURCE as NOTES_SOURCE
from backend.tools.check_delivery_notes import _key as note_key
from backend.tools.check_delivery_notes import _readings
from backend.tools.contracts import Figure
from backend.tools.detect_anomalies import detect_anomalies
from backend.tools.reconcile_fuel import SYNTHETIC, _night_dispenses, reconcile_fuel

DISCLAIMER = "Gemini suggests; code tests; a person decides."
STATUS_TEXT = {"supported": "Supported by the data", "not_supported": "Not supported by the data",
               "cannot_test": "Cannot be tested with our data"}
RANK = {"supported": 0, "cannot_test": 1, "not_supported": 2}

# Thresholds (fixed in advance; see the module note).
MIN_NIGHT_DISPENSES = 3      # one or two late dispenses happen on any farm (an early start); three is a pattern
MIN_NIGHT_SHARE = 0.5        # night fuel must cover at least half the excess to be a main cause
MATCH_SHARE = 0.10           # two litre figures "match" within 10%: meter and dip readings are about that rough
MIN_FROZEN_HOURS = 1.0       # the same one-hour floor detect_anomalies uses before it reports a frozen recorder
NIGHT_FROM, NIGHT_TO = 22, 5  # the same night window reconcile_fuel uses
LOAD_SHARE = 0.5             # engine load must move the same way as fuel per hour, by at least half as much (in %)
IDLE_POINTS = 10.0           # idling share at least 10 points above the usual for the job: a clear, visible difference
MAINTENANCE_DAYS = 30        # a workshop visit in the 30 days before a job can still change how the machine runs
NON_WORK_PART = 0.25         # a non-work use must carry at least a quarter of the excess to count as a main part
ONE_PERIOD_SHARE = 0.8       # a one-off fault puts at least 80% of the frozen hours in one month
RECURRING_MONTHS = 3         # three separate months with a freeze is a pattern, not chance
MIN_JOB_HOURS = 0.3          # the same job filter detect_anomalies uses


@dataclass
class Context:
    """The data the tests read, gathered once per diagnosis. Tests build a small one by hand."""
    dispenses: pd.DataFrame       # depot_id, machine_id, ts, litres, month
    burned: dict                  # (machine_id, month) -> litres burned (from the machines' own fuel data)
    night: pd.DataFrame           # night dispenses with no job within 2 hours: machine_id, ts, litres, month
    frozen: pd.DataFrame          # frozen-recorder hours: machine_id, month, hours
    depot_rows: list[dict]        # reconcile_fuel's depot rows: depot_id, month_end, gap_l
    deliveries: pd.DataFrame      # depot_id, ts, supplier, doc_no, litres
    note_counts: dict | None      # paper notes per note_key(supplier, doc_no); None when no note was read
    site_sources: dict            # site_id -> source id of that site's machine data
    stock_tolerance_l: float
    jobs: pd.DataFrame | None = None         # data.jobs(): job_outlier tests
    ledger: pd.DataFrame | None = None       # data.ledger(): high_non_work_share tests
    maintenance: pd.DataFrame | None = None  # data.maintenance(): machine_id, date, event_type

    @classmethod
    def from_data(cls, recon: dict) -> "Context":
        month = lambda d: d.assign(month=d.ts.dt.to_period("M").astype(str))  # noqa: E731
        other = data.other_activity()
        readings, _ = _readings()
        counts = Counter(note_key(x.get("supplier"), x.get("doc_number")) for x in readings.values()) if readings else None
        return cls(dispenses=month(data.dispenses()),
                   burned=data.ledger().groupby(["machine_id", "month"]).litres.sum().to_dict(),
                   night=month(_night_dispenses(NIGHT_FROM, NIGHT_TO)),
                   frozen=other[other.activity_class == "data_gap"][["machine_id", "month", "hours"]],
                   depot_rows=recon["depots"]["rows"], deliveries=data.deliveries(), note_counts=counts,
                   site_sources=data.sites().source_id.to_dict(), stock_tolerance_l=recon["settings"]["stock_tolerance_l"],
                   jobs=data.jobs(), ledger=data.ledger(), maintenance=data.maintenance())


COUNT_UNITS = {"notes", "months", "days"}


def _fig(value: float, unit: str, how: str, *sources: str, label: str = "measured") -> dict:
    fig = asdict(Figure(int(value) if unit in COUNT_UNITS else round(float(value), 2), unit, label, how,
                        source_ids=tuple(dict.fromkeys(s for s in sources if s))))
    return {**fig, "source_ids": list(fig["source_ids"])}


def _result(status: str, evidence: dict | None = None, explains_pct: float | None = None, would_settle: str | None = None,
            measures: str | None = None) -> dict:
    """`measures` says in a few words, with no numbers, what the evidence figure counts; it reads on from the number and
    unit ("406 L dispensed to this machine at night"). Gemini reads it, never `how`."""
    pct = None if explains_pct is None else round(min(100.0, max(0.0, float(explains_pct))), 1)
    return {"status": status, "evidence": evidence, "explains_pct": pct, "would_settle": would_settle,
            "evidence_measures": measures if evidence is not None else None}


def _excess(f: dict) -> float:
    return float(f["litres"]["value"])


# --- machine_over_dispense (A1) ---------------------------------------------------------------------------------------

def night_fuel_outside_shift(f: dict, ctx: Context) -> dict:
    n = ctx.night[(ctx.night.machine_id == f["machine_id"]) & (ctx.night.month == f["month"])]
    litres, excess = float(n.litres.sum()), _excess(f)
    ev = _fig(litres, "L", bullets(
        f"**{len(n)} dispenses** to this machine in {month_name(f['month'])} were between 22:00 and 05:00 with no job within 2 hours.",
        f"Together they come to **{litres:,.0f} litres**, against an excess of **{excess:,.0f} litres**.",
        f"The test needs at least {MIN_NIGHT_DISPENSES} such dispenses covering at least half the excess."), SYNTHETIC)
    ok = len(n) >= MIN_NIGHT_DISPENSES and litres >= MIN_NIGHT_SHARE * excess
    return _result("supported" if ok else "not_supported", ev, 100 * litres / excess if litres and excess else None,
                   "The depot's camera or key-fob log for those nights",
                   "dispensed to this machine at night, with no job nearby")


def logging_or_meter_error(f: dict, ctx: Context) -> dict:
    settle = "A meter calibration check and the paper dispense sheets for the month"
    d = ctx.dispenses[ctx.dispenses.month == f["month"]]
    mine = d[d.machine_id == f["machine_id"]]
    excess = _excess(f)
    repeated = mine[mine.duplicated(["machine_id", "ts", "litres"], keep="first")]
    if len(repeated):
        litres = float(repeated.litres.sum())
        return _result("supported", _fig(litres, "L", bullets(
            f"**{len(repeated)} dispense rows** repeat an earlier row exactly (same machine, time and litres).",
            f"The repeats add **{litres:,.0f} litres** that were probably logged twice."), SYNTHETIC), 100 * litres / excess, settle,
            "in dispense rows that repeat an earlier row exactly")
    peers = d[d.depot_id.isin(set(mine.depot_id)) & (d.machine_id != f["machine_id"])]
    if peers.empty:
        return _result("cannot_test", None, None, settle)
    given = peers.groupby("machine_id").litres.sum()
    net = float(sum(v - ctx.burned.get((m, f["month"]), 0.0) for m, v in given.items()))
    source = ctx.site_sources.get(f["site_id"])
    ev = _fig(net, "L", bullets(
        f"The other **{len(given)} machines** using the same depot in {month_name(f['month'])} were given **{net:,.0f} litres** "
        "more than they burned (a negative figure means less).",
        "If fuel were booked to the wrong machine, they would be short by about this machine's excess (within 10%)."),
        SYNTHETIC, source)
    ok = net < 0 and abs(-net - excess) <= MATCH_SHARE * excess
    return _result("supported" if ok else "not_supported", ev, 100 * -net / excess if ok else None, settle,
                   "given to the other machines on the same depot beyond what they burned; wrong booking would leave them short")


def recorder_understates_burn(f: dict, ctx: Context) -> dict:
    fr = ctx.frozen[(ctx.frozen.machine_id == f["machine_id"]) & (ctx.frozen.month == f["month"])]
    hours = float(fr.hours.sum())
    ev = _fig(hours, "h", bullets(
        f"The machine's recorder repeated the same readings for **{hours:,.1f} hours** in {month_name(f['month'])}.",
        "Fuel burned in those hours is not counted, so the machine may have burned more than its data shows.",
        "Hours cannot be turned into litres here, so this gives no share of the excess."), ctx.site_sources.get(f["site_id"]))
    return _result("supported" if hours >= MIN_FROZEN_HOURS else "not_supported", ev, None,
                   "A check of the recorder and its connection on this machine",
                   "when the machine's recorder repeated the same readings, so fuel burned then was not counted")


def fuel_used_elsewhere(f: dict, ctx: Context) -> dict:
    return _result("cannot_test", None, None, "A log of fuel drawn into cans, other vehicles or by contractors")


# --- stock_gap (A2) ---------------------------------------------------------------------------------------------------

def _stock(f: dict, ctx: Context) -> tuple[list[dict], int, float, float]:
    rows = sorted((r for r in ctx.depot_rows if r["depot_id"] == f["depot_id"]), key=lambda r: r["month_end"])
    i = next(k for k, r in enumerate(rows) if r["month_end"][:7] == f["month"])
    prev_gap = rows[i - 1]["gap_l"] if i else 0.0
    return rows, i, prev_gap, rows[i]["gap_l"] - prev_gap


def unlogged_withdrawal(f: dict, ctx: Context) -> dict:
    settle = "A record of who has the depot key, and when the tank was opened"
    rows, i, prev_gap, step = _stock(f, ctx)
    later = [r["gap_l"] for r in rows[i + 1:]]
    if not later:
        return _result("cannot_test", None, None, settle)
    ok = all(abs(g - rows[i]["gap_l"]) <= ctx.stock_tolerance_l for g in later)
    ev = _fig(step, "L", bullets(
        f"The gap between the books and the measured stock grew by **{step:,.0f} litres** at the {rows[i]['month_end']} reading.",
        f"It {'stayed' if ok else 'did not stay'} near the new level in all **{len(later)} later readings** "
        f"(within {ctx.stock_tolerance_l:,.0f} litres).",
        "Fuel that left the tank without a dispense record would leave a gap like this."), SYNTHETIC)
    return _result("supported" if ok else "not_supported", ev, 100 * (min(later) - prev_gap) / step if ok and step else None, settle,
                   "by which the gap between book and measured stock grew at this reading, and then stayed")


def dip_reading_error(f: dict, ctx: Context) -> dict:
    settle = "A second dip reading taken by another person"
    rows, i, prev_gap, _ = _stock(f, ctx)
    if i + 1 >= len(rows):
        return _result("cannot_test", None, None, settle)
    nxt = rows[i + 1]
    ok = abs(nxt["gap_l"] - prev_gap) <= ctx.stock_tolerance_l
    ev = _fig(nxt["gap_l"], "L", bullets(
        f"At the next reading ({nxt['month_end']}) the gap was **{nxt['gap_l']:,.0f} litres**.",
        f"A misread dip would go back to the earlier gap of {prev_gap:,.0f} litres (within {ctx.stock_tolerance_l:,.0f} litres); "
        f"this one {'did' if ok else 'did not'}."), SYNTHETIC)
    return _result("supported" if ok else "not_supported", ev, None, settle,
                   "of gap at the next reading; a misread dip would have gone back to the earlier gap")


def delivery_not_received_or_duplicated(f: dict, ctx: Context) -> dict:
    settle = "The supplier's statement of deliveries to this depot"
    rows, i, _, step = _stock(f, ctx)
    start = pd.Timestamp(rows[i - 1]["month_end"]) + pd.Timedelta(days=1) if i else pd.Timestamp.min
    end = pd.Timestamp(rows[i]["month_end"]) + pd.Timedelta(days=1)
    dl = ctx.deliveries[ctx.deliveries.depot_id == f["depot_id"]]
    dup = dl.duplicated(["depot_id", "supplier", "doc_no", "litres"], keep="first")
    no_note = pd.Series([ctx.note_counts.get(note_key(s, d), 0) == 0 for s, d in zip(dl.supplier, dl.doc_no)], index=dl.index,
                        dtype=bool) if ctx.note_counts is not None else pd.Series(False, index=dl.index)
    cand = dl[(dup | no_note) & (dl.ts >= start) & (dl.ts < end)]
    if cand.empty:
        if ctx.note_counts is None:
            return _result("cannot_test", None, None, settle)
        litres = 0.0
    else:
        litres = float(cand.litres.iloc[(cand.litres - step).abs().argmin()])
    ok = litres > 0 and abs(litres - step) <= MATCH_SHARE * step
    ev = _fig(litres, "L", bullets(
        f"Logged deliveries to this depot before the {rows[i]['month_end']} reading that are entered twice or have no paper note: "
        f"**{len(cand)}**.",
        f"The closest comes to **{litres:,.0f} litres**, against a step of **{step:,.0f} litres** (a match needs 10%)."),
        SYNTHETIC, NOTES_SOURCE if ctx.note_counts is not None else None)
    return _result("supported" if ok else "not_supported", ev, 100 * litres / step if ok else None, settle,
                   "in the closest logged delivery that is entered twice or has no paper note")


def leak_or_theft(f: dict, ctx: Context) -> dict:
    return _result("cannot_test", None, None, "A dip reading the day after, plus a site check of the tank, pipework and lock")


# --- duplicate_delivery_note (A3) -------------------------------------------------------------------------------------

def _note_rows(f: dict, ctx: Context) -> pd.DataFrame:
    dl = ctx.deliveries
    return dl[(dl.depot_id == f["depot_id"]) & (dl.doc_no == f["doc_no"])]


def same_note_entered_twice(f: dict, ctx: Context) -> dict:
    settle = "The depot's delivery log page for that day"
    rows = _note_rows(f, ctx)
    groups = rows.groupby(["supplier", "litres"]).size() if len(rows) else pd.Series(dtype=int)
    if groups.empty or groups.max() < 2:
        return _result("not_supported", _fig(0, "L", "No two log rows share this depot, supplier, note number and litres.", SYNTHETIC),
                       None, settle, "in log rows that repeat this note")
    (_, litres), n = groups.idxmax(), int(groups.max())
    extra = float(litres) * (n - 1)
    ev = _fig(extra, "L", bullets(
        f"**{n} log rows** share this depot, supplier, note number ({f['doc_no']}) and litres.",
        f"Counted once, the repeat adds **{extra:,.0f} litres** that arrived only once."), SYNTHETIC)
    return _result("supported", ev, 100 * extra / _excess(f), settle, "added by log rows that repeat this note")


def two_real_deliveries(f: dict, ctx: Context) -> dict:
    settle = "A photo of every paper delivery note for that day"
    rows = _note_rows(f, ctx)
    supplier = rows.supplier.iloc[0] if len(rows) else None
    count = 0 if ctx.note_counts is None else ctx.note_counts.get(note_key(supplier, f["doc_no"]), 0)
    if not count:
        return _result("cannot_test", None, None, settle)
    ev = _fig(count, "notes", bullets(
        f"We have **{count} paper note{'s' if count != 1 else ''}** with number {f['doc_no']} from this supplier.",
        f"The log has **{len(rows)} rows** for it. Two real deliveries would need two paper notes."), NOTES_SOURCE)
    return _result("supported" if count >= 2 else "not_supported", ev, None, settle,
                   "held on paper with this note number; two real deliveries would need two")


def supplier_reissued_note(f: dict, ctx: Context) -> dict:
    return _result("cannot_test", None, None, "The supplier's invoice or monthly statement")


# --- job_outlier (P1) -------------------------------------------------------------------------------------------------

def _job(f: dict, ctx: Context) -> tuple[pd.Series, pd.DataFrame]:
    """The job and the jobs it was compared with (same site and job type, the same filter as detect_anomalies)."""
    j = ctx.jobs
    job = j[j.job_id == f["job_id"]].iloc[0]
    peers = j[(j.site_id == job.site_id) & (j.operation_code == job.operation_code) & (j.hours >= MIN_JOB_HOURS) & (j.litres > 0)]
    return job, peers


def recorder_froze_during_job(f: dict, ctx: Context) -> dict:
    settle = "The recorder's own time stamps for this job, to see whether a frozen stretch falls inside it"
    fr = ctx.frozen[(ctx.frozen.machine_id == f["machine_id"]) & (ctx.frozen.month == f["month"])]
    hours = float(fr.hours.sum())
    ev = _fig(hours, "h", bullets(
        f"The machine's recorder repeated the same readings for **{hours:,.1f} hours** in {month_name(f['month'])}.",
        "Frozen time is recorded per month only, so we cannot tell whether any of it falls inside this job.",
        "The month comes from the rule that places the machine's data in the company year."),
        ctx.site_sources.get(f["site_id"]), label="allocated")
    return _result("not_supported" if hours == 0 else "cannot_test", ev, None, settle,
                   "in the same month when the machine's recorder repeated the same readings")


def high_engine_load(f: dict, ctx: Context) -> dict:
    settle = "The job notes for that day: soil, working depth, tool width and speed"
    job, peers = _job(f, ctx)
    usual = float(peers.mean_load_pct.median())
    if pd.isna(job.mean_load_pct) or pd.isna(usual) or usual <= 0:
        return _result("cannot_test", None, None, settle)
    load_dev = 100 * (float(job.mean_load_pct) / usual - 1)
    fuel_dev = float(f["difference_pct"])
    ok = load_dev * fuel_dev > 0 and abs(load_dev) >= LOAD_SHARE * abs(fuel_dev)
    ev = _fig(job.mean_load_pct, "%", bullets(
        f"The engine ran at **{job.mean_load_pct:.0f}% load** on average in this job; jobs of the same kind usually run at **{usual:.0f}%**.",
        f"That is **{load_dev:+.0f}%** against **{fuel_dev:+.0f}%** fuel per hour.",
        "A heavier or lighter load explains the fuel if it moves the same way, by at least half as much."),
        ctx.site_sources.get(f["site_id"]))
    return _result("supported" if ok else "not_supported", ev, None, settle, "average engine load during this job")


def long_idling(f: dict, ctx: Context) -> dict:
    settle = "The job sheet: waits for trailers, weather or refills during the job"
    job, peers = _job(f, ctx)
    usual = peers.idle_ratio.median()
    if pd.isna(job.idle_ratio) or pd.isna(usual):
        return _result("cannot_test", None, None, settle)
    idle, usual = 100 * float(job.idle_ratio), 100 * float(usual)
    ok = f["direction"] == "less" and idle >= usual + IDLE_POINTS
    ev = _fig(idle, "%", bullets(
        f"The engine idled for **{idle:.0f}%** of this job; jobs of the same kind usually idle for **{usual:.0f}%**.",
        "Idling burns less fuel per hour than work, so it can explain only a job that burned less per hour, "
        f"and only if it idled at least {IDLE_POINTS:.0f} points more than usual."), ctx.site_sources.get(f["site_id"]))
    return _result("supported" if ok else "not_supported", ev, None, settle, "of this job's engine time spent idling")


def recent_maintenance(f: dict, ctx: Context) -> dict:
    settle = "The workshop record of what was done, and the next jobs of the same kind on this machine"
    job, _ = _job(f, ctx)
    day = pd.Timestamp(job.start_ts).normalize()
    m = ctx.maintenance
    before = m[(m.machine_id == f["machine_id"]) & (m.date <= day)]
    if before.empty:
        return _result("not_supported", None, None, settle)
    last = before.loc[before.date.idxmax()]
    days = int((day - last.date).days)
    assigned = str(job.get("date_basis", "")) == "assigned"
    ev = _fig(days, "days", bullets(
        f"The last workshop visit before this job was **{days} days** earlier ({last.event_type.lower()}).",
        f"A visit in the {MAINTENANCE_DAYS} days before a job can still change how the machine runs.",
        "The workshop records are illustrative." + (" The job's date was assigned by rule, so the gap in days is approximate."
                                                    if assigned else "")),
        SYNTHETIC, label="allocated" if assigned else "measured")
    return _result("supported" if days <= MAINTENANCE_DAYS else "not_supported", ev, None, settle,
                   "since the last workshop visit before this job")


# --- high_non_work_share (P1) -----------------------------------------------------------------------------------------

NON_WORK_NAMES = {"road_transport": "driving on roads", "implement_nonproductive": "with a tool attached but not working",
                  "idle": "idling"}


def _non_work(category: str) -> Callable[[dict, Context], dict]:
    def test(f: dict, ctx: Context) -> dict:
        site = ctx.ledger[ctx.ledger.site_id == f["site_id"]]
        total = site.groupby("machine_id").litres.sum()
        part = site[site.operation_code == "other_" + category].groupby("machine_id").litres.sum().reindex(total.index, fill_value=0)
        share = part / total
        usual = float(share.median())
        excess_c, excess = float((share[f["machine_id"]] - usual) * total[f["machine_id"]]), _excess(f)
        ok = excess_c > 0 and excess_c >= NON_WORK_PART * excess
        ev = _fig(excess_c, "L", bullets(
            f"This tractor burned **{100 * share[f['machine_id']]:.1f}%** of its fuel {NON_WORK_NAMES[category]}; "
            f"the middle tractor on the site burns **{100 * usual:.1f}%**.",
            f"At this tractor's total that is **{excess_c:,.0f} litres** more (a negative figure means less), "
            f"against **{excess:,.0f} litres** for all non-work fuel.",
            f"It counts as a main part if it carries at least {100 * NON_WORK_PART:.0f}% of that.",
            "The split of fuel into these uses is made by rule, so it is allocated."),
            ctx.site_sources.get(f["site_id"]), label="allocated")
        return _result("supported" if ok else "not_supported", ev, 100 * excess_c / excess if ok else None,
                       "A week of this tractor's trips and waits between jobs",
                       f"burned {NON_WORK_NAMES[category]} beyond the site's middle share")
    test.__name__ = f"non_work_{category}"
    return test


non_work_road_transport = _non_work("road_transport")
non_work_implement_not_working = _non_work("implement_nonproductive")
non_work_idle = _non_work("idle")


# --- data_gap (P1) ----------------------------------------------------------------------------------------------------

MONTH_RULE = "The months come from the rule that places the machine's data in the company year, so they are allocated."


def _gap_months(machine: str, ctx: Context) -> pd.Series:
    """Frozen hours by month, counting only months over the one-hour floor, as the data_gap finding does."""
    fr = ctx.frozen[ctx.frozen.machine_id == machine].groupby("month").hours.sum()
    return fr[fr > MIN_FROZEN_HOURS]


def gap_in_one_period(f: dict, ctx: Context) -> dict:
    settle = "The workshop log for that month: a loose plug, a power cut or a swapped recorder"
    months = _gap_months(f["machine_id"], ctx)
    if months.empty:
        return _result("cannot_test", None, None, settle)
    top, total = float(months.max()), float(months.sum())
    ev = _fig(top, "h", bullets(
        f"The worst month, {month_name(months.idxmax())}, holds **{top:,.1f} of {total:,.1f} frozen hours** "
        f"(months with more than {MIN_FROZEN_HOURS:.0f} hour, as in the finding).",
        f"A one-off fault puts at least {100 * ONE_PERIOD_SHARE:.0f}% of the hours in one month.", MONTH_RULE),
        ctx.site_sources.get(f["site_id"]), label="allocated")
    share = top / total
    return _result("supported" if share >= ONE_PERIOD_SHARE else "not_supported", ev, 100 * share, settle,
                   "frozen in the worst single month")


def gap_recurs(f: dict, ctx: Context) -> dict:
    settle = "A check of the recorder's wiring and power supply"
    n = len(_gap_months(f["machine_id"], ctx))
    ev = _fig(n, "months", bullets(
        f"The recorder froze for more than {MIN_FROZEN_HOURS:.0f} hour in **{n} month{'s' if n != 1 else ''}**.",
        f"A fault that comes back shows in at least {RECURRING_MONTHS} separate months.", MONTH_RULE),
        ctx.site_sources.get(f["site_id"]), label="allocated")
    return _result("supported" if n >= RECURRING_MONTHS else "not_supported", ev, None, settle,
                   "with more than an hour of frozen readings")


def site_wide_logging_problem(f: dict, ctx: Context) -> dict:
    settle = "The recorder supplier's service log for the site"
    mine = set(_gap_months(f["machine_id"], ctx).index)
    if not mine:
        return _result("cannot_test", None, None, settle)
    fr = ctx.frozen
    others = fr[(fr.machine_id.str[:2] == f["site_id"]) & (fr.machine_id != f["machine_id"])]
    others = others.groupby(["machine_id", "month"]).hours.sum()
    shared = len({m for (_, m), h in others.items() if h > MIN_FROZEN_HOURS and m in mine})
    ev = _fig(shared, "months", bullets(
        f"In **{shared} of the {len(mine)} months** when this recorder froze, another machine on the same site froze too.",
        "A problem with the site's logging would show on several machines in at least half of those months.", MONTH_RULE),
        ctx.site_sources.get(f["site_id"]), label="allocated")
    return _result("supported" if shared >= 0.5 * len(mine) else "not_supported", ev, None, settle,
                   "in which another machine on the same site froze too")


# --- the menu ---------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Hypothesis:
    id: str
    title: str
    description: str
    test: Callable[[dict, Context], dict]


REGISTRY: dict[str, list[Hypothesis]] = {
    "machine_over_dispense": [
        Hypothesis("night_fuel_outside_shift", "Fuel was taken at night, outside the machine's working hours",
                   "Dispenses late at night with no job nearby, so the fuel may have gone somewhere else.", night_fuel_outside_shift),
        Hypothesis("logging_or_meter_error", "Fuel was booked to the wrong machine, or logged twice",
                   "Other machines on the same depot are short by the same amount, or dispense rows repeat.", logging_or_meter_error),
        Hypothesis("recorder_understates_burn", "The machine burned more than its recorder shows",
                   "A frozen recorder misses fuel, so the machine looks as if it was given too much.", recorder_understates_burn),
        Hypothesis("fuel_used_elsewhere", "The fuel went into cans, another vehicle or a contractor",
                   "Fuel drawn against this machine but used by something else.", fuel_used_elsewhere),
    ],
    "stock_gap": [
        Hypothesis("unlogged_withdrawal", "Fuel left the tank without a dispense record",
                   "The gap jumps once and stays, as it would after one large unrecorded withdrawal.", unlogged_withdrawal),
        Hypothesis("dip_reading_error", "The tank level was misread",
                   "A misread dip goes back to normal at the next reading.", dip_reading_error),
        Hypothesis("delivery_not_received_or_duplicated", "A delivery was logged but never arrived",
                   "A logged delivery with no paper note, or entered twice, that matches the gap.", delivery_not_received_or_duplicated),
        Hypothesis("leak_or_theft", "A leak or theft from the tank",
                   "Fuel logs alone cannot tell a leak or theft apart from an unrecorded withdrawal.", leak_or_theft),
    ],
    "duplicate_delivery_note": [
        Hypothesis("same_note_entered_twice", "The same delivery note was typed in twice",
                   "Two log rows with the same depot, supplier, note number and litres.", same_note_entered_twice),
        Hypothesis("two_real_deliveries", "There really were two deliveries with the same note number",
                   "That would need two paper notes with this number.", two_real_deliveries),
        Hypothesis("supplier_reissued_note", "The supplier reissued the note for a second delivery",
                   "Only the supplier's invoices could show this.", supplier_reissued_note),
    ],
    "job_outlier": [
        Hypothesis("high_engine_load", "The job was heavier or lighter work than usual",
                   "Engine load moves with fuel per hour: harder ground, a deeper setting or a wider tool.", high_engine_load),
        Hypothesis("long_idling", "The engine idled for a long time during the job",
                   "Idling burns less per hour than work, so long waits lower fuel per hour.", long_idling),
        Hypothesis("recent_maintenance", "A recent workshop visit changed how the machine runs",
                   "A repair or adjustment shortly before the job, such as a new filter or brakes.", recent_maintenance),
        Hypothesis("recorder_froze_during_job", "The recorder froze during the job",
                   "Frozen readings would make the job's hours or fuel wrong.", recorder_froze_during_job),
    ],
    "high_non_work_share": [
        Hypothesis("non_work_road_transport", "Long road trips between fields",
                   "More fuel on roads than the other tractors on the site.", non_work_road_transport),
        Hypothesis("non_work_implement_not_working", "A tool attached but not working",
                   "More fuel with a tool attached but not working, such as turning or waiting at the headland.",
                   non_work_implement_not_working),
        Hypothesis("non_work_idle", "Long idling",
                   "More fuel burned with the engine running and the tractor standing still.", non_work_idle),
    ],
    "data_gap": [
        Hypothesis("gap_in_one_period", "A one-off fault in one period",
                   "Most of the frozen time falls in one month, as after a single fault that was then fixed.", gap_in_one_period),
        Hypothesis("gap_recurs", "A fault that keeps coming back",
                   "The recorder froze in several separate months, as with a loose connection.", gap_recurs),
        Hypothesis("site_wide_logging_problem", "A problem with the site's logging, not this machine",
                   "Other machines on the same site froze in the same months.", site_wide_logging_problem),
    ],
}


def order(rows: list[dict]) -> list[dict]:
    """Supported first (largest share of the finding first, those without a share after), then cannot test, then not
    supported. A stable sort, so the menu order breaks the remaining ties."""
    return sorted(rows, key=lambda h: (RANK[h["status"]], h["explains_pct"] is None, -(h["explains_pct"] or 0)))


def diagnose(finding: dict, ctx: Context) -> dict:
    menu = REGISTRY.get(finding["kind"])
    if not menu:
        raise ValueError(f"no causes to test for a finding of kind {finding['kind']}")
    rows = [{"id": h.id, "title": h.title, "description": h.description, **h.test(finding, ctx), "suggested_by": "code"}
            for h in menu]
    for r in rows:
        r["status_text"] = STATUS_TEXT[r["status"]]
    return {"finding_id": finding["id"], "kind": finding["kind"], "title": finding["title"],
            "finding_figure": finding["litres"], "hypotheses": order(rows), "disclaimer": DISCLAIMER}


def find_finding(finding_id: str, recon: dict | None = None) -> dict:
    recon = recon or reconcile_fuel()
    for f in recon["findings"] + detect_anomalies()["findings"]:
        if f["id"] == finding_id:
            return f
    raise ValueError(f"unknown finding id {finding_id!r}; use an id from reconcile_fuel or detect_anomalies")


def diagnose_anomaly(finding_id: str) -> dict:
    """Possible causes of one finding, each tested against the data by code: supported, not supported, or cannot be
    tested with our data. A person decides; no cause is named as the answer. `finding_id` comes from reconcile_fuel or detect_anomalies."""
    recon = reconcile_fuel()
    finding = find_finding(finding_id, recon)
    if finding["kind"] not in REGISTRY:
        raise ValueError(f"no causes to test for a finding of kind {finding['kind']}")
    return diagnose(finding, Context.from_data(recon))
