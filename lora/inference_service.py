"""Serviço HTTP local do checkpoint HF Qwen2.5-1.5B e seu adapter LoRA.

Executar no WSL, no ambiente CUDA isolado::

    /home/vitor/drenaassist-v2-train/.venv/bin/python -m lora.inference_service

O servidor usa apenas 127.0.0.1. GET /health não carrega a GPU; a primeira
POST /generate carrega o modelo. Não consulta fontes, não executa ferramentas
e não julga suporte factual: devolve a saída bruta para validação pelo chamador.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .inference_contracts import (
    MAX_BODY_BYTES,
    MAX_PROMPT_TOKENS,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
)
from .train_lora import MODEL_ID, MODEL_REVISION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = Path("/home/vitor/drenaassist-v2-train/model")
DEFAULT_ADAPTER_PATH = ROOT / "lora" / "adapter"
DEFAULT_MANIFEST_PATH = ROOT / "lora" / "training_manifest.json"


class ModelUnavailable(RuntimeError):
    """Checkpoint, CUDA ou adapter necessário indisponível."""


class GenerationTimeout(TimeoutError):
    """A geração excedeu o limite solicitado."""


class PromptTooLong(ValueError):
    """A entrada tokenizada excedeu o limite local."""


class InferenceEngine:
    """Um checkpoint quantizado, duas modalidades e uma fila serial de GPU."""

    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL_PATH,
        adapter_path: Path | str = DEFAULT_ADAPTER_PATH,
        manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
    ):
        self.model_path = Path(model_path)
        self.adapter_path = Path(adapter_path)
        self.manifest_path = Path(manifest_path)
        self._lock = threading.Lock()
        self._tokenizer: Any = None
        self._base: Any = None
        self._adapted: Any = None
        self._torch: Any = None
        self._loading = False
        self._cuda_loaded = False
        self._error_type: str | None = None
        self._adapter_provenance_verified = self._verify_provenance()

    def _model_present(self) -> bool:
        return (self.model_path / "config.json").is_file() and any(self.model_path.glob("*.safetensors"))

    def _adapter_present(self) -> bool:
        return (self.adapter_path / "adapter_config.json").is_file() and (self.adapter_path / "adapter_model.safetensors").is_file()

    def _verify_provenance(self) -> bool:
        if not self._adapter_present() or not self.manifest_path.is_file():
            return False
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            artifact_manifest_path = self.manifest_path.parent / "artifact_manifest.json"
            artifact_manifest = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or not isinstance(artifact_manifest, dict):
                return False
            expected_hashes = artifact_manifest.get("sha256", {})
            if not isinstance(expected_hashes, dict):
                return False
            actual_files = {
                "adapter/adapter_model.safetensors": self.adapter_path / "adapter_model.safetensors",
                "adapter/adapter_config.json": self.adapter_path / "adapter_config.json",
                "training_manifest.json": self.manifest_path,
            }
            if set(expected_hashes) != set(actual_files):
                return False
            for name, path in actual_files.items():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != expected_hashes[name]:
                    return False
            return (
                isinstance(manifest, dict)
                and manifest.get("model_id") == MODEL_ID
                and manifest.get("model_revision") == MODEL_REVISION
                and artifact_manifest.get("model_id") == MODEL_ID
                and artifact_manifest.get("model_revision") == MODEL_REVISION
                and int(manifest.get("train_examples", 0)) > 0
                and int(manifest.get("dev_examples", 0)) > 0
            )
        except (OSError, ValueError, TypeError):
            return False

    def health(self) -> HealthResponse:
        model_present = self._model_present()
        adapter_present = self._adapter_present()
        if self._loading:
            status = "loading"
        elif self._base is not None and self._adapted is not None:
            status = "ready"
        elif self._error_type or not model_present or (self._base is not None and self._adapted is None):
            status = "degraded"
        else:
            status = "cold"
        return HealthResponse(
            status=status,
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
            model_path_exists=model_present,
            model_loaded=self._base is not None,
            adapter_present=adapter_present,
            adapter_loaded=self._adapted is not None,
            adapter_provenance_verified=self._adapter_provenance_verified,
            cuda_loaded=self._cuda_loaded,
            error_type=self._error_type,
        )

    def _ensure_loaded(self) -> None:
        if self._base is not None:
            return
        if not self._model_present():
            self._error_type = "ModelFilesMissing"
            raise ModelUnavailable("Checkpoint local ausente")
        self._loading = True
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            if not torch.cuda.is_available():
                raise ModelUnavailable("CUDA indisponível no WSL")
            compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            tokenizer = AutoTokenizer.from_pretrained(
                str(self.model_path), revision=MODEL_REVISION, trust_remote_code=False, local_files_only=True,
            )
            tokenizer.pad_token = tokenizer.eos_token
            quantization = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=compute_dtype,
            )
            base = AutoModelForCausalLM.from_pretrained(
                str(self.model_path),
                revision=MODEL_REVISION,
                quantization_config=quantization,
                device_map={"": 0},
                dtype=compute_dtype,
                trust_remote_code=False,
                local_files_only=True,
                low_cpu_mem_usage=True,
            )
            base.config.use_cache = True
            base.eval()
            self._tokenizer, self._base, self._torch = tokenizer, base, torch
            self._cuda_loaded = True
            if self._adapter_present() and self._adapter_provenance_verified:
                try:
                    adapted = PeftModel.from_pretrained(base, str(self.adapter_path), is_trainable=False)
                    if not callable(getattr(adapted, "disable_adapter", None)):
                        raise ModelUnavailable("PEFT não oferece disable_adapter")
                    adapted.eval()
                    self._adapted = adapted
                except Exception as exc:
                    self._error_type = type(exc).__name__
                    # Um carregamento parcial pode ter alterado o módulo base.
                    # Não servir modo base até reiniciar e carregar de novo.
                    self._base = None
                    self._tokenizer = None
                    self._torch = None
                    self._cuda_loaded = False
                    raise ModelUnavailable("Falha ao carregar adapter; reinicie o serviço") from exc
            elif self._adapter_present():
                self._error_type = "AdapterProvenanceInvalid"
            else:
                self._error_type = "AdapterFilesMissing"
        except Exception as exc:
            self._error_type = type(exc).__name__
            if isinstance(exc, ModelUnavailable):
                raise
            raise ModelUnavailable("Falha ao carregar checkpoint local") from exc
        finally:
            self._loading = False

    def _select_generator(self, mode: str):
        """Base com adapter desativado; nunca usa adapter por engano."""
        if mode == "adapted":
            if self._adapted is None:
                raise ModelUnavailable("Adapter não carregado")
            return self._adapted, nullcontext()
        if mode != "base":
            raise ValueError("Modo desconhecido")
        if self._adapted is not None:
            disable = getattr(self._adapted, "disable_adapter", None)
            if not callable(disable):
                raise ModelUnavailable("Não é possível desativar o adapter no modo base")
            return self._adapted, disable()
        if self._base is None:
            raise ModelUnavailable("Checkpoint base não carregado")
        return self._base, nullcontext()

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        # O contexto disable_adapter altera estado no wrapper PEFT; serializar
        # impede que outra chamada rode com o modo errado.
        with self._lock:
            started = time.monotonic()
            self._ensure_loaded()
            model, adapter_context = self._select_generator(request.mode)
            tokenizer, torch = self._tokenizer, self._torch
            messages = [item.model_dump() for item in request.messages]
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_tensors="pt",
            )
            prompt_tokens = int(prompt.shape[1])
            if prompt_tokens > MAX_PROMPT_TOKENS:
                raise PromptTooLong(f"Prompt excede {MAX_PROMPT_TOKENS} tokens")
            prompt = prompt.to("cuda:0")
            from transformers import GenerationConfig

            generation_config = GenerationConfig(
                do_sample=False,
                num_beams=1,
                max_new_tokens=request.max_new_tokens,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                use_cache=True,
            )
            torch.manual_seed(42)
            torch.cuda.manual_seed_all(42)
            generated_started = time.monotonic()
            with adapter_context, torch.inference_mode():
                generated = model.generate(
                    input_ids=prompt,
                    attention_mask=torch.ones_like(prompt),
                    generation_config=generation_config,
                    max_time=request.timeout_s,
                )
            generation_elapsed = time.monotonic() - generated_started
            generated_ids = generated[0, prompt_tokens:]
            count = int(generated_ids.shape[0])
            raw = tokenizer.decode(generated_ids, skip_special_tokens=True)
            eos_ids = tokenizer.eos_token_id
            eos_set = set(eos_ids if isinstance(eos_ids, (list, tuple)) else [eos_ids])
            ended_with_eos = count > 0 and int(generated_ids[-1]) in eos_set
            if ended_with_eos:
                stop_reason = "eos"
            elif generation_elapsed >= request.timeout_s:
                stop_reason = "timeout"
            elif count >= request.max_new_tokens:
                stop_reason = "max_new_tokens"
            else:
                stop_reason = "other"
            if stop_reason == "timeout":
                raise GenerationTimeout("Geração excedeu o limite de tempo")
            try:
                parsed = json.loads(raw)
                valid = True
            except json.JSONDecodeError:
                parsed = None
                valid = False
            return GenerateResponse(
                mode=request.mode,
                model_id=MODEL_ID,
                model_revision=MODEL_REVISION,
                adapter_loaded=self._adapted is not None,
                adapter_active=request.mode == "adapted" and self._adapted is not None,
                raw_output=raw,
                json_valid=valid,
                parsed_json=parsed,
                prompt_tokens=prompt_tokens,
                generated_tokens=count,
                stop_reason=stop_reason,
                elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                generation={
                    "do_sample": False,
                    "num_beams": 1,
                    "seed": 42,
                    "max_new_tokens": request.max_new_tokens,
                    "timeout_s": request.timeout_s,
                    "max_prompt_tokens": MAX_PROMPT_TOKENS,
                },
            )


def make_handler(engine: InferenceEngine):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DrenaAssistV2Inference/1.0"

        def _send(self, status: int, body: dict[str, Any]) -> None:
            payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send(404, {"error": {"type": "NotFound", "message": "Rota não encontrada"}})
                return
            self._send(200, engine.health().model_dump(mode="json"))

        def do_POST(self) -> None:
            if self.path != "/generate":
                self._send(404, {"error": {"type": "NotFound", "message": "Rota não encontrada"}})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send(411, {"error": {"type": "LengthRequired", "message": "Content-Length obrigatório"}})
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send(413, {"error": {"type": "RequestTooLarge", "message": "Corpo fora do limite"}})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send(400, {"error": {"type": "InvalidJSON", "message": "JSON de entrada inválido"}})
                return
            try:
                request = GenerateRequest.model_validate(body)
            except ValidationError:
                self._send(422, {"error": {"type": "InvalidRequest", "message": "Contrato de entrada inválido"}})
                return
            try:
                response = engine.generate(request)
            except PromptTooLong:
                self._send(413, {"error": {"type": "PromptTooLong", "message": "Prompt tokenizado excede limite"}})
                return
            except GenerationTimeout:
                self._send(504, {"error": {"type": "GenerationTimeout", "message": "Geração excedeu limite de tempo"}})
                return
            except ModelUnavailable:
                self._send(503, {"error": {"type": "ModelUnavailable", "message": "Modelo ou adapter indisponível"}})
                return
            except Exception:
                self._send(503, {"error": {"type": "GenerationFailure", "message": "Falha de geração local"}})
                return
            self._send(200, response.model_dump(mode="json"))

        def log_message(self, format: str, *args: Any) -> None:
            # O corpo com prompts e evidências não entra nos logs HTTP.
            print(f"inference_http {self.client_address[0]} {format % args}", flush=True)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("DRENA_V2_INFERENCE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DRENA_V2_INFERENCE_PORT", "8765")))
    parser.add_argument("--model-path", type=Path, default=Path(os.getenv("DRENA_V2_INFERENCE_MODEL_PATH", str(DEFAULT_MODEL_PATH))))
    parser.add_argument("--adapter-path", type=Path, default=Path(os.getenv("DRENA_V2_INFERENCE_ADAPTER_PATH", str(DEFAULT_ADAPTER_PATH))))
    parser.add_argument("--manifest-path", type=Path, default=Path(os.getenv("DRENA_V2_INFERENCE_MANIFEST_PATH", str(DEFAULT_MANIFEST_PATH))))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("O serviço deve escutar somente em loopback")
    if not (1 <= args.port <= 65535):
        parser.error("Porta fora do intervalo 1..65535")
    engine = InferenceEngine(args.model_path, args.adapter_path, args.manifest_path)
    with ThreadingHTTPServer((args.host, args.port), make_handler(engine)) as server:
        print(json.dumps({"service": "drenaassist-v2-inference", "host": args.host, "port": args.port, "health": engine.health().model_dump(mode="json")}, ensure_ascii=False), flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
