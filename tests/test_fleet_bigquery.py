"""Fleet data in BigQuery: the DDL matches the CSV files, BigQuery mode returns the same tables and figures as CSV mode
(tested with a fake query, no GCP), and the BigQuery views agree with the fleet_summary tool (needs GCP, skipped by default).

Run the GCP part with:  FIELDCARBON_GCP_TESTS=1 pytest -m gcp tests/test_fleet_bigquery.py
"""
import os
import re
from datetime import timezone

import pandas as pd
import pytest

from backend.emissions import data as emissions_data
from backend.fleet import data
from backend.tools.fleet_summary import fleet_summary
from infra.load_fleet import DDL, FLEET, TABLES

TYPED = {"TIMESTAMP": "timestamp", "DATE": "date"}


def ddl_columns() -> dict[str, list[tuple[str, str]]]:
    text = re.sub(r"--[^\n]*", "", DDL.read_text(encoding="utf-8"))
    tables = {}
    for name, body in re.findall(r"`\$\{dataset\}\.fleet_(\w+)`\s*\((.*?)\)\s*(?:PARTITION|;)", text, re.S):
        tables[name] = [tuple(col.split()[:2]) for col in body.split(",")]
    return tables


def test_ddl_has_one_table_per_loaded_csv_with_the_csv_columns_in_order():
    ddl = ddl_columns()
    assert set(ddl) == set(TABLES)
    for name in TABLES:
        assert [c for c, _ in ddl[name]] == list(pd.read_csv(FLEET / f"{name}.csv", nrows=0).columns), name


def test_ground_truth_files_are_never_loaded():
    assert not [t for t in TABLES if t.startswith("ground_truth")]


def fake_bigquery(sql: str) -> list[dict]:
    """Rows as the BigQuery client returns them: timezone-aware timestamps, date objects, None for missing."""
    name = re.search(r"fleet_(\w+)`", sql).group(1)
    df = pd.read_csv(FLEET / f"{name}.csv")
    for col, kind in ddl_columns()[name]:
        if kind == "TIMESTAMP":
            df[col] = [None if pd.isna(v) else v.to_pydatetime().replace(tzinfo=timezone.utc) for v in pd.to_datetime(df[col])]
        elif kind == "DATE":
            df[col] = [None if pd.isna(v) else v.date() for v in pd.to_datetime(df[col])]
    return df.astype(object).where(df.notna(), None).to_dict("records")


def clear_caches():
    for fn in vars(data).values():
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()


@pytest.fixture
def bigquery_mode(monkeypatch):
    clear_caches()
    expected = {fn.__name__: fn() for fn in (data.jobs, data.other_activity, data.machines, data.sites, data.operations,
                                             data.clients, data.actions, data.action_overlay, data.deliveries,
                                             data.dispenses, data.depots, data.stock_readings, data.ledger)}
    summary = fleet_summary("month")
    monkeypatch.setenv("FIELDCARBON_DATA", "bigquery")
    monkeypatch.setattr(emissions_data, "bigquery_query", fake_bigquery)
    clear_caches()
    yield expected, summary
    clear_caches()


def test_bigquery_mode_returns_the_same_tables_as_csv_mode(bigquery_mode):
    expected, _ = bigquery_mode
    for name, csv_table in expected.items():
        from_bq = getattr(data, name)()
        pd.testing.assert_frame_equal(from_bq.reset_index(drop=True), csv_table.reset_index(drop=True), check_dtype=False,
                                      check_index_type=False, obj=name)


def test_bigquery_mode_gives_the_same_figures_as_csv_mode(bigquery_mode):
    _, csv_summary = bigquery_mode
    assert fleet_summary("month") == csv_summary


@pytest.mark.gcp
@pytest.mark.skipif(os.environ.get("FIELDCARBON_GCP_TESTS") != "1", reason="reads BigQuery; set FIELDCARBON_GCP_TESTS=1 to run")
@pytest.mark.parametrize("group_by", ["site", "machine", "operation", "month", "client"])
def test_bigquery_view_agrees_with_the_fleet_summary_tool(group_by):
    clear_caches()
    tool = {r["key"]: r for r in fleet_summary(group_by)["rows"]}
    view = {r["key"]: r for r in emissions_data.bigquery_query(
        f"SELECT * FROM `{emissions_data.PROJECT}.{emissions_data.DATASET}.v_fleet_by_{group_by}`")}
    assert view.keys() == tool.keys()
    for key, row in view.items():
        assert row["litres"] == pytest.approx(tool[key]["litres"]["value"], rel=1e-6), key
        assert row["co2e_kg"] == pytest.approx(tool[key]["co2e_kg"]["value"], rel=1e-6), key
        assert row["jobs"] == tool[key]["jobs"], key


def _same(a, b, path="result"):
    """Equal, with floats compared to a millionth: BigQuery and pandas may differ in the last digit."""
    if isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        assert a == pytest.approx(b, rel=1e-6, abs=1e-9), path
    else:
        assert a == b, path


@pytest.mark.gcp
@pytest.mark.skipif(os.environ.get("FIELDCARBON_GCP_TESTS") != "1", reason="reads BigQuery; set FIELDCARBON_GCP_TESTS=1 to run")
@pytest.mark.parametrize("name", ["fleet_summary", "emissions_per_client", "reconcile_fuel", "detect_anomalies", "benchmark_peers",
                                  "action_impact", "data_quality", "carbon_ledger"])
def test_every_tool_gives_the_same_answer_from_bigquery_as_from_the_csv_files(name, monkeypatch):
    from evals.checks import TOOLS
    tool = TOOLS[name]
    monkeypatch.setenv("FIELDCARBON_DATA", "csv")
    clear_caches()
    from_csv = tool()
    monkeypatch.setenv("FIELDCARBON_DATA", "bigquery")
    clear_caches()
    try:
        from_bigquery = tool()
    finally:
        monkeypatch.setenv("FIELDCARBON_DATA", "csv")
        clear_caches()
    _same(from_bigquery, from_csv)
