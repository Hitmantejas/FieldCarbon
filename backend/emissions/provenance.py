from backend.emissions.farm_summary import EF_YEAR

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
