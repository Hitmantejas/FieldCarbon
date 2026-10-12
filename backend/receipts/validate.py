"""Receipt validation rules R1-R8 (docs/receipt_validation_rules.md): raw extraction -> validated lines.

Deterministic. Gemini only transcribes; these rules decide what counts toward a farm's litres,
and every decision carries its reasons. Pure functions: no GCP, no model calls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

REF = Path(__file__).resolve().parents[2] / "data" / "reference"
RULES_VERSION = "rules-v1"

MAX_SUPPLY_L = 2300            # one supply: one delivery, one site, one day (VAT Notice 701/19 para 6.1.1)
MONEY_TOL_GBP = 0.02
LINE_TOL_SHARE = 0.005         # 0.5% of the line net, for prices printed to fewer decimals
PRICE_BAND_SLACK = 0.15        # supplier and volume spread around the Defra min-max

OUTCOMES = ("accepted", "accepted_with_warning", "needs_review", "excluded")  # weakest to strongest
COUNTED = {"accepted", "accepted_with_warning"}

# Product text -> fuel type in ref_emission_factors; order matters (red diesel before plain diesel).
FUEL_PATTERNS = [
    (r"\b(red diesel|gas ?oil|rebated)\b", "gas_oil"),
    (r"\b(hvo|renewable diesel|hydrotreated)\b", "hvo"),
    (r"\b(diesel|derv)\b", "diesel_blend"),
]
NOT_FUEL = r"\b(adblue|ad blue|def|urea|engine oil|hydraulic|lubricant|grease|filter|antifreeze|coolant)\b"


@dataclass(frozen=True)
class Settings:
    season_start: date
    season_end: date
    price_low: float   # GBP/L, Defra min over the season
    price_high: float  # GBP/L, Defra max over the season


@dataclass(frozen=True)
class ValidatedLine:
    receipt_id: str
    line_no: int
    farm_id: str
    supplier: str | None
    doc_number: str | None
    delivery_date: str | None
    product: str | None
    fuel_type: str | None
    litres: float | None
    unit_price_gbp: float | None  # normalised to GBP per litre
    line_net_gbp: float | None
    outcome: str
    reasons: tuple[str, ...]
    duplicate_of: str | None
    rules_version: str = RULES_VERSION

    @property
    def counts(self) -> bool:
        return self.outcome in COUNTED


@lru_cache(maxsize=1)
def default_settings() -> Settings:
    p = pd.read_csv(REF / "ref_fuel_prices.csv")
    p = p[p.fuel_type == "gas_oil"]
    months = pd.to_datetime(p.price_month)
    end = (months.max() + pd.offsets.MonthEnd(0)).date()
    return Settings(months.min().date(), end, float(p.price_per_litre.min()), float(p.price_per_litre.max()))


def fuel_type(product: str | None) -> str | None:
    """Fuel type for a product line, "" for a known non-fuel line, None when not recognised."""
    text = (product or "").lower()
    if re.search(NOT_FUEL, text):
        return ""
    return next((fuel for pattern, fuel in FUEL_PATTERNS if re.search(pattern, text)), None)


def _num(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _doc_key(x: dict) -> tuple[str, str] | None:
    """Supplier + document number digits; handwritten dockets often show only the number."""
    digits = re.sub(r"\D", "", str(x.get("doc_number") or ""))
    supplier = re.sub(r"[^a-z]", "", str(x.get("supplier") or "").lower())
    return (supplier, digits) if digits and supplier else None


def _unit_price(line: dict) -> tuple[float | None, str | None]:
    """GBP per litre. With no stated unit, keep whichever reading matches the line arithmetic."""
    price, unit = _num(line.get("unit_price")), line.get("unit_price_unit")
    if price is None:
        return None, None
    if unit == "GBP_per_litre":
        return price, None
    if unit == "pence_per_litre":
        return price / 100, None
    litres, net = _num(line.get("litres")), _num(line.get("line_net"))
    if litres and net:
        for candidate in (price, price / 100):
            if _line_matches(litres, candidate, net):
                return candidate, "price unit not stated; read from the line arithmetic"
    return None, "price unit not stated and could not be inferred"


def _line_matches(litres: float, price: float, net: float) -> bool:
    return abs(litres * price - net) <= max(MONEY_TOL_GBP, LINE_TOL_SHARE * net)


def _parse_date(text) -> date | None:
    try:
        return date.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def _doc_checks(x: dict, s: Settings) -> tuple[list[str], list[str]]:
    """(review reasons, warnings) that apply to every line of a document: R5, R6, R8."""
    review, warn = [], []
    lines = x.get("lines") or []
    net, vat, total = _num(x.get("net")), _num(x.get("vat")), _num(x.get("total"))
    nets = [_num(l.get("line_net")) for l in lines]
    if net is None or total is None or None in nets:
        warn.append("R5: document totals incomplete, could not cross-check")
    else:
        if abs(sum(nets) - net) > MONEY_TOL_GBP:
            review.append("R5: line nets do not add up to the net")
        if abs(net + (vat or 0.0) - total) > MONEY_TOL_GBP:
            review.append("R5: net + VAT does not equal the total")
    d = _parse_date(x.get("date"))
    if d is None:
        review.append("R6: date missing or unreadable")
    elif not s.season_start <= d <= s.season_end:
        review.append(f"R6: date {d} outside the season {s.season_start} to {s.season_end}")
    low = [k for k, v in (x.get("confidence") or {}).items() if k in ("litres", "product", "date") and v == "low"]
    if low:
        review.append(f"R8: low reading confidence on {', '.join(sorted(low))}")
    return review, warn


def _line(rid: str, farm_id: str, x: dict, no: int, line: dict, s: Settings,
          doc_review: list[str], doc_warn: list[str]) -> ValidatedLine:
    product = line.get("product")
    fuel = fuel_type(product)
    litres = _num(line.get("litres"))
    price, price_note = _unit_price(line)
    net = _num(line.get("line_net"))
    common = dict(receipt_id=rid, line_no=no, farm_id=farm_id, supplier=x.get("supplier"),
                  doc_number=x.get("doc_number"), delivery_date=x.get("date"), product=product,
                  fuel_type=fuel or None, litres=litres, unit_price_gbp=price, line_net_gbp=net, duplicate_of=None)
    if fuel == "":
        return ValidatedLine(outcome="excluded", reasons=("R1: not engine fuel",), **common)
    review, warn = list(doc_review), list(doc_warn)
    if fuel is None:
        review.append("R1: product not recognised as a fuel")
    if line.get("quantity_unit") not in (None, "litres"):
        review.append(f"R3: quantity in {line.get('quantity_unit')}, only litres are supported")
    if litres is None or not 0 < litres <= MAX_SUPPLY_L:
        review.append(f"R3: litres missing or outside 0 to {MAX_SUPPLY_L:,} L")
    if price_note:
        (warn if price is not None else review).append(f"R4: {price_note}")
    if litres and price is not None and net is not None:
        if not _line_matches(litres, price, net):
            review.append("R4: litres x unit price does not match the line net (possible misread)")
    elif price_note is None:
        warn.append("R4: price or line net missing, could not cross-check")
    if fuel == "gas_oil" and price is not None:
        lo, hi = s.price_low * (1 - PRICE_BAND_SLACK), s.price_high * (1 + PRICE_BAND_SLACK)
        if not lo <= price <= hi:
            warn.append(f"R7: unit price GBP {price:.3f}/L outside the expected GBP {lo:.3f}-{hi:.3f}/L")
    outcome = "needs_review" if review else "accepted_with_warning" if warn else "accepted"
    return ValidatedLine(outcome=outcome, reasons=tuple(review + warn), **common)


def validate(extractions: list[tuple[str, dict]], farm_id: str, settings: Settings | None = None,
             seen: dict | None = None) -> list[ValidatedLine]:
    """Validate receipts in order. `seen` maps document keys to (receipt_id, date, total) of documents
    validated earlier, so a re-photographed receipt is caught across batches too (R2)."""
    s = settings or default_settings()
    seen = {} if seen is None else seen
    out: list[ValidatedLine] = []
    for rid, x in extractions:
        key = _doc_key(x)
        earlier = seen.get(key) if key else None
        if earlier and (earlier[1], earlier[2]) == (x.get("date"), _num(x.get("total"))):
            out.extend(ValidatedLine(rid, no, farm_id, x.get("supplier"), x.get("doc_number"), x.get("date"),
                                     l.get("product"), fuel_type(l.get("product")) or None, _num(l.get("litres")),
                                     None, _num(l.get("line_net")), "excluded",
                                     (f"R2: duplicate of {earlier[0]}",), earlier[0])
                       for no, l in enumerate(x.get("lines") or [], 1))
            continue
        doc_review, doc_warn = _doc_checks(x, s)
        if earlier:
            doc_review.append(f"R2: document number already used by {earlier[0]} with different details")
        elif key:
            seen[key] = (rid, x.get("date"), _num(x.get("total")))
        if not x.get("lines"):
            out.append(ValidatedLine(rid, 0, farm_id, x.get("supplier"), x.get("doc_number"), x.get("date"),
                                     None, None, None, None, None, "needs_review",
                                     tuple(doc_review + ["R3: no product lines read"]), None))
        out.extend(_line(rid, farm_id, x, no, l, s, doc_review, doc_warn)
                   for no, l in enumerate(x.get("lines") or [], 1))
    return out


def counted_litres(lines: list[ValidatedLine]) -> float:
    return round(sum(l.litres for l in lines if l.counts and l.litres), 2)


def review_litres(lines: list[ValidatedLine]) -> float:
    """Litres held back for the farmer to confirm: reported separately, never silently dropped."""
    return round(sum(l.litres for l in lines if l.outcome == "needs_review" and l.litres), 2)
