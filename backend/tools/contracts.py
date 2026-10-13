"""Shared contract for every figure the engine, API and agent tools return.

Principles enforced here: every figure carries a confidence label and at least one source_id
(traceable), and ranges are well-formed. A figure that breaks these cannot be constructed.
"""
from dataclasses import dataclass, field

# Weakest last: a breakdown figure carries the weakest label of its inputs.
LABELS: tuple[str, ...] = ("measured", "allocated", "estimated")


def weakest(labels) -> str:
    """Weakest confidence label among `labels` (measured < allocated < estimated)."""
    return max(labels, key=LABELS.index)


@dataclass(frozen=True)
class Figure:
    value: float | None  # None for a range-only figure such as cost
    unit: str
    label: str
    how: str  # plain-language calculation, shown when the user opens the figure
    source_ids: tuple[str, ...] = field(default=())  # rows of data/reference/ref_sources.csv
    low: float | None = None
    high: float | None = None

    def __post_init__(self) -> None:
        if self.label not in LABELS:
            raise ValueError(f"label must be one of {LABELS}, got {self.label!r}")
        if not self.source_ids:
            raise ValueError("a figure needs at least one source_id")
        if self.value is None and (self.low is None or self.high is None):
            raise ValueError("a figure without a value must have a low-high range")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"low {self.low} is above high {self.high}")
