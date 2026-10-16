"""A stable id for every finding, so a person or the agent can ask `diagnose_anomaly` about one of them.

The id is built from what the finding is about (kind, site, machine or depot, month, note or job), never from its
position in a list, so it is the same on every run over the same data.
"""
from __future__ import annotations

# The kinds that have a menu of possible causes in backend/tools/diagnose_anomaly.py.
DIAGNOSABLE_KINDS = frozenset({"machine_over_dispense", "stock_gap", "duplicate_delivery_note"})

ID_PARTS = {
    "machine_over_dispense": ("site_id", "machine_id", "month"),
    "machine_under_dispense": ("site_id", "machine_id", "month"),
    "night_dispense": ("site_id", "machine_id", "month"),
    "duplicate_delivery_note": ("site_id", "depot_id", "month", "doc_no"),
    "stock_gap": ("site_id", "depot_id", "month"),
    "stock_surplus": ("site_id", "depot_id", "month"),
    "data_gap": ("site_id", "machine_id"),
    "job_outlier": ("site_id", "machine_id", "month", "job_id"),
    "high_non_work_share": ("site_id", "machine_id"),
}


def finding_id(kind: str, *parts: str | None) -> str:
    """The kind and the non-empty parts joined with ':' (e.g. machine_over_dispense:S1:S1-T4:2025-10)."""
    return ":".join([kind, *(str(p) for p in parts if p)])


def tag(findings: list[dict]) -> list[dict]:
    """Adds `id` and `diagnosable` to each finding, in place."""
    for f in findings:
        f["id"] = finding_id(f["kind"], *(f.get(k) for k in ID_PARTS[f["kind"]]))
        f["diagnosable"] = f["kind"] in DIAGNOSABLE_KINDS
    return findings
