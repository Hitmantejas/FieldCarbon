# Sources and reference data

`ref_sources.csv` is the canonical list: every row in the other `ref_*.csv` files has a `source_id`
in it (enforced by `tests/test_reference_data.py`). This file records how values were derived and
what is still open.

## Files
| File | Content | Status |
|---|---|---|
| `ref_emission_factors.csv` | UK GHG CF 2025 + 2026, one row per component (Scope 1, WTT, T&D) | Read from official flat files 2026-10-08 |
| `ref_fuel_use_rates.csv` | Iowa A3-27 (rev. Feb 2026) and Purdue AE-110 (1980), diesel, L/ha | Read from sources 2026-10-08; 1 gal/ac = 9.354 L/ha |
| `ref_operations.csv` | TUM work types → operation codes → rate rows, with `match_quality` and `drive_type` (drawbar / pto / none) | Our mapping (direct / closest / composite / none). `drive_type` is our own classification, used only to apply the drawbar-only condition of the shift-up evidence; PTO-run jobs are treated as not eligible |
| `ref_interventions.csv` | Intervention coefficients from the research table | Checked against the sources 2026-10-18: `checked`, `checked_derived` (our arithmetic on the source's numbers) or `not_confirmed` (never sets a range or counts as a source) |
| `ref_intervention_costs.csv` | Cost evidence for 5 interventions (CTIS, HVO, no-till, reduced tillage, tyre gauge); sign convention: positive = extra cost, negative = saving | Researched 2026-10-10; weak and dated; HVO and gauge rows `needs_primary_check` |
| `ref_fuel_prices.csv` | Red diesel p/litre per month, May 2025–Aug 2026 (Jul 2026 not published; **Jul 2025 not published either, derived**) | Read from UKAMMG PDFs 2026-10-08; VAT basis and underlying source not stated in reports |

## Method notes
- **Boundary:** well-to-wheel = Scope 1 combustion + WTT. HVO biogenic CO2 (2.43 kg/L, "outside of
  scopes") is reported but not counted, per the UK CF methodology. Electricity = generation + T&D + WTT.
- **Fuel type:** agricultural red diesel = UK CF "Gas oil" (cell comment: "also known as red diesel").
  Our reading, not an agriculture-specific DESNZ ruling. The TUM farm (DE) likely used road diesel
  (average blend) — we apply the UK framing and state it in the report.
- **Year:** TUM data is the 2024 season. Default set = 2025 (project decision; stated in every report). Gas oil and HVO factors are
  identical in 2025 and 2026; only electricity and blended diesel differ.
- **Rate uncertainty:** Iowa states ±35%, Purdue ±50%. Where Iowa Table 2 gives an explicit
  2015–2025 range we keep it. Both sources exclude travel between fields → transport and idle are a
  residual in Tier 3, never split with rates.
- **"pct more fuel" → saving:** a source saying condition X used *p*% more fuel gives a saving of
  1 − 1/(1+p) when X is removed (e.g. 10–25% more → 9.1–20.0% saving).
- **Point estimates** (single value) keep low = high; the ranking treats them as less robust.

## Source check, 2026-10-18
Each source was opened (abstract or page; full texts of paywalled papers were not read) and its figure compared with ours.
- **Matches:** Košutić 2007 (59.4% and 86.7% less fuel per hectare, one season in Slavonia), BOKU/Moitzi 2013 (33–50%),
  Šarauskis 2014 (12–58%), Čiplienė 2019 (3.5–4.0%), Valtra 2023 test (about 1 L/ha; maker's own test), Juselius 2020 (8.9% is the
  thesis's literature average), Serrano et al. 2009 (9.1–20% and 4.8–9.1% are our conversion of +10–25% and +5–10% fuel per hectare;
  disc harrowing, one 59 kW tractor).
- **Changed:** SDSU no-till had no percentage; 66.7% was our arithmetic on 6 vs 2 gal/ac. The article also gives 5.4 vs 2.8 gal/ac for
  South Dakota (48.1%), so the range is now 48.1–66.7%. JARQ's 15–50% is indoor tests on a 24 kW tractor; the abstract gives 15–30% at 55%
  engine load, so we use 15–30%. Sondors 2014: the 4.1% is specific fuel consumption (per unit of power); hourly use was about 1% lower.
- **Not confirmed (excluded from ranges and from the source count):** Iowa State PM 2089 (the store listing exists but its text was not
  found; 13% and 21% could not be matched; the Iowa State crop article by Hanna says 10%) and KPI MicroCAD 2025 (paper not found).
  Shift-up now rests on the Iowa State crop article (10%), the SAE 961779 Nebraska test analysis (11.4–16%, abstract only) and JARQ (15–30%).
- **Košutić 2007** is one study: CROSBI 336422 is the conference version of 336450, so the two ids never count as two sources for one idea.
- **Electric tractor:** 67.8% is our arithmetic (1 − 1.56/4.84 t GHG) on totals quoted in press coverage of the Oregon State study; the primary
  report was not found. Evidence covers a 30 hp (22.4 kW) tractor; the smallest TUM tractor is 77 kW, so it is not applicable to Farm A.
- **Still not opened:** Thanet HVO report (HTTP 403), USDA Conservation Insight 2022 (403), Cummins (maker's claim, no link), SoilGrids page text.

## Open issues
1. Full texts of the paywalled papers were not read; the figures come from abstracts and records.
2. `isu_pm2089`: read the brochure itself (store.extension.iastate.edu) and either restore its 13% and 21% or drop the source.
3. GUTD `drawbar_only` applicability (not for PTO-speed-bound work, e.g. power harrow) matches the Iowa State article ("not suitable
   when using PTO powered implements").
6. No yield ranges or capex in the research table yet — needed for ROI (farmdoc proportions).
7. Idle reduction / implement matching: excluded until a source is added (73% of Fendt 211 fuel
   was used with no implement attached).
8. Licences for extension/academic PDFs: we cite and link, we do not redistribute the documents
   unless open access (Vertex AI Search corpus = open-access only).

## Attribution (CC-BY-4.0)
Telemetry: Götz, K. (2025). *Agricultural Load Cycles: Tractor Mission Profiles From Recorded GNSS
and CAN Bus Data* [Data set]. Zenodo. https://doi.org/10.5281/zenodo.14619787 — and Götz K., Kusuma
A., Dörfler A., Lienkamp M. (2025), Data in Brief 60, 111494. Changes: brand names removed, data
cleaned, aggregated by operation, machine and field.

## Intervention costs (added 2026-10-10)
- **Priced:** CTIS (2022 trade press), HVO premium (council report, not opened), no-till and reduced
  tillage (2006 Farmers Weekly / TAG tables and an AHDB research page), tyre gauge (retail listing).
- **Not priced, and never shown as zero:** liquid ballast (forum posts only), shift-up / throttle-down
  (the Virginia Tech page is withdrawn; nothing sourced says what training costs), electric tractor
  (evidence covers under 22 kW only, so it is not feasible for this farm anyway).
- **Cost types differ on purpose:** `capex_one_off` (payback possible), `running_cost_extra_per_litre`
  and `operating_cost_per_area_change` (a yearly change in running cost, no payback). Tillage rows
  are **savings per hectare of establishment** and come from 2006 and ~2003 data: use them as a
  direction and rough size, not a current figure. Buying a drill is not priced.
- **Needs a real quote:** HVO (ask a fuel supplier; red diesel duty is cut from 10.18p to 6.48p/L from
  15 June to end 2026 and may cover biofuels, unconfirmed) and any CTIS or drill purchase.
- Wisconsin custom rates were dropped: they price one drilling pass only, not the whole system.

## Red diesel prices May to August 2025 (added 2026-10-13)
Added so the company demo year (May 2025 to April 2026) has a price for every month. Read from the
Defra UKAMMG data reports: May 2025 = 73.1p (June report), June 2025 = 71.8p (July report),
August 2025 = 75.7p (September report). **July 2025 was never published**: the September report says
August was "monthly up by 1.5%", so July is derived as 75.7 / 1.015 = 74.6p (0.746 GBP). Treat it as
derived, not published. The price range used by the app is now 0.718 to 1.176 GBP/L.
