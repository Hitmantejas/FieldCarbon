"""Delivery-note images for the fleet's fuel deliveries, so Gemini can read the paper behind the fuel log.

Writes to data/fleet/delivery_notes/:
  receipts/DN-*.jpg              one image per paper delivery note (the log's duplicate row has no second paper)
  ground_truth_documents.csv     what each note says (same schema as Farm B, for scoring the reading)
  ground_truth_lines.csv
  ground_truth_checks.csv        the planted paper-vs-log difference, for scoring the document check
and four demo notes for the live upload (F7): images to frontend/public/demo-notes/, ground truth and expected
verdicts to data/fleet/delivery_notes/demo/.

Source: data/fleet/fuel_deliveries.csv (synthetic, tied to real consumption). The notes print what the log
says, except one planted keying error: the log's unit price has two digits swapped against the note.
Synthetic and labelled illustrative. Run: python data/synthetic/generate_delivery_notes.py [--demo-only]
"""
from __future__ import annotations

import random
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

import generate_farm_b as farm_b

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "data" / "fleet"
OUT = FLEET / "delivery_notes"
SEED = 20261014
CUSTOMER = "FieldCarbon demo contractor"
# Planted: the note says 0.7427 GBP/L; the log was keyed as 0.7472 (two digits swapped).
PRICE_TYPO_DOC = "DN-S1-0004"
REDUCED_RATE_MAX_L = 2300  # VAT Notice 701/19 para 6.1.1; larger supplies shown at the standard rate (illustrative)

# Live upload demo (F7): (image name, real note it copies, note number printed, extra litres, expected verdict, finding).
DEMO_OUT = OUT / "demo"
DEMO_IMAGES = ROOT / "frontend" / "public" / "demo-notes"
DEMO_NOTES = [("matches", "DN-S1-0001", "DN-S1-0001", 0.0, "matches_log", ""),
              ("litres-differ", "DN-S1-0002", "DN-S1-0002", 300.0, "needs_attention", "litres_differ"),
              ("price-differs", PRICE_TYPO_DOC, PRICE_TYPO_DOC, 0.0, "needs_attention", "price_differs"),
              ("not-in-log", "DN-S1-0003", "DN-S1-0042", 0.0, "needs_attention", "note_not_in_log")]
DEMO_CHANGES = {"matches": "none: a second copy of a logged note",
                "litres-differ": "300 litres more than the log, net, VAT and total printed to match",
                "price-differs": "none: the planted note whose price was keyed into the log with two digits swapped",
                "not-in-log": "a note number that is not in the fuel log"}


def paper_price(doc_no: str, logged: float) -> float:
    if doc_no != PRICE_TYPO_DOC:
        return logged
    s = f"{logged:.4f}"  # 0.7472 -> 0.7427: the last two digits swapped
    return float(s[:-2] + s[-1] + s[-2])


def build(seed: int = SEED) -> tuple[list[farm_b.Document], list[farm_b.Line], pd.DataFrame, dict[str, str]]:
    rng = random.Random(seed)
    log = pd.read_csv(FLEET / "fuel_deliveries.csv", parse_dates=["ts"])
    sites = pd.read_csv(FLEET / "sites.csv").set_index("site_id").name
    depots = pd.read_csv(FLEET / "depots.csv").set_index("depot_id").site_id
    papers = log.drop_duplicates(["depot_id", "supplier", "doc_no"])  # one paper per note, however often keyed
    docs, lines, addresses = [], [], {}
    for r in papers.itertuples():
        price = paper_price(r.doc_no, r.unit_price_gbp)
        line = farm_b.Line(r.doc_no, 1, farm_b.DIESEL, float(r.litres), price, round(r.litres * price, 2), True)
        vat_rate = farm_b.VAT_RATE if r.litres <= REDUCED_RATE_MAX_L else 0.20
        vat = round(line.net_gbp * vat_rate, 2)
        docs.append(farm_b.Document(r.doc_no, "delivery_note", r.supplier, r.doc_no, r.ts.date().isoformat(),
                                    r.ts.strftime("%Y-%m"), line.net_gbp, vat_rate, vat, round(line.net_gbp + vat, 2),
                                    rng.choice(farm_b.DAMAGE), "", True))
        lines.append(line)
        addresses[r.doc_no] = f"{sites[depots[r.depot_id]]} depot {r.depot_id}"
    logged = log[log.doc_no == PRICE_TYPO_DOC].iloc[0]
    checks = pd.DataFrame([{"doc_no": PRICE_TYPO_DOC, "kind": "price_differs", "field": "unit_price_gbp",
                            "on_note": paper_price(PRICE_TYPO_DOC, logged.unit_price_gbp),
                            "in_log": logged.unit_price_gbp, "label": "planted"}])
    return docs, lines, checks, addresses


def build_demo(docs: list[farm_b.Document], lines: list[farm_b.Line]) -> tuple[list[farm_b.Document], list[farm_b.Line], pd.DataFrame]:
    """The four demo notes for the live upload: copies of real notes, printed clean, one change each (or none).
    Each has its own note number, so scoring them together never flags one as a re-photographed copy of another."""
    by_doc = {d.doc_id: (d, next(l for l in lines if l.doc_id == d.doc_id)) for d in docs}
    out_docs, out_lines, expected = [], [], []
    for name, base, doc_no, extra_l, verdict, kind in DEMO_NOTES:
        d, l = by_doc[base]
        litres = l.litres + extra_l
        line = farm_b.Line(name, 1, l.product, litres, l.unit_price_gbp, round(litres * l.unit_price_gbp, 2), True)
        vat = round(line.net_gbp * d.vat_rate, 2)
        out_docs.append(farm_b.Document(name, "delivery_note", d.supplier, doc_no, d.date, d.price_month, line.net_gbp, d.vat_rate,
                                        vat, round(line.net_gbp + vat, 2), "clean", "", True))
        out_lines.append(line)
        expected.append({"note": name, "based_on": base, "doc_number": doc_no, "change": DEMO_CHANGES[name],
                         "expected_verdict": verdict, "expected_finding": kind})
    return out_docs, out_lines, pd.DataFrame(expected)


def main(demo_only: bool = False) -> None:
    docs, lines, checks, addresses = build()
    if not demo_only:
        (OUT / "receipts").mkdir(parents=True, exist_ok=True)
        pd.DataFrame([asdict(d) for d in docs]).to_csv(OUT / "ground_truth_documents.csv", index=False)
        pd.DataFrame([asdict(l) for l in lines]).to_csv(OUT / "ground_truth_lines.csv", index=False)
        checks.to_csv(OUT / "ground_truth_checks.csv", index=False)
        for d in docs:
            farm_b.render(d, lines, seed=SEED, customer=CUSTOMER, delivered_to=addresses[d.doc_id]).save(
                OUT / "receipts" / f"{d.doc_id}.jpg", quality=78, optimize=True)
        print(f"{len(docs)} delivery notes; planted: {PRICE_TYPO_DOC} price on note {checks.on_note.iloc[0]} "
              f"vs log {checks.in_log.iloc[0]}")
    demo_docs, demo_lines, expected = build_demo(docs, lines)
    DEMO_OUT.mkdir(parents=True, exist_ok=True)
    DEMO_IMAGES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(d) for d in demo_docs]).to_csv(DEMO_OUT / "ground_truth_documents.csv", index=False)
    pd.DataFrame([asdict(l) for l in demo_lines]).to_csv(DEMO_OUT / "ground_truth_lines.csv", index=False)
    expected.to_csv(DEMO_OUT / "expected_verdicts.csv", index=False)
    for d in demo_docs:
        base = expected.set_index("note").based_on[d.doc_id]
        farm_b.render(d, demo_lines, seed=SEED, customer=CUSTOMER, delivered_to=addresses[base]).save(
            DEMO_IMAGES / f"{d.doc_id}.jpg", quality=82, optimize=True)
    print(f"{len(demo_docs)} demo notes for the live upload -> {DEMO_IMAGES.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main(demo_only="--demo-only" in sys.argv)
