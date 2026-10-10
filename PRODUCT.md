# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
React + Vite + Tailwind static build, served by the FastAPI backend in one Cloud Run service (decided in CLAUDE.md section 7). Local-first; Terraform and Cloud Run come later.

## Users
Small and mid-sized farmers, primarily on a phone, at the farm or at home. They are not emissions experts. Their job: understand where their machinery fuel goes, what it costs, and what to change. The 3-minute demo video for the hackathon judges is a secondary audience.

## Product Purpose
FieldCarbon turns farm fuel data (telemetry CSV, logbook, or receipts) into a ranked action plan with honest confidence levels: what to change, what it costs and saves, how sure we are, and what extra data would make us surer. Uncertainty is the product.

## Positioning
Other tools give you a number. FieldCarbon tells you what to change, how sure we are, and what data would make us surer. Every figure carries a measured / allocated / estimated label and a traceable source.

## Operating Context
Data tiers: telemetry (measured), logbook (allocated), receipts only (estimated). Demo: Farm A is real TUM telemetry; Farm B is the same farm seen through generated receipts. All results are labelled illustrative demo data. Flow: Your farm, Pain points + rating, Set a goal, Plan, Sharpen, Report.

## Capabilities and Constraints
- Frontend only displays; every figure comes from tested Python or SQL (API: `/api/farms/a/summary`, `/breakdown/{operation|tractor|field}`, `/pain-points`).
- Each figure: `{value, unit, label, how, low?, high?}`. Cost is a range only.
- Rating is a per-operation band (Below typical, Typical, Above typical, Well above), never a 0-100 score.
- Savings, cost and yield effects are ranges, never guarantees. Use "traceable" or "audit-ready", never "verified".
- Only Farm A exists; Farm B, the chat panel, interventions, ROI and "what would improve" are not built yet.
- Light and dark themes required. Confidence labels are text, never colour only. Show one "Demo data: illustrative" banner. Attribute TUM (CC-BY-4.0) in the footer.

## Brand Commitments
Name: FieldCarbon. Tagline: "From farm fuel receipts to ranked climate action, with honest confidence." Voice: plain first, detail on demand (confirmed). The user asked for a modern, edgy look with animated elements and a light/dark toggle.

## Evidence on Hand
Real Farm A aggregates in `data/aggregated/`, reference tables in `data/reference/` (emission factors, fuel-use rates, interventions, prices, sources). No farmer testimonials, no user research, no Farm B data, no logo or brand assets exist yet; do not fabricate them.

## Product Principles
1. Honest uncertainty over false precision: ranges and labels are first-class, not footnotes.
2. Show the data first, then the goal, then the plan.
3. Every number is traceable on demand; plain language by default.
4. Only recommend what has a source and is feasible for this farm.
5. Delight must never imply a claim the data does not support.

## Accessibility & Inclusion
Baseline WCAG: contrast in both themes, large tap targets, text labels for confidence, screen-reader labels, respect reduced motion. Basic multilingual output is planned in core.
