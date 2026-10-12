from typing import Literal

from fastapi import FastAPI, HTTPException, Query

from backend.emissions.data import farm_a_breakdown, farm_a_totals
from backend.emissions.farm_summary import TRACTOR_KW
from backend.emissions.pain_points import above_range, farm_a_ratings
from backend.emissions.provenance import PROVENANCE
from backend.emissions.sources import all_sources
from backend.tools.generate_report import generate_report
from backend.tools.rank_interventions import rank_interventions
from backend.tools.set_goal import set_goal
from backend.tools.what_would_improve import what_would_improve

app = FastAPI(title="FieldCarbon API")

GROUPINGS = {"operation", "tractor", "field"}

def _require_farm_a(farm_id: str) -> None:
    if farm_id != "a":
        raise HTTPException(404, f"unknown farm {farm_id}")


@app.get("/api/farms/{farm_id}/summary")
def get_summary(farm_id: str):
    _require_farm_a(farm_id)
    totals = farm_a_totals()
    s = totals.summary
    return {
        "farm": {"id": "a", "name": "Farm A", "tier": 1, "description": "Real telemetry, 5 tractors, one season"},
        "litres": s.litres,
        "co2e_kg": s.co2e_kg,
        "cost_gbp": s.cost_gbp,
        "hours": s.hours,
        "tractors": [f"Tractor {t[-1]}, {kw} kW" for t, kw in TRACTOR_KW.items()],
        "excluded_hours": totals.excluded_hours,
        "provenance": {**PROVENANCE, "data_source": totals.data_source},
    }


@app.get("/api/farms/{farm_id}/breakdown/{by}")
def get_breakdown(farm_id: str, by: str):
    _require_farm_a(farm_id)
    if by not in GROUPINGS:
        raise HTTPException(404, f"cannot group by {by}")
    return farm_a_breakdown(by)


@app.get("/api/farms/{farm_id}/pain-points")
def get_pain_points(farm_id: str):
    _require_farm_a(farm_id)
    ratings, not_working = farm_a_ratings()
    return {"ratings": ratings, "above_range": above_range(ratings), "not_working": not_working}


def _answers(tyre_pressure_checked: bool | None, has_ctis: bool | None, ballast_type: str | None) -> dict:
    """The farmer's answers; an unanswered question is simply absent."""
    given = {"tyre_pressure_checked": tyre_pressure_checked, "has_ctis": has_ctis, "ballast_type": ballast_type}
    return {k: v for k, v in given.items() if v is not None}


@app.get("/api/farms/{farm_id}/interventions")
def get_interventions(farm_id: str, tyre_pressure_checked: bool | None = None, has_ctis: bool | None = None,
                      ballast_type: Literal["liquid", "none"] | None = None):
    _require_farm_a(farm_id)
    return rank_interventions(farm_id, _answers(tyre_pressure_checked, has_ctis, ballast_type))


@app.get("/api/sources")
def get_sources():
    return all_sources()


@app.get("/api/farms/{farm_id}/goal")
def get_goal(farm_id: str, target_pct: float | None = Query(None, ge=1, le=90), tyre_pressure_checked: bool | None = None,
             has_ctis: bool | None = None, ballast_type: Literal["liquid", "none"] | None = None):
    _require_farm_a(farm_id)
    return set_goal(target_pct, farm_id, _answers(tyre_pressure_checked, has_ctis, ballast_type))


@app.get("/api/farms/{farm_id}/sharpen")
def get_sharpen(farm_id: str, target_pct: float | None = Query(None, ge=1, le=90), tyre_pressure_checked: bool | None = None,
                has_ctis: bool | None = None, ballast_type: Literal["liquid", "none"] | None = None):
    _require_farm_a(farm_id)
    return what_would_improve(target_pct, farm_id, _answers(tyre_pressure_checked, has_ctis, ballast_type))


@app.get("/api/farms/{farm_id}/report")
def get_report(farm_id: str, target_pct: float | None = Query(None, ge=1, le=90), tyre_pressure_checked: bool | None = None,
               has_ctis: bool | None = None, ballast_type: Literal["liquid", "none"] | None = None):
    _require_farm_a(farm_id)
    return generate_report(target_pct, farm_id, _answers(tyre_pressure_checked, has_ctis, ballast_type))
