from fastapi import FastAPI, HTTPException

from backend.emissions.farm_summary import EF_YEAR, TRACTOR_KW, breakdown, farm_a_rows, summarise
from backend.emissions.pain_points import above_range, farm_a_ratings
from backend.tools.rank_interventions import rank_interventions

app = FastAPI(title="FieldCarbon API")

GROUPINGS = {"operation", "tractor", "field"}

PROVENANCE = {
    "dataset": "Agricultural Load Cycles: Tractor Mission Profiles From Recorded GNSS and CAN Bus Data, "
               "Götz K. (2025), Zenodo, doi:10.5281/zenodo.14619787; article: Götz K., Kusuma A., Dörfler A., "
               "Lienkamp M., Data in Brief 60 (2025) 111494, doi:10.1016/j.dib.2025.111494",
    "licence": "CC-BY-4.0",
    "attribution": "Technical University of Munich. Changes by FieldCarbon: tractor brands removed, "
                   "frozen-logger stretches excluded, data aggregated, per-field figures allocated by GPS geometry.",
    "emission_factors": f"UK GHG Conversion Factors {EF_YEAR}, gas oil, well-to-wheel",
    "demo_data": True,
}


def _require_farm_a(farm_id: str) -> None:
    if farm_id != "a":
        raise HTTPException(404, f"unknown farm {farm_id}")


@app.get("/api/farms/{farm_id}/summary")
def get_summary(farm_id: str):
    _require_farm_a(farm_id)
    rows = farm_a_rows()
    s = summarise(rows)
    excluded_h = float(rows[rows.activity_class == "data_gap"].hours.sum())
    return {
        "farm": {"id": "a", "name": "Farm A", "tier": 1, "description": "Real telemetry, 5 tractors, one season"},
        "litres": s.litres,
        "co2e_kg": s.co2e_kg,
        "cost_gbp": s.cost_gbp,
        "hours": s.hours,
        "tractors": [f"Tractor {t[-1]}, {kw} kW" for t, kw in TRACTOR_KW.items()],
        "excluded_hours": excluded_h,
        "provenance": PROVENANCE,
    }


@app.get("/api/farms/{farm_id}/breakdown/{by}")
def get_breakdown(farm_id: str, by: str):
    _require_farm_a(farm_id)
    if by not in GROUPINGS:
        raise HTTPException(404, f"cannot group by {by}")
    return breakdown(farm_a_rows(), by)


@app.get("/api/farms/{farm_id}/pain-points")
def get_pain_points(farm_id: str):
    _require_farm_a(farm_id)
    ratings, not_working = farm_a_ratings()
    return {"ratings": ratings, "above_range": above_range(ratings), "not_working": not_working}


@app.get("/api/farms/{farm_id}/interventions")
def get_interventions(farm_id: str):
    _require_farm_a(farm_id)
    return rank_interventions(farm_id)
