"""Range coverage: do Farm B's estimated ranges (receipts + profile, Tier 3) contain Farm A's measured
litres (telemetry, Tier 1)? Same real farm, so this measures how honest the uncertainty is.

Truth per operation = Farm A working litres (field_work, measured): published rates exclude field travel.
Truth for the remainder = Farm A total minus the working litres of the operations Farm B estimated.

Run: python -m evals.range_coverage
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.emissions.farm_summary import farm_a_rows
from backend.emissions.tier3 import REMAINDER_KEY, breakdown_by_operation

RESULTS = Path(__file__).resolve().parents[1] / "evals" / "results" / "range_coverage.json"


def farm_a_truth(keys: list[str]) -> dict[str, float]:
    rows = farm_a_rows()
    working = rows[rows.activity_class == "field_work"].groupby("operation_code").litres.sum()
    truth = {k: float(working.get(k, 0.0)) for k in keys if k != REMAINDER_KEY}
    truth[REMAINDER_KEY] = float(rows.litres.sum()) - sum(truth.values())
    return truth


def coverage() -> dict:
    estimate = breakdown_by_operation()
    truth = farm_a_truth([r.key for r in estimate])
    rows = []
    for r in estimate:
        t, lo, hi = truth[r.key], r.litres.low, r.litres.high
        side = "inside" if lo <= t <= hi else "below" if t < lo else "above"
        rows.append({"key": r.key, "name": r.name, "low": round(lo, 1), "typical": round(r.litres.value, 1),
                     "high": round(hi, 1), "measured": round(t, 1), "side": side,
                     "miss_pct": 0.0 if side == "inside" else round(100 * (t - (lo if t < lo else hi)) / t, 1)})
    ops = [r for r in rows if r["key"] != REMAINDER_KEY]
    inside = [r for r in ops if r["side"] == "inside"]
    remainder = next(r for r in rows if r["key"] == REMAINDER_KEY)
    return {
        "operations": len(ops), "operations_inside": len(inside),
        "coverage_by_count": round(len(inside) / len(ops), 3),
        "coverage_by_litres": round(sum(r["measured"] for r in inside) / sum(r["measured"] for r in ops), 3),
        "remainder_inside": remainder["side"] == "inside",
        "misses": [{k: r[k] for k in ("key", "side", "low", "high", "measured", "miss_pct")}
                   for r in ops if r["side"] != "inside"],
        "rows": rows,
        "note": "Farm B never sees telemetry: ranges come from receipts, the farm profile and Iowa A3-27 rates.",
    }


def main() -> None:
    result = coverage()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
