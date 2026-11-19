"""Contratos comuns para evidências de módulos distintos da DrenaHub.

IDs de sistemas diferentes nunca são unidos por semelhança textual. Um vínculo
com ponto canônico só existe quando foi registrado e verificado explicitamente.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceSystem = Literal["drenadata", "drenavision", "central", "document"]
EvidenceKind = Literal["water_level", "precipitation", "vision_detection", "incident", "document"]
DataOrigin = Literal["real", "synthetic", "unverified"]
ReviewStatus = Literal["not_applicable", "pending", "reviewed"]
FactValue = str | int | float | bool | None | list[str]


class SourceUnavailable(RuntimeError):
    """A fonte não respondeu; isso é diferente de uma consulta sem resultados."""


class PointLink(BaseModel):
    """Correspondência física confirmada entre um ID externo e um ponto comum."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_system: SourceSystem
    source_point_id: str = Field(min_length=1)
    canonical_point_id: str = Field(min_length=1)
    verified_by: str = Field(min_length=1)
    verified_at: datetime

    @model_validator(mode="after")
    def require_timed_verification(self) -> "PointLink":
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("verified_at precisa incluir fuso horário")
        return self


class PointRegistry(BaseModel):
    """Cadastro versionado; vazio por padrão, sem adivinhar equivalências."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    links: tuple[PointLink, ...] = ()

    @model_validator(mode="after")
    def reject_ambiguous_links(self) -> "PointRegistry":
        keys = [(link.source_system, link.source_point_id) for link in self.links]
        if len(keys) != len(set(keys)):
            raise ValueError("um ponto externo não pode ter dois vínculos")
        return self

    def resolve(self, source_system: SourceSystem, source_point_id: str | None) -> str | None:
        if not source_point_id:
            return None
        for link in self.links:
            if (link.source_system, link.source_point_id) == (source_system, source_point_id):
                return link.canonical_point_id
        return None


class Evidence(BaseModel):
    """Fato rastreável para consulta; não contém escore de risco inferido."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["2"] = "2"
    source_system: SourceSystem
    kind: EvidenceKind
    source_record_id: str = Field(min_length=1)
    source_point_id: str | None = None
    canonical_point_id: str | None = None
    observed_at: datetime
    collected_at: datetime | None = None
    retrieved_at: datetime | None = None
    snapshot_at: datetime | None = None
    data_origin: DataOrigin
    review_status: ReviewStatus
    facts: dict[str, FactValue]
    source_uri: str | None = None

    @model_validator(mode="after")
    def require_timezone_and_provenance(self) -> "Evidence":
        for field_name in ("observed_at", "collected_at", "retrieved_at", "snapshot_at"):
            value = getattr(self, field_name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{field_name} precisa incluir fuso horário")
        if self.canonical_point_id and not self.source_point_id:
            raise ValueError("canonical_point_id exige source_point_id")
        return self

    @property
    def citation_id(self) -> str:
        return f"{self.source_system}:{self.source_record_id}"
