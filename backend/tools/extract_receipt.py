"""Agent tool: read a fuel receipt image with Gemini (raw), then validate it with rules R1-R8.

Gemini transcribes only: no arithmetic, no decision about what counts. The raw extraction is kept
as provenance (model, prompt version, endpoint, time) and is reused when it already exists, so a
receipt is read once and every later figure traces back to the same stored reading.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.receipts.validate import ValidatedLine, counted_litres, default_settings, fleet_settings, validate

ROOT = Path(__file__).resolve().parents[2]
# Each source of fuel documents: a folder with receipts/*.jpg, ground truth and stored readings.
FARM_RECEIPTS = {"b": ROOT / "data" / "synthetic" / "farm_b", "fleet": ROOT / "data" / "fleet" / "delivery_notes"}
SETTINGS = {"b": default_settings, "fleet": fleet_settings}

PROJECT = os.environ.get("FIELDCARBON_PROJECT", "ai-hackathon-india")
MODEL = os.environ.get("FIELDCARBON_GEMINI_MODEL", "gemini-3.5-flash")
# Decided 2026-10-14: gemini-3.5-flash is offered on "global" (and "us"/"eu"), not on "us-central1".
LOCATION = os.environ.get("FIELDCARBON_GEMINI_LOCATION", "global")
PROMPT_VERSION = "receipt-v1"

PROMPT = """You are reading a photo of a fuel receipt, delivery note or handwritten fuel docket from a farm.
Transcribe exactly what is printed or written. Rules:
- Copy numbers as shown. Never calculate, correct or fill in a value that is not on the document.
- Use null for anything missing or unreadable.
- One entry in "lines" per product line (fuel, AdBlue, oil, anything else), in the order shown.
- Dates as YYYY-MM-DD (UK documents write day/month/year).
- unit_price_unit: "pence_per_litre" if the price is in pence (e.g. 77.27 p/litre, 73.0p),
  "GBP_per_litre" if in pounds (e.g. 0.756), null if you cannot tell.
- confidence: how sure you are of your reading of litres, product and date: high, medium or low.
- notes: anything unusual (damage, crossings-out, a second copy, a non-fuel item). Keep it short."""

_NUM = {"type": ["number", "null"]}
_STR = {"type": ["string", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "enum": ["delivery_note", "till_receipt", "handwritten_docket", "other"]},
        "supplier": _STR, "doc_number": _STR, "date": _STR, "currency": _STR,
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "product": _STR, "litres": _NUM,
            "quantity_unit": {"type": ["string", "null"], "enum": ["litres", "gallons", "other", None]},
            "unit_price": _NUM,
            "unit_price_unit": {"type": ["string", "null"], "enum": ["GBP_per_litre", "pence_per_litre", None]},
            "line_net": _NUM,
        }, "required": ["product", "litres", "quantity_unit", "unit_price", "unit_price_unit", "line_net"]}},
        "net": _NUM, "vat_rate_pct": _NUM, "vat": _NUM, "total": _NUM,
        "confidence": {"type": "object", "properties": {
            k: {"type": "string", "enum": ["high", "medium", "low"]} for k in ("litres", "product", "date")},
            "required": ["litres", "product", "date"]},
        "notes": _STR,
    },
    "required": ["doc_type", "supplier", "doc_number", "date", "lines", "net", "vat", "total", "confidence"],
}

Generate = Callable[[bytes, str], dict]  # (image bytes, mime type) -> extraction dict
META = "_vertex_meta"  # added by gemini_generate to the extraction, then moved onto RawExtraction


@dataclass(frozen=True)
class RawExtraction:
    receipt_id: str
    farm_id: str
    model_id: str
    location: str
    prompt_version: str
    extracted: dict
    extracted_at: str
    image: str  # path relative to the farm's receipt folder, e.g. receipts/B03.jpg
    # Token use reported by Vertex AI (input, output, thinking) and the model version that answered:
    # the basis for the cost of reading documents. None for readings stored before this was recorded.
    usage: dict | None = None
    model_version: str | None = None


def gemini_generate(model: str = MODEL, location: str = LOCATION, project: str = PROJECT) -> Generate:
    """Gemini on Vertex AI (ADC credentials, no keys). Imported lazily: tests never need the SDK."""
    def generate(image: bytes, mime: str) -> dict:
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=image, mime_type=mime), PROMPT],
            config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json",
                                               response_json_schema=SCHEMA),
        )
        u = response.usage_metadata
        meta = {"usage": {"input_tokens": u.prompt_token_count, "output_tokens": u.candidates_token_count,
                          "thinking_tokens": u.thoughts_token_count or 0, "total_tokens": u.total_token_count},
                "model_version": response.model_version}
        return {**json.loads(response.text), META: meta}
    return generate


def cache_path(farm_id: str, receipt_id: str) -> Path:
    return FARM_RECEIPTS[farm_id] / "extractions" / f"{receipt_id}.json"


def read_receipt(receipt_id: str, farm_id: str = "b", generate: Generate | None = None,
                 model: str = MODEL, location: str = LOCATION, refresh: bool = False) -> RawExtraction:
    """The stored raw extraction, or a new Gemini reading (stored) when there is none or `refresh`."""
    cached = cache_path(farm_id, receipt_id)
    if cached.exists() and not refresh:
        return RawExtraction(**json.loads(cached.read_text(encoding="utf-8")))
    image = FARM_RECEIPTS[farm_id] / "receipts" / f"{receipt_id}.jpg"
    extracted = dict((generate or gemini_generate(model, location))(image.read_bytes(), "image/jpeg"))
    meta = extracted.pop(META, {})
    raw = RawExtraction(receipt_id, farm_id, model, location, PROMPT_VERSION, extracted,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        image.relative_to(FARM_RECEIPTS[farm_id]).as_posix(), meta.get("usage"), meta.get("model_version"))
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(asdict(raw), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return raw


def validate_farm(farm_id: str = "b", receipt_ids: list[str] | None = None) -> list[ValidatedLine]:
    """Validate every stored extraction for a farm, in receipt order (duplicates are caught across them)."""
    folder = FARM_RECEIPTS[farm_id] / "extractions"
    ids = receipt_ids or sorted(p.stem for p in folder.glob("*.json"))
    return validate([(rid, read_receipt(rid, farm_id).extracted) for rid in ids], farm_id, SETTINGS[farm_id]())


def extract_receipt(receipt_id: str, farm_id: str = "b") -> dict:
    """Agent tool: what one receipt says (raw, as read by Gemini) and what counts (validated lines),
    checked against the farm's other receipts for duplicates. Litres only count when accepted."""
    if farm_id not in FARM_RECEIPTS:
        raise KeyError(f"unknown farm {farm_id}")
    raw = read_receipt(receipt_id, farm_id)
    folder = FARM_RECEIPTS[farm_id] / "extractions"
    earlier = sorted(p.stem for p in folder.glob("*.json") if p.stem < receipt_id)
    lines = [l for l in validate_farm(farm_id, earlier + [receipt_id]) if l.receipt_id == receipt_id]
    return {
        "receipt_id": receipt_id,
        "raw": asdict(raw),
        "lines": [{**asdict(l), "counts": l.counts} for l in lines],
        "counted_litres": counted_litres(lines),
        "note": "Read by Gemini, checked by fixed rules (docs/receipt_validation_rules.md). "
                "Only accepted lines count toward the farm's fuel.",
    }
