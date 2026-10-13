"""Agent tool: read the fleet's delivery notes and check them against the fuel log.

Gemini reads each note (backend/tools/extract_receipt.py); rules R1-R8 decide which lines count
(backend/receipts/validate.py); this code matches each note to the log by supplier and note number and
compares litres, date and unit price. Until Gemini has read every note, the notes' ground truth stands in
and `data_source` says so. Nothing here does arithmetic in a model.
"""
from __future__ import annotations

import re

import pandas as pd

from backend.emissions.text import bullets
from backend.fleet import data
from backend.receipts.ground_truth import ground_truth_extractions
from backend.receipts.validate import fleet_settings, validate
from backend.tools.contracts import Figure
from backend.tools.extract_receipt import FARM_RECEIPTS, cache_path, read_receipt

SOURCE = "fleet_delivery_notes"
LOG_SOURCE = "fleet_synthetic"
SEVERITY = {"entered_twice": "high", "note_not_in_log": "high", "litres_differ": "high", "price_differs": "medium",
            "date_differs": "low", "log_row_without_note": "medium", "note_needs_review": "low"}


def _key(supplier, doc_no) -> tuple[str, str]:
    return re.sub(r"[^a-z]", "", str(supplier or "").lower()), re.sub(r"\D", "", str(doc_no or ""))


def _readings() -> tuple[dict[str, dict], str]:
    ids = sorted(p.stem for p in (FARM_RECEIPTS["fleet"] / "receipts").glob("*.jpg"))
    if ids and all(cache_path("fleet", i).exists() for i in ids):
        raw = {i: read_receipt(i, "fleet") for i in ids}
        model = next(iter(raw.values())).model_id
        return {i: r.extracted for i, r in raw.items()}, f"Gemini readings ({model}), checked by validation rules R1-R8"
    return ground_truth_extractions("fleet"), "delivery-note ground truth (Gemini reading pending the Vertex AI endpoint decision)"


def _litres(value: float, how: str, *sources: str) -> dict:
    return vars(Figure(round(value, 2), "L", "measured", how, sources))


def _gbp(value: float, how: str, *sources: str) -> dict:
    return vars(Figure(round(value, 2), "GBP", "measured", how, sources))


def _finding(kind: str, doc_no: str, title: str, figure: dict | None, **extra) -> dict:
    return {"kind": kind, "severity": SEVERITY[kind], "doc_no": doc_no, "title": title, "figure": figure, **extra}


def check_delivery_notes(litres_tolerance: float = 0.5, price_tolerance: float = 0.00005) -> dict:
    """Each delivery note against the fuel log: matches, differs (which field and what it costs),
    is missing from the log, or is entered twice; and log rows that have no note behind them."""
    readings, source = _readings()
    lines = validate(sorted(readings.items()), "fleet", fleet_settings())
    log = data.deliveries().assign(key=lambda d: [_key(s, n) for s, n in zip(d.supplier, d.doc_no)])
    findings, matched, used_rows = [], 0, set()
    for rid, x in sorted(readings.items()):
        doc_lines = [l for l in lines if l.receipt_id == rid]
        fuel = [l for l in doc_lines if l.counts and l.litres]
        review = [l for l in doc_lines if l.outcome == "needs_review"]
        doc_no = x.get("doc_number") or rid
        if review:
            findings.append(_finding("note_needs_review", doc_no, f"Delivery note {doc_no} could not be read with confidence",
                                     None, reasons=sorted({r for l in review for r in l.reasons})))
            continue
        rows = log[log.key == _key(x.get("supplier"), doc_no)]
        litres = sum(l.litres for l in fuel)
        if rows.empty:
            findings.append(_finding("note_not_in_log", doc_no, f"Delivery note {doc_no} is not in the fuel log", _litres(
                litres, bullets(f"The note shows **{litres:,.0f} litres** delivered.",
                                "No row in the fuel log has this supplier and note number, so the depot's books miss it."),
                SOURCE)))
            continue
        used_rows |= set(rows.delivery_id)
        first = rows.iloc[0]
        diffs = 0
        if len(rows) > 1:
            diffs += 1
            findings.append(_finding("entered_twice", doc_no, f"Delivery note {doc_no} is in the fuel log {len(rows)} times",
                                     _litres(float(first.litres) * (len(rows) - 1), bullets(
                                         f"There is **one paper note** for **{litres:,.0f} litres**.",
                                         f"The fuel log has **{len(rows)} rows** with its supplier and number.",
                                         "Only one delivery happened, so the extra rows overstate fuel received."),
                                         SOURCE, LOG_SOURCE)))
        if abs(litres - float(first.litres)) > litres_tolerance:
            diffs += 1
            findings.append(_finding("litres_differ", doc_no, f"Litres on note {doc_no} differ from the fuel log",
                                     _litres(litres - float(first.litres), bullets(
                                         f"Note: **{litres:,.1f} litres**. Log: **{first.litres:,.1f} litres**."),
                                         SOURCE, LOG_SOURCE)))
        price = next((l.unit_price_gbp for l in fuel if l.unit_price_gbp is not None), None)
        if price is not None and abs(price - float(first.unit_price_gbp)) > price_tolerance:
            diffs += 1
            cost = (float(first.unit_price_gbp) - price) * litres
            findings.append(_finding("price_differs", doc_no, f"The price on note {doc_no} differs from the fuel log",
                                     _gbp(cost, bullets(
                                         f"Note: **£{price:.4f} a litre**. Log: **£{first.unit_price_gbp:.4f} a litre**.",
                                         f"On **{litres:,.0f} litres** the log's fuel cost is off by **£{abs(cost):,.2f}** "
                                         f"({'too high' if cost > 0 else 'too low'}).",
                                         "Likely a keying error: check the invoice before paying or reporting."),
                                         SOURCE, LOG_SOURCE), on_note=price, in_log=float(first.unit_price_gbp)))
        if str(x.get("date")) != first.ts.date().isoformat():
            diffs += 1
            findings.append(_finding("date_differs", doc_no, f"The date on note {doc_no} differs from the fuel log", None,
                                     on_note=x.get("date"), in_log=first.ts.date().isoformat()))
        matched += diffs == 0
    for r in log[~log.delivery_id.isin(used_rows)].itertuples():
        findings.append(_finding("log_row_without_note", r.doc_no, f"Fuel log row {r.delivery_id} has no delivery note",
                                 _litres(float(r.litres), bullets(f"The log records **{r.litres:,.0f} litres**.",
                                                                  "No delivery note was found for it."), LOG_SOURCE)))
    note_litres = sum(l.litres for l in lines if l.counts and l.litres)
    log_litres = float(log.litres.sum())
    return {
        "data_source": source,
        "notes": len(readings), "log_rows": len(log), "notes_matching_log": matched,
        "litres_on_notes": _litres(note_litres, bullets(f"Fuel lines on **{len(readings)} delivery notes**, read and "
                                                        "checked by fixed rules."), SOURCE),
        "litres_in_log": _litres(log_litres, bullets(f"**{len(log)} rows** in the fuel log, as entered."), LOG_SOURCE),
        "findings": sorted(findings, key=lambda f: ["high", "medium", "low"].index(f["severity"])),
        "note": "Gemini reads the notes; fixed rules and code do every check. Synthetic demo documents.",
    }
