# Receipt validation rules (spec)

Gemini reads each receipt image into a **raw** row (exactly as extracted). Deterministic rules then
decide what goes into the **validated** table that the emissions engine uses. Gemini never decides
whether a receipt counts; these rules do, and every decision is recorded with its reason.

Implementation and tests come with the `extract_receipt` tool. Ground truth for scoring:
`data/synthetic/farm_b/ground_truth_documents.csv` and `ground_truth_lines.csv`.

## Outcomes per line

| Outcome | Meaning | Counts toward litres? |
|---|---|---|
| `accepted` | All checks pass | Yes |
| `accepted_with_warning` | Counts, but a soft check failed (shown to the farmer) | Yes |
| `excluded` | Not engine fuel, or a duplicate | No |
| `needs_review` | Cannot be trusted without the farmer confirming | No, until confirmed |

## Rules

| # | Rule | Check | On failure |
|---|---|---|---|
| R1 | **Fuel product** | Product maps to a fuel in `ref_emission_factors` (red diesel / gas oil, diesel, HVO). AdBlue, oil, lubricants, filters and other non-fuel lines are not fuel. | `excluded` (reason: not engine fuel) |
| R2 | **Duplicate document** | Same supplier + document number as an already validated document (also same date and total). | `excluded` (reason: duplicate of `<doc>`) |
| R3 | **Litres present and positive** | 0 < litres <= 2,300 per supply (one delivery, one site, one day). | `needs_review` |
| R4 | **Line arithmetic** | litres x unit price = line net, within GBP 0.02 (or 0.5% of net, whichever is larger). | `needs_review` (a digit was probably misread) |
| R5 | **Document arithmetic** | Sum of line nets = net; net + VAT = total, within GBP 0.02. | `needs_review` |
| R6 | **Date in season** | Date parses and falls within the reporting season. | `needs_review` |
| R7 | **Plausible unit price** | Red diesel unit price within the Defra UKAMMG min-max for the season, +-15% (prices vary by supplier and volume). | `accepted_with_warning` |
| R8 | **Readability** | Gemini's own field-level confidence below threshold on litres, product or date. | `needs_review` |

Notes:
- VAT **rate** is not validated, only the arithmetic: the treatment of gas oil depends on use and supply
  size (VAT Notice 701/19 para 6.1) and is not needed for emissions.
- Litres are the only input to emissions. Money fields exist to catch misreads (R4, R5), not to compute cost.
- Units: litres only for now. A gallon receipt is `needs_review` until a unit conversion rule is added.
- A Tier 3 farm's total litres is the sum of `accepted` + `accepted_with_warning` lines; the
  `needs_review` litres are reported separately so the uncertainty is visible, never silently dropped.

## Expected results on the Farm B set

- B03 line 2 (AdBlue, 20 L) -> `excluded` by R1.
- B24 (a second photo of B22) -> `excluded` by R2.
- All other lines -> `accepted`; their litres sum to 10,813.7 L (Farm A measured: 10,813.69 L).
