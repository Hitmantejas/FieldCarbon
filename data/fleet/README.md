# Fleet data: illustrative demo company

A contractor / co-operative that works many farms' fields, built from three real sites plus clearly
labelled synthetic records. Rebuild: `python -m backend.fleet.build` (needs `python data/prep/download_fleet.py`
once; seed 2026 makes every run identical). **All of it is illustrative demo data.**

Company year: **1 May 2025 to 30 April 2026**. Every job row has `date_basis`: `real+4y` (the vineyard's real
dates shifted exactly four years, so its seasons stay real) or `assigned` (placed in season by the generator).

| File | What it is | Real or synthetic |
|---|---|---|
| `sites.csv`, `machines.csv`, `operations.csv` | The three sites, 12 tractors, 30 operation codes | Real (from the sources) |
| `jobs.csv` | One row per job: litres, hours, area, load, idle ratio | **Real** values. `operator_id`, `client_id` and (S1, S3) `start_ts` are synthetic; `synthetic_columns` lists them |
| `other_activity.csv` | S1 fuel burned outside jobs (road transport, idling, tool not working) by month | Real litres, months allocated in proportion to each machine's job litres |
| `clients.csv`, `fields.csv`, `operators.csv` | Fictional client farms, fields (real ids and areas), operator pseudonyms (OP-01...) | Synthetic client and operator records |
| `depots.csv`, `fuel_deliveries.csv`, `fuel_dispenses.csv`, `depot_stock_readings.csv` | Fuel depots, tanker deliveries (real Defra monthly prices, +-2.5%), dispenses to machines, month-end dips | Synthetic, tied to the real consumption |
| `maintenance_events.csv` | Services every 250 job hours and a few routine repairs | Synthetic |
| `ground_truth_anomalies.csv` | The three planted problems, for scoring detection. Never shown to the analytics | Synthetic |
| `actions.csv`, `action_overlay.csv`, `ground_truth_actions.csv` | Two logged changes at S2 (a real effect of 15% planted on one, none on the other), the litres of the treated jobs after the change, and the planted effects for scoring. The tool never reads the last file | Synthetic, illustrative. Real litres in `jobs.csv` are never changed |

Sources: S1 TUM Agricultural Load Cycles (CC BY 4.0); S2 Rossi & Alemanno vineyard dataset (CC BY 4.0, fuel
estimated from tank level, labelled measured); S3 Dana, Ozener & Tellioglu tillage CAN data (CC BY 4.0, area
estimated from speed x time x tool width). Changes by FieldCarbon: aggregated, brands removed, dates shifted or
assigned, operators and clients added. No coordinates are stored anywhere.

Planted problems: **A1** one S1 machine takes about 20% more fuel than it burns in October 2025, on six
nights; **A2** 900 L leaves the S1 depot unlogged on 17 January 2026; **A3** one S2 delivery note is entered twice.
