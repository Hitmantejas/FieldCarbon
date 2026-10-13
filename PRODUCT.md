# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
React + Vite + Tailwind static build served by the FastAPI backend in one Cloud Run service (CLAUDE.md section 7). Local-first; Terraform and Cloud Run come later. Desktop web application (laptop first).

## Users
Fleet managers, sustainability leads and operations staff at an agri contractor or co-operative that works many farms' fields. They sit at a laptop with live fleet data: tractors with telemetry, job logs, fuel deliveries and maintenance records. They are technical enough to read tables and charts. They are not emissions specialists. The 3-minute demo video for the hackathon judges is a secondary audience.

## Product Purpose
FieldCarbon shows where fuel is wasted across machines, jobs, fields and clients, ranks what to change from a curated evidence table, says how sure it is about every figure, names what extra data would make it surer, and shows whether past changes worked. A contractor also needs emissions per client job for its customers' reporting. Uncertainty is the product.

## Positioning
Other tools give you a fuel dashboard. FieldCarbon tells you what to change, how sure we are, what data would make us surer, and whether it worked. Every figure carries a measured / allocated / estimated label and traceable sources. Fuel reconciliation (fuel handed out against fuel burned, depot book stock against measured stock) catches problems a dashboard misses.

## Operating Context
Three demo sites with different data: raw telemetry (arable, Bavaria), per-operation summaries (vineyard, Tuscany) and raw CAN data for one tractor (tillage, Konya). Company year 1 May 2025 to 30 April 2026. Everything is demo data and labelled illustrative with one banner. Operators exist only as pseudonymous filters: they are never ranked, scored or compared, and the UI does not mention this rule.

## Capabilities and Constraints
- Frontend only displays; every figure comes from tested Python or SQL (API: `/api/fleet/summary`, `/clients`, `/data-quality`, `/reconciliation`, `/benchmark`, `/anomalies`, `/opportunities`, `/what-if`).
- Each figure: `{value, unit, label, how, source_ids, low?, high?}`. Savings, cost and yield effects are ranges, never guarantees. Use "traceable" or "audit-ready", never "verified".
- Recommendations come only from the evidence table and only where applicable. The vineyard has no applicable evidence yet and says so. Benchmark differences are "to investigate, not waste".
- Light and dark themes required. Confidence labels are text, never colour only. Respect reduced motion.
- Explanations are short bullets with bold facts; plain language; no internal ids.

## Brand Commitments
Name: FieldCarbon. Tagline: "From fleet telemetry to ranked climate action, with honest confidence." Voice: plain, direct, honest about uncertainty. The user wants a modern, edgy look with some animated elements and a light/dark toggle (carried over from the farmer version).

## Evidence on Hand
Real fleet data in `data/fleet/` (713 real jobs over three sites, 16,493 L), labelled synthetic operators, clients, depots, deliveries, dispenses and maintenance, and three planted fuel problems with ground truth for evals. No testimonials, user research or brand assets exist; do not fabricate them.

## Product Principles
1. Honest uncertainty over false precision: ranges and labels are first-class, not footnotes.
2. Show what is wrong and what to do about it before showing more data.
3. Every number is traceable on demand.
4. Only recommend what has a source and applies to this machine, site or job.
5. Never pretend a difference in the data is proof of a fault.

## Accessibility & Inclusion
Baseline WCAG: contrast in both themes, text labels for confidence, keyboard focus, screen-reader labels, tables with real headers, respect reduced motion.
