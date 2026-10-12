from fastapi import FastAPI, HTTPException

from backend.emissions.data import farm_a_breakdown, farm_a_totals
from backend.emissions.farm_summary import EF_YEAR, TRACTOR_KW
from backend.emissions.pain_points import above_range, farm_a_ratings

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
