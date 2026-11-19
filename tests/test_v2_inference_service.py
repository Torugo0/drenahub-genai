"""Contratos e roteamento HTTP V2; nenhum teste carrega checkpoint/GPU."""

import json
import hashlib
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import httpx
import pytest
from pydantic import ValidationError

from lora.inference_client import InferenceClient, InferenceClientError
from lora.inference_contracts import GenerateRequest, GenerateResponse, HealthResponse, MAX_BODY_BYTES
from lora.inference_service import GenerationTimeout, InferenceEngine, ModelUnavailable, make_handler
from lora.train_lora import MODEL_ID, MODEL_REVISION


MESSAGES = [{"role": "system", "content": "Responda em JSON."}, {"role": "user", "content": "Pergunta técnica geral."}]


class FakeEngine:
    def __init__(self):
        self.requests = []
        self.fail = False
        self.timeout = False

    def health(self):
        return HealthResponse(
            status="ready", model_id=MODEL_ID, model_revision=MODEL_REVISION,
            model_path_exists=True, model_loaded=True, adapter_present=True,
            adapter_loaded=True, adapter_provenance_verified=True, cuda_loaded=True,
        )

    def generate(self, request):
        if self.fail:
            raise ModelUnavailable("somente teste")
        if self.timeout:
            raise GenerationTimeout("somente teste")
        self.requests.append(request)
        raw = '{"answer":"Não consta nos dados disponíveis.","refused":true}'
        return GenerateResponse(
            mode=request.mode, model_id=MODEL_ID, model_revision=MODEL_REVISION,
            adapter_loaded=True, adapter_active=request.mode == "adapted", raw_output=raw, json_valid=True,
            parsed_json=json.loads(raw), prompt_tokens=21, generated_tokens=18,
            stop_reason="eos", elapsed_ms=12.3,
            generation={"do_sample": False, "num_beams": 1, "seed": 42, "max_new_tokens": request.max_new_tokens},
        )


@contextmanager
def local_server(engine):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(engine))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_generate_contract_limits_and_roles():
    request = GenerateRequest.model_validate({"mode": "base", "messages": MESSAGES})
    assert request.max_new_tokens == 256
    for invalid in (
        {"mode": "other", "messages": MESSAGES},
        {"mode": "base", "messages": [{"role": "user", "content": "x"}], "max_new_tokens": 513},
        {"mode": "base", "messages": [{"role": "assistant", "content": "x"}]},
        {"mode": "base", "messages": [{"role": "user", "content": " "}]},
        {"mode": "base", "messages": [{"role": "user", "content": "x" * 8_001}]},
        {"mode": "base", "messages": MESSAGES, "secret": "não permitido"},
    ):
        with pytest.raises(ValidationError):
            GenerateRequest.model_validate(invalid)


def test_health_distinguishes_absent_adapter_without_gpu(tmp_path):
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "model.safetensors").write_bytes(b"placeholder")
    engine = InferenceEngine(model_path, tmp_path / "missing-adapter", tmp_path / "missing-manifest")
    health = engine.health()
    assert health.status == "cold"
    assert health.model_path_exists and not health.model_loaded
    assert not health.adapter_present and not health.adapter_loaded
    assert not health.adapter_provenance_verified and not health.cuda_loaded


def test_adapter_provenance_rejects_changed_weight_bytes(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    files = {
        "adapter/adapter_model.safetensors": adapter / "adapter_model.safetensors",
        "adapter/adapter_config.json": adapter / "adapter_config.json",
        "training_manifest.json": tmp_path / "training_manifest.json",
    }
    files["adapter/adapter_model.safetensors"].write_bytes(b"original")
    files["adapter/adapter_config.json"].write_text("{}", encoding="utf-8")
    files["training_manifest.json"].write_text(json.dumps({
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "train_examples": 84, "dev_examples": 18,
    }), encoding="utf-8")
    (tmp_path / "artifact_manifest.json").write_text(json.dumps({
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
    }), encoding="utf-8")
    assert InferenceEngine(tmp_path, adapter, files["training_manifest.json"]).health().adapter_provenance_verified
    files["adapter/adapter_model.safetensors"].write_bytes(b"modified")
    assert not InferenceEngine(tmp_path, adapter, files["training_manifest.json"]).health().adapter_provenance_verified


def test_base_mode_disables_adapter_on_same_wrapper(tmp_path):
    class FakeAdapter:
        disabled = False

        @contextmanager
        def disable_adapter(self):
            self.disabled = True
            try:
                yield
            finally:
                self.disabled = False

    engine = InferenceEngine(tmp_path, tmp_path, tmp_path)
    wrapper = FakeAdapter()
    engine._base = object()
    engine._adapted = wrapper
    base_model, context = engine._select_generator("base")
    assert base_model is wrapper
    with context:
        assert wrapper.disabled
    assert not wrapper.disabled
    adapted_model, context = engine._select_generator("adapted")
    assert adapted_model is wrapper
    with context:
        assert not wrapper.disabled


def test_http_contract_and_read_only_client_without_gpu():
    engine = FakeEngine()
    with local_server(engine) as url:
        client = InferenceClient(url)
        health = client.health()
        assert health.model_loaded and health.adapter_loaded
        result = client.generate(MESSAGES, mode="base", max_new_tokens=128)
        assert result.raw_output == '{"answer":"Não consta nos dados disponíveis.","refused":true}'
        assert result.json_valid and result.mode == "base"
        assert result.adapter_loaded and not result.adapter_active
        assert engine.requests[0].max_new_tokens == 128
        with httpx.Client() as raw_client:
            invalid = raw_client.post(url + "/generate", json={"mode": "wrong", "messages": MESSAGES})
            assert invalid.status_code == 422
            oversized = raw_client.post(url + "/generate", content=b"x" * (MAX_BODY_BYTES + 1))
            assert oversized.status_code == 413
            missing = raw_client.get(url + "/other")
            assert missing.status_code == 404
        engine.fail = True
        with pytest.raises(InferenceClientError) as exc:
            client.generate(MESSAGES, mode="adapted")
        assert exc.value.status_code == 503
        assert exc.value.error_type == "ModelUnavailable"
        engine.fail = False
        engine.timeout = True
        with pytest.raises(InferenceClientError) as exc:
            client.generate(MESSAGES, mode="base")
        assert exc.value.status_code == 504
        assert exc.value.error_type == "GenerationTimeout"


def test_client_rejects_nonlocal_url():
    with pytest.raises(ValueError):
        InferenceClient("https://example.com")
