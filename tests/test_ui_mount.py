"""The container serves the built React app from the same service as the API, without shadowing any API route."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.main import mount_ui


def app_with(dist) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_ui(app, dist)
    return TestClient(app)


def build(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>FieldCarbon</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


def test_the_built_app_is_served_at_the_root_with_its_assets(tmp_path):
    c = app_with(build(tmp_path))
    r = c.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and "FieldCarbon" in r.text
    assert c.get("/assets/app.js").status_code == 200


def test_api_routes_still_win_and_an_unknown_api_path_is_a_404_not_the_page(tmp_path):
    c = app_with(build(tmp_path))
    assert c.get("/api/ping").json() == {"ok": True}
    r = c.get("/api/x")
    assert r.status_code == 404 and "FieldCarbon" not in r.text


def test_without_a_build_only_the_api_runs(tmp_path):
    assert mount_ui(FastAPI(), tmp_path) is False
    c = app_with(tmp_path)
    assert c.get("/").status_code == 404 and c.get("/api/ping").status_code == 200
