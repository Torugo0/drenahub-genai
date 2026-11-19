"""As rotas V2 distinguem fonte não configurada de consulta vazia."""

from datetime import datetime, timezone
from types import SimpleNamespace
import hashlib
import json

from fastapi.testclient import TestClient

from app.api import app
from app import api_v2 as v2_api
from app.contracts import Evidence
from app.response_agent import AnswerResult
from treino.train_lora import MODEL_ID, MODEL_REVISION


def test_v2_source_status_and_unconfigured_data(monkeypatch, tmp_path):
    monkeypatch.delenv("DRENA_V2_DATA_EXPORT_DIR", raising=False)
    monkeypatch.delenv("DRENA_V2_VISION_URL", raising=False)
    monkeypatch.setattr(v2_api, "TRAINING_MANIFEST", tmp_path / "missing-manifest.json")
    monkeypatch.setattr(v2_api, "ADAPTER_WEIGHTS", tmp_path / "missing-adapter.safetensors")
    client = TestClient(app)
    status = client.get("/v2/sources")
    assert status.status_code == 200
    assert status.json()["llm_training"]["completed"] is False
    assert status.json()["point_registry"]["automatic_name_matching"] is False
    missing = client.get("/v2/drenadata/points/GARAGEM_A_RALO_01/latest")
    assert missing.status_code == 503
    assert missing.json()["detail"] == "Fonte indisponível nesta instância"
    assert client.get("/v2/drenavision/events", params={"point_id": "P-1"}).status_code == 503


def test_v2_source_status_reports_trained_adapter_without_runtime(monkeypatch, tmp_path):
    manifest = tmp_path / "training_manifest.json"
    manifest.write_text(json.dumps({"model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                                    "train_examples": 84, "dev_examples": 18}), encoding="utf-8")
    weights = tmp_path / "adapter_model.safetensors"
    weights.write_bytes(b"adapter fixture")
    config = tmp_path / "adapter_config.json"
    config.write_text("{}", encoding="utf-8")
    artifact = tmp_path / "artifact_manifest.json"
    artifact.write_text(json.dumps({
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "sha256": {
            "adapter/adapter_model.safetensors": hashlib.sha256(weights.read_bytes()).hexdigest(),
            "adapter/adapter_config.json": hashlib.sha256(config.read_bytes()).hexdigest(),
            "training_manifest.json": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    }), encoding="utf-8")
    monkeypatch.setattr(v2_api, "TRAINING_MANIFEST", manifest)
    monkeypatch.setattr(v2_api, "ADAPTER_WEIGHTS", weights)
    monkeypatch.setattr(v2_api, "ADAPTER_CONFIG", config)
    monkeypatch.setattr(v2_api, "ARTIFACT_MANIFEST", artifact)
    monkeypatch.setattr(v2_api, "_runtime_status", lambda: (False, False, "unavailable"))
    status = TestClient(app).get("/v2/sources")
    assert status.status_code == 200
    training = status.json()["llm_training"]
    assert training["completed"] is True
    assert training["adapter_runtime_available"] is False


def test_v2_runtime_cold_is_configured_but_not_ready(monkeypatch):
    class Client:
        def health(self):
            return SimpleNamespace(
                status="cold", model_path_exists=True, adapter_present=True,
                adapter_provenance_verified=True, model_loaded=False, adapter_loaded=False,
            )

    monkeypatch.setattr(v2_api, "InferenceClient", Client)
    assert v2_api._runtime_status() == (False, True, "cold")


def test_v2_latest_reading_preserves_provenance(monkeypatch):
    expected = Evidence(
        source_system="drenadata",
        kind="water_level",
        source_record_id="reading:sample-1",
        source_point_id="GARAGEM_A_RALO_01",
        observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
        data_origin="synthetic",
        review_status="not_applicable",
        facts={"water_level_cm": 12.3, "unit": "cm"},
    )

    class StubSource:
        def latest_reading(self, source_point_id):
            assert source_point_id == "GARAGEM_A_RALO_01"
            return expected

    monkeypatch.setattr(v2_api, "_data", lambda: StubSource())
    response = TestClient(app).get("/v2/drenadata/points/GARAGEM_A_RALO_01/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_system"] == "drenadata"
    assert payload["data_origin"] == "synthetic"
    assert payload["canonical_point_id"] is None
    assert "responsavel_hash" not in payload["facts"]


def test_v2_point_catalog_comes_from_configured_snapshot(monkeypatch):
    monkeypatch.setattr(v2_api, "_data", lambda: SimpleNamespace(
        snapshot_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
        readings=[SimpleNamespace(point_id="P-2"), SimpleNamespace(point_id="P-1"), SimpleNamespace(point_id="P-1")],
    ))
    response = TestClient(app).get("/v2/drenadata/points")
    assert response.status_code == 200
    assert response.json()["point_ids"] == ["P-1", "P-2"]
    assert response.json()["data_origin"] == "synthetic"


def test_v2_vision_blank_point_is_client_error(monkeypatch):
    class Vision:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def list_events(self, **kwargs):
            raise ValueError("point_id é obrigatório para delimitar a consulta")

    monkeypatch.setattr(v2_api, "_vision", Vision)
    response = TestClient(app).get("/v2/drenavision/events", params={"point_id": " "})
    assert response.status_code == 422


def test_v2_answer_endpoint_does_not_expose_raw_model_output(monkeypatch):
    async_result = AnswerResult(
        status="guarded_refusal",
        answer="A resposta gerada não passou na validação.",
        refused=True,
        source_ids=[],
        evidence=[],
        model_invoked=True,
        model_mode="adapted",
        raw_model_output="Afirmação inventada sobre sensor físico",
        validation_issues=["schema_invalid"],
    )
    monkeypatch.setattr(v2_api, "answer_with_evidence", lambda *args, **kwargs: async_result)
    response = TestClient(app).post("/v2/assistant/ask", json={
        "question": "Qual é a leitura?",
        "source": "drenadata_latest",
        "source_point_id": "EXTERNO-1",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "guarded_refusal"
    assert "raw_model_output" not in response.json()
