"""Ground truth of the synthetic fuel documents: what each image says.

Used to score Gemini's readings, and as a clearly labelled stand-in until Gemini has read the images."""
import pandas as pd

from backend.tools.extract_receipt import FARM_RECEIPTS

DOC_TYPES = {"delivery_note": "delivery_note", "merchant_till": "till_receipt", "handwritten": "handwritten_docket"}


def ground_truth(farm: str = "b") -> tuple[pd.DataFrame, pd.DataFrame]:
    folder = FARM_RECEIPTS[farm]
    docs = pd.read_csv(folder / "ground_truth_documents.csv", keep_default_na=False)
    lines = pd.read_csv(folder / "ground_truth_lines.csv")
    return docs, lines


def ground_truth_extractions(farm: str = "b") -> dict[str, dict]:
    """What a perfect reading of each image would return (scoring baseline; stand-in until Gemini has read them)."""
    docs, lines = ground_truth(farm)
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
