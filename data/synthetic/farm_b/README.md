# Farm B: illustrative demo data

Farm B is the **same real farm as Farm A**, seen only through fuel receipts and a simple farm profile
(Tier 3). Regenerate with `python data/synthetic/generate_farm_b.py` (Windows fonts are used for
rendering; the committed images make regeneration optional).

| File | What it is | Real or synthetic |
|---|---|---|
| `receipts/B01.jpg` ... `B24.jpg` | 24 fuel receipt images: 12 delivery notes, 6 handwritten dockets, 5 farm-store till receipts, 1 duplicate photo | **Synthetic** (fictional suppliers, invented layouts and damage) |
| `ground_truth_documents.csv`, `ground_truth_lines.csv` | What each image says, for scoring receipt extraction | Synthetic |
| `farm_b_profile.csv` | Fields, field area, operations and worked area, as a farmer would state them | Derived from Farm A GPS distance x implement width; **no fuel, no coordinates** |
| `farm_b_machines.csv` | Tractors and rated power | From the TUM article (Table 1) |

- **Real inputs:** the diesel litres on the receipts add up to Farm A's measured fuel (10,813.7 L,
  TUM Agricultural Load Cycles, CC-BY-4.0), and unit prices follow Defra UKAMMG monthly red-diesel
  prices (OGL-3.0) with a +-3% supplier spread.
- **Assumption:** fuel delivered over the season equals fuel used (tank level the same at start and end).
- **Traps for validation:** an AdBlue line (B03) and a re-photographed delivery note (B24 = B22). See
  `docs/receipt_validation_rules.md`.
- **VAT:** shown at 5%; every supply is at most 2,300 L (VAT Notice 701/19 para 6.1.1). Illustrative only.
- July has no deliveries because Defra published no July price in our reference data.
