"""Build the fleet tables into data/fleet. Run: python -m backend.fleet.build"""
from __future__ import annotations

from pathlib import Path

from backend.fleet.synth import build_fleet

OUT = Path(__file__).resolve().parents[2] / "data" / "fleet"


def write(out: Path = OUT, seed: int = 2026) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, table in build_fleet(seed).items():
        table.to_csv(out / f"{name}.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d %H:%M:%S")
        counts[name] = len(table)
    return counts


if __name__ == "__main__":
    for name, n in write().items():
        print(f"{name:24} {n:6} rows")
