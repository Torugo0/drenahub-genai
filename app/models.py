"""Contratos de entrada e saida compartilhados pela API e pela avaliacao."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class Configuration(str, Enum):
    baseline = "baseline"
    rag = "rag"
    agent = "agent"


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    configuration: Configuration = Configuration.agent
    location_id: str | None = Field(default=None, max_length=80)
    point_id: str | None = Field(default=None, max_length=80)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A pergunta deve ter ao menos 3 caracteres")
        return value


class EvidenceSource(BaseModel):
    source_id: str
    source_type: str
    title: str
    url: str | None = None


class DraftWorkOrder(BaseModel):
    point_id: str
    event_id: str
    evidence_ids: list[str]
    priority: str
    checklist: list[str]
    justification: str
    source_ids: list[str]
    status: str = "rascunho_pendente_aprovacao_humana"


class AskResponse(BaseModel):
    question: str
    answer: str
    supported: bool
    refused: bool
    sources: list[EvidenceSource] = Field(default_factory=list)
    reason: str
    suggested_actions: list[str] = Field(default_factory=list)
    draft_work_order: DraftWorkOrder | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self) -> "AskResponse":
        if self.refused:
            self.supported = False
            self.answer = "Não consta nos dados disponíveis."
            self.draft_work_order = None
        return self
