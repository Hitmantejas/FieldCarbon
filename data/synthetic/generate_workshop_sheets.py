"""Workshop job-sheet images for the fleet's maintenance log, so Gemini can read the paper behind it (P2b).

Writes to data/fleet/maintenance_sheets/:
  sheets/MNT-*.jpg              one photo of a workshop job sheet per logged event
  ground_truth.csv              what each sheet says, for scoring the reading
  ground_truth_checks.csv       the planted sheet-vs-log difference, for scoring the code check

Source: data/fleet/maintenance_events.csv (synthetic). The sheets print what the log says, except one planted keying
error: the log's hours at service have two digits swapped against the sheet. The machine is printed by its name and
site, never its id. The cost is illustrative only: parts and labour from the fixed price list below (invented, not a
market survey); it is printed on the sheets to test reading and never enters a fleet figure or the log.
Synthetic and labelled illustrative. Run: python data/synthetic/generate_workshop_sheets.py
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

import generate_farm_b as farm_b

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "data" / "fleet"
OUT = FLEET / "maintenance_sheets"
SEED = 20261017
WORKSHOP = "Workshop A (demo)"
# Planted: the sheet says 165.1 hours; the log was keyed as 156.1 (two digits swapped).
HOURS_TYPO_SHEET = "MNT-0022"

# Illustrative price list (invented): service type -> (parts GBP, labour hours). Labour at one invented hourly rate.
PRICE_LIST = {"Hydraulic hose replaced": (64.50, 1.5), "Tyre repair": (38.00, 1.0), "Brake adjustment": (12.00, 1.5),
              "Fuel filter replaced": (27.80, 0.5), "Air filter replaced": (46.20, 0.5), "Battery replaced": (148.00, 0.5)}
LABOUR_RATE_GBP = 58.00
HANDWRITTEN_SHARE = 1 / 3


def sheet_hours(sheet_id: str, logged: float) -> float:
    if sheet_id != HOURS_TYPO_SHEET:
        return logged
    s = f"{logged:.1f}"  # 156.1 -> 165.1: the last two digits before the decimal point swapped
    return float(s[:-4] + s[-3] + s[-4] + s[-2:])


def build(seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    log = pd.read_csv(FLEET / "maintenance_events.csv")
    machines = pd.read_csv(FLEET / "machines.csv").set_index("machine_id")
    sites = pd.read_csv(FLEET / "sites.csv").set_index("site_id").name
    rows = []
    for e in log.itertuples():
        parts, labour_h = PRICE_LIST[e.event_type]
        labour = round(labour_h * LABOUR_RATE_GBP, 2)
        m = machines.loc[e.machine_id]
        rows.append({"sheet_id": e.event_id, "sheet_number": e.event_id, "date": e.date, "machine_id": e.machine_id,
                     "machine_name": m.display_name, "site_name": sites[m.site_id], "service_type": e.event_type,
                     "hours_at_service": sheet_hours(e.event_id, round(float(e.job_hours_at_event), 1)),
                     "parts_gbp": parts, "labour_hours": labour_h, "labour_gbp": labour, "cost_gbp": round(parts + labour, 2),
                     "layout": "handwritten" if rng.random() < HANDWRITTEN_SHARE else "printed",
                     "damage": rng.choice(farm_b.DAMAGE)})
    truth = pd.DataFrame(rows)
    logged = round(float(log.set_index("event_id").job_hours_at_event[HOURS_TYPO_SHEET]), 1)
    checks = pd.DataFrame([{"sheet_id": HOURS_TYPO_SHEET, "kind": "differs", "field": "hours_at_service",
                            "on_sheet": sheet_hours(HOURS_TYPO_SHEET, logged), "in_log": logged, "label": "planted"}])
    return truth, checks


def render(r, seed: int = SEED):
    """A workshop job sheet: printed headings; in the handwritten layout the values are filled in by hand."""
    from PIL import Image, ImageDraw
    rng = random.Random(f"{seed}-{r.sheet_id}")
    img = Image.new("RGB", (900, 1000), (252, 252, 248) if r.layout == "printed" else (246, 242, 226))
    d = ImageDraw.Draw(img)
    big, bold, reg, small = (farm_b._font("arialbd.ttf", 32), farm_b._font("arialbd.ttf", 22),
                             farm_b._font("arial.ttf", 22), farm_b._font("arial.ttf", 16))
    d.rectangle([40, 40, 860, 125], outline=(30, 30, 30), width=3)
    d.text((60, 52), WORKSHOP, font=big, fill=(20, 20, 20))
    d.text((60, 94), "Tractor and machinery repairs - Yard 2, Fenmarsh", font=small, fill=(60, 60, 60))
    d.text((60, 155), "WORKSHOP JOB SHEET", font=bold, fill=(20, 20, 20))
    y0, mo, da = r.date.split("-")
    fields = [("Job sheet no.", r.sheet_number), ("Date", f"{da}/{mo}/{y0}"), ("Machine", r.machine_name),
              ("Site", r.site_name), ("Work done", r.service_type), ("Hours at service", f"{r.hours_at_service:.1f}"),
              ("Parts (GBP)", farm_b._money(r.parts_gbp)), (f"Labour {r.labour_hours:g} h (GBP)", farm_b._money(r.labour_gbp)),
              ("Total cost (GBP)", farm_b._money(r.cost_gbp))]
    hand = {"Date", "Hours at service", "Parts (GBP)", f"Labour {r.labour_hours:g} h (GBP)", "Total cost (GBP)"}
    for i, (k, v) in enumerate(fields):
        y = 210 + i * 70
        d.text((60, y), k, font=bold if k.startswith("Total") else reg, fill=(70, 70, 70))
        d.line([360, y + 32, 840, y + 32], fill=(170, 170, 170), width=1)
        if r.layout == "handwritten" and k in hand:
            farm_b._hand(d, (380 + rng.uniform(-6, 6), y - 6), v, rng)
        else:
            d.text((380, y), v, font=bold, fill=(20, 20, 20))
    d.text((60, 860), "Mechanic signature: ________    Parts and labour at workshop rates.", font=small, fill=(60, 60, 60))
    d.text((60, 950), farm_b.FOOTER.replace("fictional supplier", "fictional workshop"), font=small, fill=(120, 120, 120))
    img = farm_b._photograph(img, r.damage, rng)
    scale = 1000 / max(img.size)
    return img.resize((int(img.width * scale), int(img.height * scale)))


def main() -> None:
    truth, checks = build()
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    truth.to_csv(OUT / "ground_truth.csv", index=False)
    checks.to_csv(OUT / "ground_truth_checks.csv", index=False)
    for r in truth.itertuples():
        render(r).save(OUT / "sheets" / f"{r.sheet_id}.jpg", quality=78, optimize=True)
    print(f"{len(truth)} workshop sheets ({(truth.layout == 'handwritten').sum()} handwritten); planted: {HOURS_TYPO_SHEET} "
          f"hours on sheet {checks.on_sheet.iloc[0]} vs log {checks.in_log.iloc[0]}")


if __name__ == "__main__":
    main()
