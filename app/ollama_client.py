"""Cliente HTTP sincrono para LLM local via Ollama."""

import os
from time import perf_counter
from typing import Any

import httpx


DEFAULT_MODEL = "qwen2.5:3b-instruct"


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, model: str | None = None, base_url: str | None = None, timeout_s: float | None = None):
        self.model = model or os.getenv("DRENA_MODEL", DEFAULT_MODEL)
        self.base_url = (base_url or os.getenv("DRENA_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout_s = timeout_s or float(os.getenv("DRENA_LLM_TIMEOUT_S", "120"))

    def generate_json(self, messages: list[dict[str, str]]) -> tuple[str, float]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "seed": 42, "num_predict": 512},
        }
        started = perf_counter()
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                response = client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Falha na chamada local ao Ollama: {type(exc).__name__}") from exc
        content = body.get("message", {}).get("content")
        if not isinstance(content, str):
            raise OllamaError("Ollama retornou resposta sem conteudo textual")
        return content, (perf_counter() - started) * 1000

    def available(self) -> bool:
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                names = [row.get("name", "") for row in response.json().get("models", [])]
                return self.model in names or any(name.startswith(self.model + ":") for name in names)
        except (httpx.HTTPError, ValueError):
            return False
