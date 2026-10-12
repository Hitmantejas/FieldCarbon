"""Every 'how this was worked out' text is short bullets with the key facts in bold and no internal names."""
import re

from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)
INTERNAL_ID = re.compile(r"\b[a-z]{2,}_[a-z0-9]+(?:_[a-z0-9]+)*\b")  # isu_a3_27, tum_alc_data, purdue_ae110


def hows():
    s = client.get("/api/farms/a/summary").json()
    for key in ("litres", "co2e_kg", "cost_gbp"):
        yield s[key]["how"]
    for by in ("operation", "tractor", "field"):
        for row in client.get(f"/api/farms/a/breakdown/{by}").json():
            for key in ("litres", "co2e_kg", "cost_gbp"):
                yield row[key]["how"]
    for rating in client.get("/api/farms/a/pain-points").json()["ratings"]:
        yield rating["how"]
    for idea in client.get("/api/farms/a/interventions").json():
        if idea["state"] != "not_feasible":  # a not-feasible idea shows its reason instead
            yield idea["how"]
        for figure in idea["figures"].values():
            if figure:
                yield figure["how"]
    goal = client.get("/api/farms/a/goal?target_pct=20").json()
    for figure in (goal["target_co2e"], goal["target_litres"]):
        yield figure["how"]
    for idea in goal["ideas"]:
        if idea["reach"]:
            yield idea["reach"]["how"]


def test_every_explanation_is_a_bullet_list():
    for how in hows():
        assert all(line.startswith("- ") for line in how.split("\n")), how


def test_every_explanation_bolds_the_facts_worth_noticing():
    for how in hows():
        assert "**" in how, how


def test_no_explanation_shows_internal_names_or_symbols():
    for how in hows():
        assert not INTERNAL_ID.search(how), how
        assert "+-" not in how and " x GBP" not in how and "L/ha" not in how, how
