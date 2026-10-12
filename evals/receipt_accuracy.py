"""Receipt extraction accuracy: Gemini's stored readings vs the Farm B ground truth.

Scores fields per document and per line, the validation outcome per line (AdBlue and the duplicate
must be excluded), and the headline: do the counted litres equal Farm A's measured fuel?

Run: python -m evals.receipt_accuracy        (reads data/synthetic/farm_b/extractions/*.json)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from backend.receipts.validate import ValidatedLine, counted_litres, validate

ROOT = Path(__file__).resolve().parents[1]
FARM_B = ROOT / "data" / "synthetic" / "farm_b"
RESULTS = ROOT / "evals" / "results" / "receipt_accuracy.json"

DOC_TYPES = {"delivery_note": "delivery_note", "merchant_till": "till_receipt", "handwritten": "handwritten_docket"}


def ground_truth() -> tuple[pd.DataFrame, pd.DataFrame]:
    docs = pd.read_csv(FARM_B / "ground_truth_documents.csv", keep_default_na=False)
    lines = pd.read_csv(FARM_B / "ground_truth_lines.csv")
    return docs, lines


def ground_truth_extractions() -> dict[str, dict]:
    """What a perfect reading of each image would return (used as the scoring baseline in tests)."""
    docs, lines = ground_truth()
    out = {}
    for d in docs.itertuples():
        out[d.doc_id] = {
            "doc_type": DOC_TYPES[d.doc_type], "supplier": d.supplier, "doc_number": d.doc_number, "date": d.date,
            "currency": "GBP", "net": d.net_gbp, "vat_rate_pct": 100 * d.vat_rate, "vat": d.vat_gbp,
            "total": d.total_gbp, "confidence": {"litres": "high", "product": "high", "date": "high"}, "notes": None,
            "lines": [{"product": l.product, "litres": l.litres, "quantity_unit": "litres",
                       "unit_price": l.unit_price_gbp, "unit_price_unit": "GBP_per_litre", "line_net": l.net_gbp}
                      for l in lines[lines.doc_id == d.doc_id].itertuples()],
        }
    return out


def _digits(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _close(a, b, tol: float) -> bool:
    try:
        return a is not None and abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _unit_gbp(line: dict) -> float | None:
    p = line.get("unit_price")
    if p is None:
        return None
    return float(p) / 100 if line.get("unit_price_unit") == "pence_per_litre" else float(p)


def score(extractions: dict[str, dict]) -> dict:
    docs, gt_lines = ground_truth()
    validated = validate(sorted(extractions.items()), "b")
    by_line = {(v.receipt_id, v.line_no): v for v in validated}
    rows = []
    for d in docs.itertuples():
        x = extractions.get(d.doc_id)
        doc = {"doc_id": d.doc_id, "doc_type": d.doc_type, "damage": d.damage, "read": x is not None}
        if x is None:
            rows.append(doc)
            continue
        doc.update(date=x.get("date") == d.date, doc_number=_digits(x.get("doc_number")) == _digits(d.doc_number),
                   supplier=str(x.get("supplier") or "").lower().strip() == d.supplier.lower(),
                   total=_close(x.get("total"), d.total_gbp, 0.005))
        got = x.get("lines") or []
        want = gt_lines[gt_lines.doc_id == d.doc_id]
        doc["line_count"] = len(got) == len(want)
        litres_ok = price_ok = outcome_ok = True
        for i, l in enumerate(want.itertuples(), 1):
            g = got[i - 1] if i <= len(got) else {}
            litres_ok &= _close(g.get("litres"), l.litres, 0.005)
            price_ok &= _close(_unit_gbp(g), l.unit_price_gbp, 0.00051)
            v = by_line.get((d.doc_id, i))
            expected_counts = bool(l.counts_toward_fuel)
            outcome_ok &= v is not None and v.counts == expected_counts
        doc.update(litres=litres_ok, unit_price=price_ok, outcome=outcome_ok)
        rows.append(doc)
    table = pd.DataFrame(rows)
    fields = ["date", "doc_number", "supplier", "total", "line_count", "litres", "unit_price", "outcome"]
    read = table[table.read]
    target = round(float(gt_lines[gt_lines.counts_toward_fuel].litres.sum()), 2)
    got_litres = counted_litres(validated)
    return {
        "documents": len(docs), "read": int(table.read.sum()),
        "field_accuracy": {f: round(float(read[f].mean()), 3) for f in fields if f in read},
        "litres_accuracy_by_damage": read.groupby("damage").litres.mean().round(3).to_dict(),
        "counted_litres": got_litres, "target_litres": target, "litres_error": round(got_litres - target, 2),
        "outcomes": pd.Series([v.outcome for v in validated]).value_counts().to_dict(),
        "misread_docs": read[~read[fields].all(axis=1)].doc_id.tolist(),
        "per_document": rows,
    }


def load_extractions(folder: Path = FARM_B / "extractions") -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))["extracted"] for p in sorted(folder.glob("*.json"))}


def main() -> None:
    extractions = load_extractions()
    if not extractions:
        print("no stored readings yet: run infra/run_receipts.py --steps extract first")
        return
    result = score(extractions)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_document"}, indent=2, default=str))


if __name__ == "__main__":
    main()
