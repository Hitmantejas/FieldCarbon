"""Farm B: the same real farm as Farm A, seen through fuel receipts and a farm profile only (Tier 3).

Writes to data/synthetic/farm_b/:
  farm_b_profile.csv            fields, worked area and operations, as a farmer would state them (no fuel, no coordinates)
  farm_b_machines.csv           tractors and rated power
  ground_truth_documents.csv    one row per receipt image
  ground_truth_lines.csv        one row per line item
  receipts/*.jpg                the receipt images (synthetic; the only synthetic data in FieldCarbon)

Real inputs: Farm A's measured total litres (TUM telemetry) and Defra UKAMMG monthly red-diesel prices.
Invented: how the litres split into deliveries, dates within each month, suppliers, layouts, damage.
Deterministic for a given SEED. The profile never uses fuel, so Tier 3 estimates are not circular.

Run: python data/synthetic/generate_farm_b.py            (plan + profile + images)
     python data/synthetic/generate_farm_b.py --no-images
"""
from __future__ import annotations

import argparse
import calendar
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AGG = ROOT / "data" / "aggregated"
REF = ROOT / "data" / "reference"
OUT = ROOT / "data" / "synthetic" / "farm_b"
FONTS = Path("C:/Windows/Fonts")  # fonts are used at generation time only, never committed

SEED = 20261012
FARM_NAME = "Farm B (demo)"
DIESEL = "Red diesel (gas oil)"
ADBLUE = "AdBlue"
# VAT Notice 701/19 para 6.1.1: gas oil supplies of 2,300 L or less take the reduced rate regardless of use.
# Every generated diesel supply stays under that limit. Illustrative only, not tax advice.
VAT_RATE = 0.05
MAX_SUPPLY_L = 2300
ADBLUE_PRICE = 0.85  # GBP/L, invented: AdBlue is not fuel and never counts toward litres
FOOTER = "ILLUSTRATIVE DEMO DATA - fictional supplier - FieldCarbon"
MIN_PROFILE_HA = 0.5  # field-operation pairs below this are passes through a field, not work on it

# Fictional suppliers (no real companies). Prefix is used for document numbers.
SUPPLIERS = {
    "delivery_note": [("Larkspur Vale Fuels Ltd", "LVF"), ("Corrow & Pike Oils", "CPO")],
    "merchant_till": [("Fenmarsh Agri Supplies", "FAS")],
    "handwritten": [("Hob Lane Fuel Services", "HL")],
}
# Relative fuel demand per month (autumn tillage and drilling, spring work, harvest stubble).
# July has no Defra price in ref_fuel_prices.csv, so no deliveries are dated in July.
MONTH_WEIGHT = {"2025-09": 3, "2025-10": 3, "2025-11": 1, "2025-12": 0.5, "2026-01": 0.5, "2026-02": 1,
                "2026-03": 2, "2026-04": 2, "2026-05": 1.5, "2026-06": 1, "2026-08": 2}
# (document type, count, litres low, high, decimals shown on the document)
MIX = [("delivery_note", 12, 400, 1500, 1), ("handwritten", 6, 200, 900, 0), ("merchant_till", 5, 20, 200, 2)]
DAMAGE = ["clean", "skewed", "blurred", "low_light", "crumpled"]
# Decimals of GBP/L each document prints (pence to 2 dp, GBP to 3 dp, pence to 1 dp): the ground truth
# uses the printed price so litres x price = net holds on the paper itself.
PRICE_DP = {"delivery_note": 4, "merchant_till": 3, "handwritten": 3}


@dataclass(frozen=True)
class Line:
    doc_id: str
    line_no: int
    product: str
    litres: float
    unit_price_gbp: float
    net_gbp: float
    counts_toward_fuel: bool


@dataclass(frozen=True)
class Document:
    doc_id: str
    doc_type: str
    supplier: str
    doc_number: str
    date: str
    price_month: str
    net_gbp: float
    vat_rate: float
    vat_gbp: float
    total_gbp: float
    damage: str
    duplicate_of: str  # "" for originals; a re-photographed copy must not be counted twice
    counts_toward_total: bool


# ------------------------------------------------------------------------------------------- data

def farm_a_total_litres() -> float:
    return float(pd.read_csv(AGG / "farm_a_operations_summary.csv").litres.sum())


def monthly_prices() -> dict[str, float]:
    p = pd.read_csv(REF / "ref_fuel_prices.csv")
    p = p[p.fuel_type == "gas_oil"]
    return dict(zip(p.price_month.str[:7], p.price_per_litre.astype(float)))


def _split(total: float, rng: random.Random) -> list[tuple[str, float, int]]:
    """Draw litres per document by type, then scale so the shown litres add up exactly to `total` (0.1 L)."""
    raw = [(kind, rng.uniform(lo, hi), dec) for kind, n, lo, hi, dec in MIX for _ in range(n)]
    scale = total / sum(l for _, l, _ in raw)
    docs = [(kind, round(l * scale, dec), dec) for kind, l, dec in raw]
    # Rounding remainder, in hundredths of a litre, so the documents add up to round(total, 1) exactly:
    # whole tenths go to the largest delivery note (shown to 0.1 L), the rest to the largest till receipt (0.01 L).
    remainder = round(round(total, 1) * 100) - sum(round(d[1] * 100) for d in docs)
    for kind, share in (("delivery_note", 10 * (remainder // 10)), ("merchant_till", remainder % 10)):
        i = max((j for j, d in enumerate(docs) if d[0] == kind), key=lambda j: docs[j][1])
        docs[i] = (kind, (round(docs[i][1] * 100) + share) / 100, docs[i][2])
    if any(l > MAX_SUPPLY_L or l <= 0 for _, l, _ in docs):
        raise ValueError("a supply fell outside 0-2,300 L; change SEED or MIX")
    return docs


def plan(seed: int = SEED) -> tuple[list[Document], list[Line]]:
    rng = random.Random(seed)
    prices = monthly_prices()
    months = [m for m in MONTH_WEIGHT if m in prices]
    docs, lines = [], []
    counters = {prefix: rng.randint(1000, 8000) for group in SUPPLIERS.values() for _, prefix in group}
    split = _split(farm_a_total_litres(), rng)
    rng.shuffle(split)
    dated = []
    for s in split:
        month = rng.choices(months, weights=[MONTH_WEIGHT[m] for m in months])[0]
        y, m = map(int, month.split("-"))
        dated.append((f"{month}-{rng.randint(1, calendar.monthrange(y, m)[1]):02d}", month, s))
    dated.sort(key=lambda x: x[0])  # document numbers then rise with the date, as on real paperwork
    adblue_doc = next(i for i, (_, _, s) in enumerate(dated) if s[0] == "merchant_till")
    for i, (date, month, (kind, litres, _dec)) in enumerate(dated, 1):
        doc_id = f"B{i:02d}"
        supplier, prefix = rng.choice(SUPPLIERS[kind])
        counters[prefix] += rng.randint(3, 40)
        unit = round(prices[month] * rng.uniform(0.97, 1.03), PRICE_DP[kind])  # spread around the Defra average
        doc_lines = [Line(doc_id, 1, DIESEL, litres, unit, round(litres * unit, 2), True)]
        if i - 1 == adblue_doc:  # trap: a non-fuel line on the same receipt
            doc_lines.append(Line(doc_id, 2, ADBLUE, 20.0, ADBLUE_PRICE, round(20.0 * ADBLUE_PRICE, 2), False))
        net = round(sum(l.net_gbp for l in doc_lines), 2)
        vat = round(net * VAT_RATE, 2)
        damage = "handwritten" if kind == "handwritten" else rng.choice(DAMAGE)
        docs.append(Document(doc_id, kind, supplier, f"{prefix}-{counters[prefix]}", date, month, net, VAT_RATE, vat, round(net + vat, 2), damage, "", True))
        lines.extend(doc_lines)
    # Trap: the largest delivery note photographed a second time, more damaged.
    original = max((d for d in docs if d.doc_type == "delivery_note"),
                   key=lambda d: next(l.litres for l in lines if l.doc_id == d.doc_id))
    dup_id = f"B{len(docs) + 1:02d}"
    docs.append(Document(**{**asdict(original), "doc_id": dup_id, "damage": "blurred",
                            "duplicate_of": original.doc_id, "counts_toward_total": False}))
    lines.extend(Line(**{**asdict(l), "doc_id": dup_id, "counts_toward_fuel": False})
                 for l in lines if l.doc_id == original.doc_id)
    return docs, lines


def profile() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fields and worked area per operation as a farmer would state them, derived from Farm A's
    GPS distance x implement width (never from fuel). Area is capped at the field outline."""
    s = pd.read_csv(AGG / "farm_a_operations_summary.csv")
    fields = pd.read_csv(AGG / "farm_a_fields.csv").set_index("field_id").hull_area_ha
    ff = pd.read_csv(AGG / "farm_a_field_files.csv")
    width = ff.groupby(["tractor_id", "operation_code"]).implement_width_m.median()
    width_any = ff.groupby("operation_code").implement_width_m.median()
    work = s[(s.activity_class == "field_work") & s.field_id.notna() & s.operation_code.notna()
             & (s.operation_code != "transport")].copy()
    work["width_m"] = [width.get((t, o), width_any.get(o)) for t, o in zip(work.tractor_id, work.operation_code)]
    work["area"] = work.distance_km * work.width_m / 10  # km x m / 10 = ha
    pairs = work.groupby(["field_id", "operation_code"]).area.sum().reset_index()
    pairs["area_ha"] = np.minimum(pairs.area, pairs.field_id.map(fields)).round(1)
    pairs = pairs[pairs.area_ha >= MIN_PROFILE_HA]
    pairs["field_area_ha"] = pairs.field_id.map(fields).round(1)
    pairs["label"] = "user-provided"
    prof = pairs[["field_id", "field_area_ha", "operation_code", "area_ha", "label"]].sort_values(
        ["field_id", "operation_code"]).reset_index(drop=True)
    kw = {"tractor_1": 77, "tractor_2": 104, "tractor_3": 140, "tractor_4": 163, "tractor_5": 174}
    machines = pd.DataFrame([{"machine_id": t, "name": f"Tractor {t[-1]}, {k} kW", "rated_kw": k,
                              "fuel_type": "gas_oil", "label": "user-provided"} for t, k in kw.items()])
    return prof, machines


# -------------------------------------------------------------------------------------- rendering

def _font(name: str, size: int):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONTS / name), size)


def _hand(draw, xy, text, rng, size=34):
    """Handwriting: a script font with per-character wobble."""
    x, y = xy
    font = _font(rng.choice(["Inkfree.ttf", "segoepr.ttf"]), size)
    for ch in text:
        draw.text((x, y + rng.uniform(-2.5, 2.5)), ch, font=font, fill=(25, 35, 110))
        x += draw.textlength(ch, font=font) + rng.uniform(-0.5, 1.5)


def _money(v: float) -> str:
    return f"{v:,.2f}"


def _render_delivery_note(doc: Document, lines: list[Line], rng: random.Random):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (900, 1180), (252, 252, 248))
    d = ImageDraw.Draw(img)
    big, bold, reg, small = _font("arialbd.ttf", 34), _font("arialbd.ttf", 22), _font("arial.ttf", 22), _font("arial.ttf", 16)
    d.rectangle([40, 40, 860, 130], outline=(30, 30, 30), width=3)
    d.text((60, 55), doc.supplier, font=big, fill=(20, 20, 20))
    d.text((60, 98), "Bulk fuel deliveries - Unit 4, Mill Lane, Fenmarsh", font=small, fill=(60, 60, 60))
    d.text((60, 160), "DELIVERY NOTE / INVOICE", font=bold, fill=(20, 20, 20))
    meta = [("Document no.", doc.doc_number), ("Date", doc.date), ("Customer", FARM_NAME),
            ("Delivered to", "Farm yard tank")]
    for i, (k, v) in enumerate(meta):
        d.text((60, 210 + i * 38), k, font=reg, fill=(70, 70, 70))
        d.text((300, 210 + i * 38), v, font=bold, fill=(20, 20, 20))
    y = 400
    d.line([60, y, 840, y], fill=(30, 30, 30), width=2)
    for x, h in [(60, "Product"), (420, "Litres"), (560, "p/litre"), (700, "Net GBP")]:
        d.text((x, y + 10), h, font=bold, fill=(20, 20, 20))
    y += 50
    for l in lines:
        d.text((60, y), l.product, font=reg, fill=(20, 20, 20))
        d.text((420, y), f"{l.litres:,.1f}", font=reg, fill=(20, 20, 20))
        d.text((560, y), f"{100 * l.unit_price_gbp:.2f}", font=reg, fill=(20, 20, 20))
        d.text((700, y), _money(l.net_gbp), font=reg, fill=(20, 20, 20))
        y += 40
    d.line([60, y + 10, 840, y + 10], fill=(30, 30, 30), width=2)
    for i, (k, v) in enumerate([("Net", doc.net_gbp), (f"VAT {100 * doc.vat_rate:g}%", doc.vat_gbp),
                                ("TOTAL GBP", doc.total_gbp)]):
        d.text((480, y + 30 + i * 40), k, font=bold if k.startswith("TOTAL") else reg, fill=(20, 20, 20))
        d.text((700, y + 30 + i * 40), _money(v), font=bold if k.startswith("TOTAL") else reg, fill=(20, 20, 20))
    d.text((60, 1000), "Rebated gas oil. Not for use as road fuel.", font=small, fill=(60, 60, 60))
    d.text((60, 1030), f"Meter ticket {rng.randint(10000, 99999)}   Driver signature: ________", font=small,
           fill=(60, 60, 60))
    d.text((60, 1130), FOOTER, font=small, fill=(120, 120, 120))
    return img


def _render_till(doc: Document, lines: list[Line], rng: random.Random):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (520, 900), (246, 246, 242))
    d = ImageDraw.Draw(img)
    mono, monob, small = _font("consola.ttf", 22), _font("consola.ttf", 26), _font("consola.ttf", 15)
    y = 30
    for text, f in [(doc.supplier.upper(), monob), ("Farm store - Fenmarsh", mono), ("", mono),
                    (f"{doc.date}  {rng.randint(7, 17):02d}:{rng.randint(0, 59):02d}", mono),
                    (f"Receipt {doc.doc_number}", mono), ("-" * 34, mono)]:
        d.text((30, y), text, font=f, fill=(40, 40, 40))
        y += 34
    for l in lines:
        d.text((30, y), l.product[:24], font=mono, fill=(40, 40, 40))
        d.text((360, y), f"{l.net_gbp:>8.2f}", font=mono, fill=(40, 40, 40))
        d.text((30, y + 30), f"  {l.litres:.2f} L @ {l.unit_price_gbp:.3f}", font=mono, fill=(40, 40, 40))
        y += 70
    for text in ["-" * 34, f"NET{doc.net_gbp:>27.2f}", f"VAT {100 * doc.vat_rate:g}%{doc.vat_gbp:>23.2f}",
                 f"TOTAL GBP{doc.total_gbp:>21.2f}", "", "CARD   ****"]:
        d.text((30, y), text, font=monob if text.startswith("TOTAL") else mono, fill=(40, 40, 40))
        y += 34
    d.text((30, 860), FOOTER, font=small, fill=(120, 120, 120))
    return img


def _render_handwritten(doc: Document, lines: list[Line], rng: random.Random):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (900, 760), (250, 244, 214))  # carbon-copy docket
    d = ImageDraw.Draw(img)
    bold, reg, small = _font("arialbd.ttf", 26), _font("arial.ttf", 20), _font("arial.ttf", 15)
    d.text((40, 30), doc.supplier, font=bold, fill=(150, 40, 40))
    d.text((40, 66), "Fuel docket - customer copy", font=reg, fill=(150, 40, 40))
    d.text((680, 34), f"No. {doc.doc_number.split('-')[1]}", font=bold, fill=(150, 40, 40))
    labels = [("Date", 140), ("Customer", 210), ("Product", 280), ("Litres", 350), ("Price per litre", 420),
              ("Net", 490), (f"VAT {100 * doc.vat_rate:g}%", 560), ("Total", 630)]
    for text, y in labels:
        d.text((40, y), text, font=reg, fill=(150, 40, 40))
        d.line([260, y + 30, 820, y + 30], fill=(190, 120, 120), width=1)
    l = lines[0]
    y0, mo, da = doc.date.split("-")
    values = [f"{da}/{mo}/{y0[2:]}", FARM_NAME, "Red diesel", f"{l.litres:,.0f}", f"{100 * l.unit_price_gbp:.1f}p",
              f"£{doc.net_gbp:,.2f}", f"£{doc.vat_gbp:,.2f}", f"£{doc.total_gbp:,.2f}"]
    for (_, y), v in zip(labels, values):
        _hand(d, (280 + rng.uniform(-8, 8), y - 8), v, rng)
    d.text((40, 730), FOOTER, font=small, fill=(150, 120, 110))
    return img


def _photograph(img, damage: str, rng: random.Random):
    """Place the document on a table and apply the damage a phone photo would show."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    nr = np.random.default_rng(rng.randint(0, 2**31))
    if damage == "crumpled":
        shade = Image.new("L", img.size, 0)
        d = ImageDraw.Draw(shade)
        for _ in range(9):
            x0, y0 = rng.randint(0, img.width), rng.randint(0, img.height)
            d.line([x0, y0, x0 + rng.randint(-600, 600), y0 + rng.randint(-600, 600)], fill=70, width=rng.randint(2, 5))
        shade = shade.filter(ImageFilter.GaussianBlur(6))
        img = Image.composite(Image.new("RGB", img.size, (150, 150, 140)), img, shade)
    table = Image.new("RGB", (img.width + 160, img.height + 160), (96, 78, 60))
    angle = {"skewed": rng.uniform(4, 9) * rng.choice([-1, 1])}.get(damage, rng.uniform(-1.5, 1.5))
    rotated = img.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(96, 78, 60))
    table = table.resize((rotated.width + 120, rotated.height + 120))
    table.paste(rotated, (60, 60))
    img = table
    if damage == "blurred":
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(1.8, 2.6)))
    if damage == "low_light":
        img = ImageEnhance.Brightness(img).enhance(0.5)
        img = ImageEnhance.Contrast(img).enhance(0.75)
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    vignette = 1 - 0.25 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / 2
    arr = arr * vignette[..., None] + nr.normal(0, 4 if damage == "clean" else 7, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


RENDERERS = {"delivery_note": _render_delivery_note, "merchant_till": _render_till,
             "handwritten": _render_handwritten}


def render(doc: Document, lines: list[Line], seed: int = SEED):
    rng = random.Random(f"{seed}-{doc.doc_id}")
    img = RENDERERS[doc.doc_type](doc, [l for l in lines if l.doc_id == doc.doc_id], rng)
    img = _photograph(img, doc.damage, rng)
    scale = 1000 / max(img.size)  # keep the committed images small
    return img.resize((math.floor(img.width * scale), math.floor(img.height * scale)))


# ------------------------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-images", action="store_true", help="write the CSVs only")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    docs, lines = plan()
    pd.DataFrame([asdict(d) for d in docs]).to_csv(OUT / "ground_truth_documents.csv", index=False)
    pd.DataFrame([asdict(l) for l in lines]).to_csv(OUT / "ground_truth_lines.csv", index=False)
    prof, machines = profile()
    prof.to_csv(OUT / "farm_b_profile.csv", index=False)
    machines.to_csv(OUT / "farm_b_machines.csv", index=False)
    if not args.no_images:
        (OUT / "receipts").mkdir(exist_ok=True)
        for d in docs:
            render(d, lines).save(OUT / "receipts" / f"{d.doc_id}.jpg", quality=78, optimize=True)
    fuel = round(sum(l.litres for l in lines if l.counts_toward_fuel), 2)
    print(f"{len(docs)} documents, {len(lines)} lines, counted diesel {fuel:,.1f} L "
          f"(Farm A measured {farm_a_total_litres():,.2f} L); profile {len(prof)} field-operation rows")


if __name__ == "__main__":
    main()
