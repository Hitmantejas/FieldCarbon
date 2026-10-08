# Sources and reference data

`ref_sources.csv` is the canonical list: every row in the other `ref_*.csv` files has a `source_id`
in it (enforced by `tests/test_reference_data.py`). This file records how values were derived and
what is still open.

## Files
| File | Content | Status |
|---|---|---|
| `ref_emission_factors.csv` | UK GHG CF 2025 + 2026, one row per component (Scope 1, WTT, T&D) | Read from official flat files 2026-10-08 |
| `ref_fuel_use_rates.csv` | Iowa A3-27 (rev. Feb 2026) and Purdue AE-110 (1980), diesel, L/ha | Read from sources 2026-10-08; 1 gal/ac = 9.354 L/ha |
| `ref_operations.csv` | TUM work types → operation codes → rate rows, with `match_quality` | Our mapping (direct / closest / composite / none) |
| `ref_interventions.csv` | Intervention coefficients from the problem-statement research table | `from_problem_statement` until checked against primary source |
| `ref_fuel_prices.csv` | Red diesel p/litre per month, Sep 2025–Aug 2026 (Jul 2026 not published) | Read from UKAMMG PDFs 2026-10-08; VAT basis and underlying source not stated in reports |

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

## Open issues
1. Košutić 2007: two links (bib.irb.hr 336422 / 336450) — confirm if one study or two.
2. KPI MicroCAD 2025: archive link only — find the specific paper.
3. Electric tractor: news summary only — find the Oregon State primary study, else stays low confidence.
   Evidence covers a 30 hp (22.4 kW) tractor; smallest TUM tractor is 77 kW → not applicable to Farm A.
4. Missing links: SDSU no-till, ISU PM 2089, JARQ, Cummins.
5. GUTD `drawbar_only` applicability (not for PTO-speed-bound work, e.g. power harrow) is our
   inference — verify against PM 2089.
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
