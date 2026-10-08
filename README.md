# FieldCarbon

**From farm fuel receipts to ranked climate action, with honest confidence.**

FieldCarbon is a mobile-friendly AI agent for small and mid-sized farms. A farmer sets a goal, such as
*"cut my machinery emissions by 20%"*. The agent returns a ranked action plan: what to change, what it
costs and saves, how sure we are, and which extra piece of data would make us surer.

Built for the Google Cloud AI Builder Cup 2026 (Sustainability & Social Impact track).

> **Demo data: illustrative.** Results are computed from public research data and synthetic receipts.
> They are not advice for a specific farm.

## Why it is different

**Uncertainty is the product.** A farm's total fuel use is solid. The split by operation and the effect
of each intervention are uncertain, and FieldCarbon says so:

- **Every figure carries a label.** `measured` comes from telemetry, `allocated` from a logbook or
  rules, and `estimated` from receipts plus standard rates.
- **Every figure is traceable** to its source, emission factor (with version and year), calculation
  and timestamp.
- **Savings are ranges.** Each low–high range comes from published sources. Every recommendation cites
  its evidence, and only actions that suit the farm's machinery are suggested.
- **The AI never does the maths.** Gemini plans, calls tools and explains. All numbers come from
  tested Python code and BigQuery SQL.
- **"What would improve this answer?"** A deterministic sensitivity analysis names the one missing
  data item that would most narrow the uncertainty.

## Demo concept: one real farm, two views

| View | Data | Label |
|---|---|---|
| **Farm A** | Real CAN-bus and GNSS telemetry from 5 tractors (TUM Agricultural Load Cycles, 2024 season) | measured |
| **Farm B** | The *same* farm seen only through fuel receipts, generated so their litres add up to Farm A's real fuel use | estimated |

Running the same goal on both views shows whether Farm B's estimated ranges contain Farm A's
measured values. That is an honest test of our uncertainty.

## Status

| Phase | Scope | Status |
|---|---|---|
| 1. Data foundation | Reference tables, BigQuery schema, telemetry preparation | **In progress.** Local data preparation is done; BigQuery load is next |
| 0. Cloud Run skeleton | Container, health endpoint, deployment | Planned |
| 2. Deterministic engine | Emissions, driver breakdown, intervention ranking, ROI, "what would improve" | Planned |
| 3. Agent and chat UI | Gemini agent with tool calling, faithfulness checks, mobile UI | Planned |
| 4. Receipts (Farm B) | Receipt images, Gemini extraction (raw and validated tables), estimated breakdown | Planned |
| 5. Grounding and report | Vertex AI Search over open-access evidence, shareable traceable report | Planned |
| 6. Evaluation and submission | Eval harness, results, demo video, deck | Planned |

### Farm A telemetry after cleaning

| Tractor | Rated power | Fuel (L) | Excluded as frozen data |
|---|---|---|---|
| Tractor 1 | 77 kW | 207.5 | none |
| Tractor 2 | 104 kW | 2,065.5 | none |
| Tractor 3 | 140 kW | 1,937.5 | 3.4 h |
| Tractor 4 | 163 kW | 5,314.2 | 92.2 h |
| Tractor 5 | 174 kW | 1,289.0 | none |
| **Total** | | **10,813.7** | |

**Frozen data.** Some stretches of the recordings repeat every signal for hours, including GPS
position. One example shows 0 rpm while moving at 3.36 m/s. These are carried-forward values from
logger gaps, not measurements, so they are excluded and reported rather than counted.

## Architecture (planned)

- **Agent:** Google Agent Development Kit (ADK) on Gemini (Vertex AI), with tool calling
- **Engine:** BigQuery (reference tables, input tables, calculated views; BigQuery GIS for fields) and
  tested Python
- **App:** FastAPI backend and a React + Vite + Tailwind frontend in one Cloud Run service
- **Receipts:** Gemini multimodal extraction, keeping raw and validated tables for provenance
- **Grounding:** Vertex AI Search over open-access evidence documents only
- **Storage:** Cloud Storage for datasets and uploads

## Repository layout

```
backend/emissions/ddl/     BigQuery table definitions
backend/emissions/views/   Aggregation and calculated views (SQL)
data/prep/                 Download and clean the TUM telemetry
data/reference/            Emission factors, fuel-use rates, interventions, prices, sources
data/aggregated/           Small Farm A aggregates (no coordinates)
tests/                     pytest for all deterministic logic
```

## Setup

Requires Python 3.12 or later.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows; use .venv/bin/python on macOS/Linux
.venv/Scripts/python -m pytest -q
```

Download and prepare the telemetry (about 2.8 GB, checksum-verified, stored in the gitignored `data/raw/`):

```bash
.venv/Scripts/python data/prep/download_tum.py
.venv/Scripts/python data/prep/prepare_tum.py
```

The preparation script reads only the CSV files from the dataset zips. It never loads the `.pkl` files
they also contain.

## Data sources and licences

| Source | Used for | Licence |
|---|---|---|
| TUM Agricultural Load Cycles (Götz, 2025), [doi:10.5281/zenodo.14619787](https://doi.org/10.5281/zenodo.14619787) | Farm A telemetry | CC BY 4.0 |
| UK Government GHG Conversion Factors 2025/2026 (DESNZ) | Emission factors (well-to-wheel) | Open Government Licence v3.0 |
| Iowa State University Extension A3-27 (rev. 2026); Purdue Extension AE-110 (1980) | Fuel-use rates per operation | Cited, not redistributed |
| Defra UK Agricultural Market Monitoring Group reports | Red diesel price range | Open Government Licence v3.0 |
| Peer-reviewed, extension, thesis and manufacturer sources | Intervention effects | Cited, not redistributed |

The full source list, with derivations and open issues, is in
[`data/reference/sources.md`](data/reference/sources.md).

**Attribution.** Telemetry: Götz, K. (2025). *Agricultural Load Cycles: Tractor Mission Profiles From
Recorded GNSS and CAN Bus Data* [Data set]. Zenodo. https://doi.org/10.5281/zenodo.14619787. Article:
Götz K., Kusuma A., Dörfler A., Lienkamp M. (2025), *Data in Brief* 60, 111494.
https://doi.org/10.1016/j.dib.2025.111494.

**Changes made:**
- tractor and implement brand names removed;
- sentinel values and frozen stretches excluded;
- data aggregated by operation, machine and field;
- raw GPS coordinates not published.

**Limitations:**
- The farm is in Germany, but the report uses UK emission factors and prices and US fuel-use rates.
  These choices are stated in every report.
