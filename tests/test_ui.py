"""A interface local deve carregar no mesmo servidor da API."""

from fastapi.testclient import TestClient

from app.api import app


def test_local_ui_and_assets_are_served_without_breaking_api_docs():
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "DrenaAssist · DrenaHub" in page.text
    assert 'src="/static/app.js"' in page.text

    script = client.get("/static/app.js")
    stylesheet = client.get("/static/styles.css")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "fetch(\"/assistant/ask\"" in script.text
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert client.get("/static/favicon.svg").status_code == 200

    assert client.get("/docs").status_code == 200


def test_operational_overview_lists_points_with_latest_records():
    client = TestClient(app)
    data = client.get("/operational/overview").json()
    assert data["synthetic"] is True
    points = {p["id"]: p for loc in data["locations"] for p in loc["points"]}
    assert set(points) == {"RALO-01", "CANALETA-02", "BOMBA-01", "RALO-02", "RALO-03"}
    assert points["RALO-01"]["reading"]["id"] == "LE-001"
    assert points["RALO-01"]["inspection"]["obstruction"] is True
    assert [e["id"] for e in points["RALO-01"]["open_events"]] == ["OC-001"]
    assert points["CANALETA-02"]["open_events"] == []
