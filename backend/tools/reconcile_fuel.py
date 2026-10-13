from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from backend.emissions.text import bullets, month_name
from backend.fleet import data
from backend.tools.contracts import Figure

SYNTHETIC = "fleet_synthetic"


def _litres(value: float, how: str, *sources: str) -> dict:
    return asdict(Figure(value, "L", "measured", how, source_ids=tuple(dict.fromkeys(sources))))


def _severity(litres: float) -> str:
    return "high" if litres >= 500 else "medium" if litres >= 100 else "low"


def _night_dispenses(night_from: int, night_to: int) -> pd.DataFrame:
    """Dispenses at night on a machine that had no job within two hours either side."""
    d, jobs = data.dispenses(), data.jobs()
    end = jobs.start_ts + pd.to_timedelta(jobs.hours, unit="h")
    out = []
    for r in d[(d.ts.dt.hour >= night_from) | (d.ts.dt.hour < night_to)].itertuples():
        near = jobs[(jobs.machine_id == r.machine_id) & (jobs.start_ts - pd.Timedelta(hours=2) <= r.ts)
                    & (end + pd.Timedelta(hours=2) >= r.ts)]
        if near.empty:
            out.append(r._asdict())
    return pd.DataFrame(out, columns=list(d.columns) + ["Index"]).drop(columns="Index")


def _day(t: pd.Timestamp, year: bool = True) -> str:
    return f"{t.day} {t:%B %Y}" if year else f"{t.day} {t:%B}"


def _span(ts: pd.Series) -> str:
    """Dates as people say them: one day, or the first to the last day."""
    first, last = ts.min(), ts.max()
    if first.date() == last.date():
        return _day(first)
    return f"{_day(first, first.year != last.year)} to {_day(last)}"


def reconcile_fuel(ratio_limit: float = 1.10, min_litres: float = 50.0, stock_tolerance_l: float = 100.0,
                   night_from_hour: int = 22, night_to_hour: int = 5) -> dict:
    """Does the fuel handed out match the fuel burned, and does the depot's book stock match its measured stock?

    Works only from the logs and the machines' fuel data; it never reads the planted-problem answer file.
    """
    findings: list[dict] = []
    deliveries, disp = data.deliveries(), data.dispenses().assign(month=lambda d: d.ts.dt.to_period("M").astype(str))

    # 1. The same delivery note entered twice.
    keys = ["depot_id", "supplier", "doc_no", "litres"]
    dup = deliveries[deliveries.duplicated(keys, keep="first")]
    valid = deliveries[~deliveries.duplicated(keys, keep="first")]
    for r in dup.itertuples():
        site = data.depots().site_id[r.depot_id]
        first_ts = deliveries[~deliveries.duplicated(keys, keep="first") & (deliveries.doc_no == r.doc_no) & (deliveries.depot_id == r.depot_id)].ts.iloc[0]
        when = f"both on **{_span(pd.Series([r.ts]))}**" if first_ts.date() == r.ts.date() else f"on **{_span(pd.Series([first_ts]))}** and again on **{_span(pd.Series([r.ts]))}**"
        findings.append({
            "kind": "duplicate_delivery_note", "severity": _severity(r.litres), "title":
            f"Delivery note {r.doc_no} was entered twice at the {data.site_name(site)} depot",
            "site_id": site, "site": data.site_name(site), "machine_id": None, "machine": None, "depot_id": r.depot_id,
            "month": str(r.ts.to_period("M")), "ratio": None, "night_dispenses": 0,
            "litres": _litres(r.litres, bullets(
                f"Delivery note **{r.doc_no}** from {r.supplier} for **{r.litres:,.0f} litres** was entered twice, {when}.",
                "The same note number, depot and litres can only be one delivery, so we count it once when comparing the depot's stock.",
                f"Counting both would make the books show {r.litres:,.0f} litres that never arrived."), SYNTHETIC)})

    # 2. Fuel handed to each machine against fuel it burned.
    burned = data.ledger().groupby(["machine_id", "month"]).litres.sum()
    given = disp.groupby(["machine_id", "month"]).litres.sum()
    table = pd.concat({"dispensed": given, "burned": burned}, axis=1).fillna(0.0)
    table = table[(table.dispensed > 0) | (table.burned > 0)]
    table["ratio"] = (table.dispensed / table.burned).where(table.burned > 0)
    night = _night_dispenses(night_from_hour, night_to_hour)
    night = night.assign(month=night.ts.dt.to_period("M").astype(str))
    night_on = night.groupby(["machine_id", "month"]).ts.apply(_span) if len(night) else pd.Series(dtype=str)
    night = night.groupby(["machine_id", "month"]).litres.agg(["count", "sum"]) if len(night) else pd.DataFrame(columns=["count", "sum"])
    given_on = disp.groupby(["machine_id", "month"]).ts.apply(_span)
    flagged = set()
    for (machine, month), r in table.iterrows():
        site = data.machines().site_id[machine]
        source = data.sites().source_id[site]
        n, n_litres = (int(night.loc[(machine, month), "count"]), float(night.loc[(machine, month), "sum"])) if (machine, month) in night.index else (0, 0.0)
        over = r.ratio is not None and r.ratio >= ratio_limit and r.dispensed - r.burned >= min_litres
        under = r.ratio is not None and r.ratio <= 1 / ratio_limit and r.burned - r.dispensed >= min_litres
        base = {"site_id": site, "site": data.site_name(site), "machine_id": machine, "machine": data.machine_name(machine),
                "depot_id": None, "month": month, "ratio": None if pd.isna(r.ratio) else float(r.ratio),
                "night_dispenses": n}
        if over:
            flagged.add((machine, month))
            findings.append({**base, "kind": "machine_over_dispense", "severity": _severity(r.dispensed - r.burned),
                "title": f"{data.machine_name(machine)} at {data.site_name(site)} was given {100 * (r.ratio - 1):.0f}% more fuel than it burned in {month_name(month)}",
                "litres": _litres(r.dispensed - r.burned, bullets(
                    f"**{r.dispensed:,.0f} litres** were handed to {data.machine_name(machine)} in {month_name(month)} (dispenses from **{given_on[(machine, month)]}**).",
                    f"The machine's own fuel data shows it burned **{r.burned:,.0f} litres**.",
                    *([f"**{n} of the dispenses** ({n_litres:,.0f} litres) happened at night, when the machine had no job (**{night_on[(machine, month)]}**)."] if n else [])),
                    SYNTHETIC, source)})
        elif under:
            flagged.add((machine, month))
            findings.append({**base, "kind": "machine_under_dispense", "severity": _severity(r.burned - r.dispensed),
                "title": f"{data.machine_name(machine)} at {data.site_name(site)} burned more fuel than it was given in {month_name(month)}",
                "litres": _litres(r.burned - r.dispensed, bullets(
                    f"**{r.dispensed:,.0f} litres** were handed out in {month_name(month)} but the machine burned **{r.burned:,.0f} litres**.",
                    "The rest came from somewhere not logged."), SYNTHETIC, source)})
        elif n:
            findings.append({**base, "kind": "night_dispense", "severity": _severity(n_litres),
                "title": f"{data.machine_name(machine)} at {data.site_name(site)} took fuel at night in {month_name(month)}",
                "litres": _litres(n_litres, bullets(f"**{n} dispenses** ({n_litres:,.0f} litres) happened at night, when the machine had no job (**{night_on[(machine, month)]}**)."),
                                  SYNTHETIC, source)})
    machine_rows = [{"machine_id": m, "machine": data.machine_name(m), "month": mo, "dispensed_l": float(r.dispensed),
                     "burned_l": float(r.burned), "ratio": None if pd.isna(r.ratio) else float(r.ratio),
                     "flagged": (m, mo) in flagged} for (m, mo), r in table.iterrows()]

    # 3. Each depot's book stock (opening + deliveries - dispenses) against the stock actually measured.
    depot_rows = []
    for depot_id, dep in data.depots().iterrows():
        prev_gap, prev_date, site = 0.0, None, dep.site_id
        for rd in data.stock_readings()[data.stock_readings().depot_id == depot_id].sort_values("date").itertuples():
            until = rd.date + pd.Timedelta(days=1)
            book = dep.opening_stock_l + valid[(valid.depot_id == depot_id) & (valid.ts < until)].litres.sum() \
                - disp[(disp.depot_id == depot_id) & (disp.ts < until)].litres.sum()
            gap = float(book - rd.dip_litres)
            step, month = gap - prev_gap, str(rd.date.to_period("M"))
            depot_rows.append({"depot_id": depot_id, "depot": f"{data.site_name(site)} depot", "month_end": str(rd.date.date()),
                               "book_l": float(book), "measured_l": float(rd.dip_litres), "gap_l": gap})
            if abs(step) >= stock_tolerance_l:
                loss = step > 0
                findings.append({
                    "kind": "stock_gap" if loss else "stock_surplus", "severity": _severity(abs(step)),
                    "title": (f"About {abs(step):,.0f} litres {'are missing from' if loss else 'extra were found in'} the "
                              f"{data.site_name(site)} depot, first seen in {month_name(month)}"),
                    "site_id": site, "site": data.site_name(site), "machine_id": None, "machine": None, "depot_id": depot_id,
                    "month": month, "ratio": None, "night_dispenses": 0,
                    "litres": _litres(abs(step), bullets(
                        f"The depot's books (deliveries minus dispenses) say **{book:,.0f} litres** should be in the tank.",
                        f"The measured level was **{rd.dip_litres:,.0f} litres**.",
                        f"The gap {'grew' if loss else 'shrank'} by **{abs(step):,.0f} litres** between the tank readings of "
                        + (f"**{_day(prev_date)}** and **{_day(rd.date)}**." if prev_date is not None else f"the start of the year and **{_day(rd.date)}**.")),
                        SYNTHETIC)})
            prev_gap, prev_date = gap, rd.date

    findings.sort(key=lambda f: -f["litres"]["value"])
    label = {"label": "measured", "source_ids": [SYNTHETIC]}
    return {
        "findings": findings,
        "machine_months": {**label, "how": bullets("Fuel handed to each machine against the fuel it burned, month by month.",
                                                   "A ratio near 100% is normal; the machines' fuel data is the check."), "rows": machine_rows},
        "depots": {**label, "how": bullets("Each depot's book stock against its measured stock at month end.",
                                           "Duplicate delivery notes are removed first, so they are not mistaken for missing fuel."), "rows": depot_rows},
        "settings": {"ratio_limit": ratio_limit, "min_litres": min_litres, "stock_tolerance_l": stock_tolerance_l},
    }
