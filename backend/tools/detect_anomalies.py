from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from backend.emissions.text import bullets, month_name
from backend.fleet import data
from backend.tools.contracts import Figure

NON_WORK = ("idle", "implement_nonproductive", "road_transport")


def _severity(value: float, unit: str) -> str:
    big = 24 if unit == "h" else 500
    return "high" if value >= big else "medium" if value >= big / 5 else "low"


def _fig(value: float, unit: str, label: str, how: str, *sources: str) -> dict:
    return asdict(Figure(value, unit, label, how, source_ids=tuple(sources)))


def detect_anomalies(z_limit: float = 3.5, min_group_jobs: int = 8, min_hours: float = 0.3, min_dev_pct: float = 30.0,
                     share_ratio: float = 1.25) -> dict:
    """Things in the machines' own data that are worth a look: frozen recorders, unusual jobs, heavy non-work fuel.

    These are observations from statistics, not proof of a fault. Operators are never named or compared.
    """
    findings: list[dict] = []

    # 1. Recorders that repeated the same values.
    other = data.other_activity()
    for r in other[(other.activity_class == "data_gap") & (other.hours > 1)].groupby("machine_id").hours.sum().items():
        machine, hours = r
        months = other[(other.activity_class == "data_gap") & (other.machine_id == machine) & (other.hours > 0)].sort_values("month")
        spread = ", ".join(f"{month_name(m)} ({h:.1f} h)" for m, h in zip(months.month, months.hours))
        findings.append({
            "kind": "data_gap", "severity": _severity(hours, "h"), "machine_id": machine, "machine": data.machine_name(machine),
            "site_id": machine[:2], "month": None, "robust_z": None, "difference_pct": None,
            "title": f"The recorder on {data.machine_name(machine)} froze for {hours:,.0f} hours" if hours >= 10
                     else f"The recorder on {data.machine_name(machine)} froze for {hours:.1f} hours",
            "litres": _fig(float(hours), "h", "measured", bullets(
                f"The recorder on {data.machine_name(machine)} saved **the same readings, over and over, for {hours:,.1f} hours**: engine speed, fuel flow and position never changed.",
                f"The frozen stretches fall in these months: **{spread}**.",
                "The original recording has no calendar dates, so these months come from the rule that places this machine's fuel in the company year.",
                "A working tractor does not do that, so this is a **recording fault**, not real work.",
                "We **left those hours out** and counted no fuel for them. The fuel burned in that time is unknown, not zero.",
                "So the fleet's real fuel use may be **higher** than shown. Check this tractor's recorder and its connection."), "tum_alc_data")})

    # 2. Jobs whose fuel per hour is far from what the same job usually needs.
    j = data.jobs()
    j = j[(j.hours >= min_hours) & (j.litres > 0)].assign(lph=lambda d: d.litres / d.hours)
    for (site, op), g in j.groupby(["site_id", "operation_code"]):
        if len(g) < min_group_jobs:
            continue
        median = g.lph.median()
        mad = 1.4826 * (g.lph - median).abs().median()
        if mad <= 0:
            continue
        for r in g.itertuples():
            z = (r.lph - median) / mad
            dev = 100 * (r.lph / median - 1)
            if abs(z) < z_limit or abs(dev) < min_dev_pct:
                continue
            more = dev > 0
            litres = abs(r.lph - median) * r.hours
            findings.append({
                "kind": "job_outlier", "severity": _severity(litres, "L"), "machine_id": r.machine_id,
                "machine": data.machine_name(r.machine_id), "site_id": site, "month": str(r.start_ts.to_period("M")),
                "robust_z": float(z), "difference_pct": float(dev), "direction": "more" if more else "less",
                "title": (f"{data.machine_name(r.machine_id)} burned {abs(dev):.0f}% {'more' if more else 'less'} fuel per hour than usual "
                          f"for {data.operation_name(op).lower()} on {r.start_ts.date():%d %B %Y}"),
                "litres": _fig(float(litres), "L", "measured", bullets(
                    f"On {r.start_ts.date():%d %B %Y}, {data.machine_name(r.machine_id)} did {data.operation_name(op).lower()} and burned **{r.lph:.1f} litres an hour**.",
                    f"Other jobs of the same kind at {data.site_name(site)} usually burn **{median:.1f} litres an hour**, so this one burned **{abs(dev):.0f}% {'more' if more else 'less'}**.",
                    f"Over its {r.hours:.1f} hours that is about **{litres:,.0f} litres** {'extra' if more else 'less'}.",
                    "The data cannot say why. Compare it with the job notes: ground, tool, speed or a long trip could all play a part.",
                    "It is worth a look, not proof of a fault."), data.sites().source_id[site])})

    # 3. Machines that burn a bigger share of their fuel on idling, travel and tool-not-working than their peers (arable site).
    ledger = data.ledger()
    s1 = ledger[ledger.site_id == "S1"]
    total = s1.groupby("machine_id").litres.sum()
    waste = s1[s1.operation_code.isin(["other_" + c for c in NON_WORK])].groupby("machine_id").litres.sum().reindex(total.index, fill_value=0)
    share = waste / total
    median = float(share.median())
    for machine, value in share.items():
        excess = (value - median) * total[machine]
        if median > 0 and value >= share_ratio * median and excess >= 100:
            findings.append({
                "kind": "high_non_work_share", "severity": _severity(excess, "L"), "machine_id": machine,
                "machine": data.machine_name(machine), "site_id": "S1", "month": None, "robust_z": None,
                "difference_pct": float(100 * (value / median - 1)),
                "title": f"{data.machine_name(machine)} spent {100 * value:.0f}% of its fuel on idling, travel and tool-not-working",
                "litres": _fig(float(excess), "L", "allocated", bullets(
                    f"Over the company year (May 2025 to April 2026), **{100 * value:.0f}%** of this tractor's fuel was burned while idling, driving on roads, or with a tool attached but not working.",
                    f"The middle tractor on the arable site spends **{100 * median:.0f}%** that way, so this one burned about **{excess:,.0f} litres** more than that.",
                    "The total fuel is measured. Splitting it into these uses is done **by rule**, so the split is allocated, not measured.",
                    "Worth a look at how this tractor is used between jobs, not proof of waste."), "tum_alc_data")})

    findings.sort(key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f["severity"]], -f["litres"]["value"]))
    return {"findings": findings, "settings": {"z_limit": z_limit, "min_group_jobs": min_group_jobs, "min_hours": min_hours,
                                               "min_dev_pct": min_dev_pct, "share_ratio": share_ratio}}
