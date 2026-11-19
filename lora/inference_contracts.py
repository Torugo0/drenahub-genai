"""Contratos HTTP do runtime local Qwen/LoRA da V2.

O serviço devolve a saída bruta do modelo. JSON sintaticamente válido não
equivale a afirmações fundamentadas; o chamador valida evidências e política.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Mode = Literal["base", "adapted"]
MAX_INPUT_CHARS = 12_000
MAX_BODY_BYTES = 65_536
MAX_PROMPT_TOKENS = 2_048


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode
    messages: list[ChatMessage] = Field(min_length=1, max_length=8)
    max_new_tokens: int = Field(default=256, ge=32, le=512)
    timeout_s: float = Field(default=60.0, ge=1.0, le=120.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_conversation(self) -> "GenerateRequest":
        if self.messages[-1].role != "user":
            raise ValueError("A última mensagem deve ser do usuário")
        if not any(item.role == "user" for item in self.messages):
            raise ValueError("Ao menos uma mensagem de usuário é necessária")
        if any(not item.content.strip() for item in self.messages):
            raise ValueError("Mensagens não podem estar vazias")
        if sum(len(item.content) for item in self.messages) > MAX_INPUT_CHARS:
            raise ValueError(f"Entrada excede {MAX_INPUT_CHARS} caracteres")
        if any(item.role == "system" for item in self.messages[1:]):
            raise ValueError("Mensagem de sistema só pode ser a primeira")
        return self


class GenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode
    model_id: str
    model_revision: str
    adapter_loaded: bool
    adapter_active: bool = False
    raw_output: str
    json_valid: bool
    parsed_json: Any | None = None
    prompt_tokens: int = Field(ge=1)
    generated_tokens: int = Field(ge=0)
    stop_reason: Literal["eos", "max_new_tokens", "timeout", "other"]
    elapsed_ms: float = Field(ge=0)
    generation: dict[str, Any]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["cold", "loading", "ready", "degraded"]
    model_id: str
    model_revision: str
    model_path_exists: bool
    model_loaded: bool
    adapter_present: bool
    adapter_loaded: bool
    adapter_provenance_verified: bool
    cuda_loaded: bool
    error_type: str | None = None
