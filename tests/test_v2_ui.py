"""O console V2 deve ser servido localmente e rotular as consultas com honestidade."""

from fastapi.testclient import TestClient

from app.api import app


def test_console_and_assets_are_served_from_local_app() -> None:
    client = TestClient(app)

    page = client.get("/v2/console")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "DrenaHub" in page.text
    assert 'src="/static/v2.js"' in page.text
    assert 'href="/static/v2.css"' in page.text
    assert "cdn." not in page.text.lower()

    script = client.get("/static/v2.js")
    stylesheet = client.get("/static/v2.css")
    assert script.status_code == 200
    assert stylesheet.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "text/css" in stylesheet.headers["content-type"]


def test_console_loads_data_catalog_and_keeps_sources_separate() -> None:
    client = TestClient(app)
    page = client.get("/v2/console").text
    script = client.get("/static/v2.js").text

    assert 'id="data-point-id"' in page
    assert "GARAGEM_A_RALO_01" not in page
    assert 'id="vision-point-id"' in page
    assert "Exemplo de teste" in page
    assert "não representa vínculo com a DrenaData" in page
    assert "Treino LoRA V2" in page
    assert "Pendente" in page
    assert "/v2/sources" in script
    assert "/v2/drenadata/points" in script
    assert "catalog.point_ids" in script
    assert "/v2/drenadata/points/" in script
    assert "/v2/drenavision/events?point_id=" in script
    assert "/v2/drenadata/precipitation/history" in script
    assert "error.status === 503" in script
    assert "error.status === 404" in script
    assert "records.length === 0" in script
    assert "innerHTML" not in script


def test_agent_is_a_reviewable_draft_with_visible_evidence() -> None:
    client = TestClient(app)
    page = client.get("/v2/console").text
    script = client.get("/static/v2.js").text

    assert 'id="agent-form"' in page
    assert 'value="drenadata_latest"' in page
    assert 'value="drenavision_events"' in page
    assert 'value="rain_history"' in page
    assert 'value="base"' in page
    assert 'value="adapted"' in page
    assert "revisão humana" in page.lower()
    assert "/v2/assistant/ask" in script
    assert 'method: "POST"' in script
    assert "draft_requires_review" in script
    assert "model_refusal_requires_review" in script
    assert "guarded_refusal" in script
    assert "no_record" in script
    assert "Revisão humana obrigatória" in script
    assert "Evidências consultadas" in script
    assert "IDs citados" in script
    assert "raw_model_output" not in script

