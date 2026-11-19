"""Cliente HTTP somente de inferência para a API principal do DrenaAssist.

Não abre arquivos do adapter, não grava registros e não trata JSON gerado
como evidência factual. A API chamadora decide quais fontes fornecer e validar.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .inference_contracts import GenerateRequest, GenerateResponse, HealthResponse


DEFAULT_URL = "http://127.0.0.1:8765"


class InferenceClientError(RuntimeError):
    def __init__(self, error_type: str, status_code: int | None = None):
        self.error_type = error_type
        self.status_code = status_code
        super().__init__(f"Serviço local de inferência: {error_type}")


class InferenceClient:
    def __init__(self, base_url: str | None = None, load_allowance_s: float | None = None):
        self.base_url = (base_url or os.getenv("DRENA_V2_INFERENCE_URL", DEFAULT_URL)).rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.path not in {"", "/"}:
            raise ValueError("A inferência V2 deve usar uma URL HTTP local em loopback")
        self.load_allowance_s = load_allowance_s if load_allowance_s is not None else float(os.getenv("DRENA_V2_INFERENCE_LOAD_ALLOWANCE_S", "120"))
        if not 0 <= self.load_allowance_s <= 300:
            raise ValueError("DRENA_V2_INFERENCE_LOAD_ALLOWANCE_S fora do limite")

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            error_type = str(response.json().get("error", {}).get("type", "HTTPError"))
        except (ValueError, AttributeError, TypeError):
            error_type = "HTTPError"
        raise InferenceClientError(error_type, response.status_code)

    def health(self) -> HealthResponse:
        try:
            with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
                response = client.get(f"{self.base_url}/health")
            self._raise_for_error(response)
            return HealthResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise InferenceClientError(type(exc).__name__) from exc

    def generate(
        self,
        messages: list[dict[str, str]],
        mode: str = "adapted",
        max_new_tokens: int = 256,
        timeout_s: float = 60.0,
    ) -> GenerateResponse:
        request = GenerateRequest.model_validate({
            "messages": messages,
            "mode": mode,
            "max_new_tokens": max_new_tokens,
            "timeout_s": timeout_s,
        })
        read_timeout = request.timeout_s + self.load_allowance_s
        try:
            with httpx.Client(timeout=httpx.Timeout(read_timeout, connect=3.0, write=5.0, pool=3.0)) as client:
                response = client.post(f"{self.base_url}/generate", json=request.model_dump(mode="json"))
            self._raise_for_error(response)
            return GenerateResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise InferenceClientError(type(exc).__name__) from exc
