# FieldCarbon — deck text for the official template

Template: "Submission Template _ AI Builder Cup.pptx" (14 slides). Each section below is one template slide,
in order; paste the text under the slide's existing title. Slide 2 is the template's own instruction note:
delete it before submitting.

Every figure comes from the app's own endpoints (`FIELDCARBON_DATA=csv`, 18 Oct 2026) or
`evals/results/summary.md`. Wording rules: "traceable" / "audit-ready", never "verified"; savings are ranges;
demo data is illustrative.

---

## Slide 1 — Team Details

- **Team name:** Valtechies
- **Team leader name:** Tejas Bhorade
- **Problem Statement:** Sustainability & Social Impact — helping agricultural contractors and farm
  co-operatives measure and cut the fuel and CO2e of their tractor fleets, with honest confidence levels.

---

## Slide 2 — (template instruction note)

Delete before submitting.

---

## Slide 3 — Brief about the idea

**FieldCarbon: where a farm-machinery fleet wastes fuel, what to change, and how sure we are. Every figure
traceable.**

Agricultural contractors run tractors across many client farms. Buyers now ask them for fuel and CO2e per
farm and per job, but fuel is bought in bulk, dispensed from a depot tank and burned across dozens of
clients, and the paperwork is on paper or in people's heads.

FieldCarbon is a web app for the fleet manager. It turns telemetry, fuel logs, photos of delivery notes and
workshop sheets, and voice notes into fuel, cost and CO2e by site, machine, job, field and client. It
finds waste, ranks what to change by strength of evidence, proves savings before and after, and writes a
traceable statement for each client farm.

**Gemini reads and explains; tested code does every calculation; an auditor checks every number Gemini
writes.**

---

## Slide 4 — Opportunities

**How different is it from any of the other existing ideas?**
Other tools give you a number. FieldCarbon tells you what to change, how sure we are, and what data would
make us surer. Every figure carries a label shown as text — MEASURED, ALLOCATED or ESTIMATED — and opens
into its sources, emission factor and calculation. Savings are ranges from published research, never a
single promise.

**How will it be able to solve the problem?**
- Works with the data contractors already have: telemetry CSVs, a fuel log, and photos of paperwork.
- Splits fleet fuel to each client farm and job, so a contractor can answer a buyer's carbon request.
- Checks deliveries against dispenses and fuel burned, and diagnoses each gap with causes tested in code.
- Ranks only the changes that fit this fleet; names the one missing input that would most narrow a range.

**USP of the proposed solution**
- **Uncertainty is the product:** confidence labels on 100% of figures, "what would improve this answer?"
- **Gemini never does the maths:** an auditor traces every number in an AI answer to a tool output.
- **Proof, not promises:** savings judged against machines that did not change; "can't tell yet" when the
  range still crosses zero.

---

## Slide 5 — List of features offered by the solution

- **Fleet overview & carbon ledger:** tonnes emitted, bounded range that could be avoided, tonnes proven
  avoided, whether a goal is reachable; week summary of the three things to look at first.
- **Sites, machines, jobs, clients:** the same job compared across machines (L/ha, L/h, idle share);
  emissions per client farm.
- **Fuel control:** deliveries vs dispenses vs fuel burned; delivery notes read by Gemini and checked
  against the fuel log; live photo upload with an instant verdict.
- **Anomaly diagnosis:** code tests a fixed menu of causes ("supported", "not supported", "cannot test");
  Gemini suggests, a person decides.
- **Voice notes:** record a machine problem; Gemini hears machine, issue, severity and follow-up.
- **Workshop job sheets:** handwritten sheets read and checked against the maintenance log.
- **Opportunities & what-if:** 8 interventions ranked by evidence, with litres, CO2e, cost and payback ranges.
- **Before-and-after proof** of logged changes.
- **Fleet analyst agent:** ask in plain language; shows the tools it used and traces every number.
- **Reports:** a one-page client carbon statement in English, German, Spanish or Hindi; print or PDF.
- **Trust screen:** the latest evaluation results in plain words.

---

## Slide 6 — Process flow diagram or Use-case diagram

Diagram (to draw): left to right.

1. **Capture** — telemetry CSV · fuel log · photo of a delivery note or workshop sheet · voice note
2. **Read** — Gemini 3.5 Flash turns photos and audio into a fixed JSON schema (instructions on the
   document are ignored)
3. **Check** — rules R1–R8 in code; compared with the fuel log: matches / differs / not in the log /
   keyed twice / needs review
4. **Calculate** — litres x UK GHG 2025 emission factor (well-to-wheel) in BigQuery; each figure labelled
   MEASURED / ALLOCATED / ESTIMATED
5. **Find & diagnose** — fuel gaps, frozen recorders, unusual jobs; causes tested in code
6. **Act** — ranked ideas with savings ranges and "what would improve this answer?"
7. **Prove** — before-and-after against machines that did not change
8. **Report** — traceable client statement; the analyst agent answers questions along the way

Use case: the fleet manager asks "Where did we waste fuel this season and what should we change first?" →
agent calls the tools → answer with labelled, traced numbers → manager prints the client statement.

---

## Slide 7 — Wireframes/Mock diagrams (optional)

Use the three design mocks in `docs/design/` (emission rail, reference page, docket desktop), or skip this
slide since slide 11 shows the real app.

---

## Slide 8 — Architecture diagram of the proposed solution

```
Telemetry (3 public datasets) ─► Cloud Storage ─► BigQuery (dataset fieldcarbon) ─► deterministic tools
Photos and voice notes ─► Gemini 3.5 Flash on Vertex AI ─► JSON schema ─► rules R1–R8 ─► BigQuery
Reference tables (emission factors, fuel-use rates, interventions, prices) ─► BigQuery
Browser ─► Cloud Run (React frontend) ─► Cloud Run (FastAPI backend) ─► tools
Question ─► ADK analyst agent (Gemini) ─► tool calls ─► answer ─► auditor (every number traced) ─► browser
```

- Region `us-central1`; Gemini on Vertex AI's `global` endpoint. Only synthetic documents and demo
  questions are sent to the model.
- Redraw from the mermaid diagram in `README.md`.

---

## Slide 9 — Technologies to be used in the solution

| Layer | Technology |
|---|---|
| AI model | Gemini 3.5 Flash on Vertex AI (multimodal: images and audio) |
| Agent | Google Agent Development Kit (ADK), tool calling |
| Data | BigQuery (tables, SQL views, BigQuery GIS for fields), Cloud Storage |
| Hosting | Cloud Run (frontend and backend), Cloud Build, Artifact Registry |
| Backend | Python, FastAPI, pytest |
| Frontend | React, Vite, Tailwind CSS |
| Reference data | UK GHG Conversion Factors 2025, Iowa State A3-27 and Purdue AE-110 fuel-use rates, Defra red diesel prices |

---

## Slide 10 — Estimated implementation cost (optional)

- **Cloud Run:** scales to zero; cost only while in use.
- **BigQuery:** small data (MB), queries in the free tier.
- **Gemini:** about 3,000 tokens per document read, about 1,600 per voice note, about 17,000 per analyst
  question. TODO: £/$ at current Vertex AI pricing for gemini-3.5-flash.
- **Per contractor:** TODO, e.g. 50 delivery notes + 50 questions a month = tokens x price.

---

## Slide 11 — Snapshots of the prototype

Screenshots to take from the live app (one per tile):
1. Overview — carbon ledger and week summary
2. Fuel control — a delivery note read by Gemini with its verdict
3. Diagnosis — causes marked supported / not supported
4. Opportunities — ranked ideas with ranges and evidence strength
5. Ask the analyst — an answer with "Numbers checked by code" open
6. Reports — client statement with the label stamps

Caption: *Demo data: illustrative.*

---

## Slide 12 — Prototype Performance report/Benchmarking

**Demo fleet:** 3 real public datasets (TUM arable, Italian vineyard, Turkish tillage) — 16,492 litres,
**55.8 t CO2e**, £13,221 fuel cost (estimated), 713 jobs, 1,508 engine hours, 1,800 ha.

| Evaluation | Result |
|---|---|
| Tool eval cases | 72 of 72 pass |
| Figures with a confidence label and sources | 100% of 918 |
| Analyst agent, 43 live questions: right tools / every number traced / ideas citing source | 100% / 100% / 100% |
| Agent refusals (ranking operators, farming advice, forecasts, guarantees, injected rules) | 7 of 7 |
| Gemini reading: 24 receipts, 14 delivery notes, 36 workshop sheets (every field) | 100% |
| Voice notes (8 recorded clips): machine and issue / status | 8 of 8 / 8 of 8 |
| Planted fuel problems found / top cause correct | 3 of 3 / 3 of 3 |
| Before-and-after, 150 random trials: false saving claimed / 90% range holds the truth | 9% / 91–97% |
| Receipts-only estimate vs telemetry truth | 8 of 12 job types inside the range |

Impact example: the strongest-evidence idea (shift up / throttle down) saves **329–987 litres, 1.1–3.3 t
CO2e a year** (estimated, 3 sources); the logged change has avoided **0.77 t (range 0.18–1.53 t)** so far
(illustrative logged change).

Honest notes: 17 of 43 first agent answers needed one automatic rewrite; document images are synthetic
renders, so 100% shows the pipeline works, not every real receipt.

---

## Slide 13 — Additional Details/Future Development

- Live fleet telemetry exports (CSV today, no brand lock-in).
- Co-operative and advisor view across many contractors.
- Field-level soil and terrain at scale; alerts when a machine drifts from its peers.
- Production: scheduled BigQuery loads, data-quality checks, layered ingestion.
- Privacy by design: operators never named or ranked; uploads never stored; no coordinates published.
- Data credits: Götz et al. (TUM, CC BY 4.0); Rossi & Alemanno (CC BY 4.0); Dana, Ozener & Tellioglu
  (CC BY 4.0); UK DESNZ GHG Conversion Factors 2025 (OGL v3.0).

---

## Slide 14 — Links

- **GitHub Public Repository:** https://github.com/Hitmantejas/FieldCarbon
- **Demo Video Link (3 Minutes):** TODO
- **Final Product Link:** https://fieldcarbon-frontend-818326148498.us-central1.run.app
