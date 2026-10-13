from functools import lru_cache
from pathlib import Path

import pandas as pd

REF = Path(__file__).resolve().parents[2] / "data" / "reference"


@lru_cache(maxsize=1)
def all_sources() -> list[dict]:
    """ref_sources.csv as JSON-safe rows (empty cells become None)."""
    table = pd.read_csv(REF / "ref_sources.csv").astype(object)
    return table.where(table.notna(), None).to_dict("records")
