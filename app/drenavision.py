"""Leitura de eventos DrenaVision sem executar inferência nem baixar mídia.

O horário retornado pela origem é o horário de análise, não a data em que a
foto/vídeo foi capturado. A origem dos pixels permanece não verificada.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator, model_validator

from .contracts import Evidence, PointRegistry, SourceUnavailable


VisionClass = Literal["obstrucao_visivel", "agua_acumulada", "animal_visivel"]
VisionStatus = Literal["sem_deteccao", "revisao_recomendada", "revisado"]


class _VisionEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(min_length=1)
    point_id: str | None = None
    timestamp: datetime
    input_type: Literal["image", "video"]
    model_version: str = Field(min_length=1)
    inspection_recommended: StrictBool
    status: VisionStatus
    evidence_uri: str | None = None

    @field_validator("event_id")
    @classmethod
    def require_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @field_validator("point_id")
    @classmethod
    def reject_blank_point(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("point_id vazio")
        return value

    @field_validator("timestamp", mode="before")
    @classmethod
    def require_iso_timestamp(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("timestamp precisa ser texto ISO com fuso horário")
        return value

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp precisa incluir fuso horário")
        return value


class _VisionEventSummary(_VisionEvent):
    detection_count: int = Field(ge=0)
    detected_classes: list[VisionClass]

    @model_validator(mode="after")
    def require_consistent_detection_summary(self) -> "_VisionEventSummary":
        if self.inspection_recommended != (self.detection_count > 0):
            raise ValueError("resumo de inspeção inconsistente")
        if self.status == "sem_deteccao" and self.detection_count:
            raise ValueError("sem_deteccao não pode conter detecções")
        if self.status == "revisao_recomendada" and not self.detection_count:
            raise ValueError("revisao_recomendada exige detecções")
        if self.detection_count == 0 and self.detected_classes:
            raise ValueError("classes sem detecções")
        if self.detection_count > 0 and not self.detected_classes:
            raise ValueError("detecções sem classes")
        return self


class _VisionDetection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    class_name: VisionClass


class _VisionEventDetail(_VisionEvent):
    detections: list[_VisionDetection]

    @model_validator(mode="after")
    def require_consistent_detections(self) -> "_VisionEventDetail":
        if self.inspection_recommended != bool(self.detections):
            raise ValueError("detecções e recomendação de inspeção incompatíveis")
        if self.status == "sem_deteccao" and self.detections:
            raise ValueError("sem_deteccao não pode conter detecções")
        if self.status == "revisao_recomendada" and not self.detections:
            raise ValueError("revisao_recomendada exige detecções")
        return self


class _VisionEventList(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[_VisionEventSummary]
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def require_possible_total(self) -> "_VisionEventList":
        if len(self.items) > self.total:
            raise ValueError("mais itens do que o total informado")
        return self


class DrenaVisionClient:
    """Adaptador HTTP para consultar evidências de visão já persistidas."""

    def __init__(
        self,
        *,
        base_url: str,
        registry: PointRegistry,
        timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = httpx.URL(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.username or parsed.password:
            raise ValueError("base_url deve ser HTTP(S) com host e sem credenciais na URL")
        if timeout_s <= 0:
            raise ValueError("timeout_s deve ser positivo")
        self._registry = registry
        self._client = httpx.Client(
            base_url=str(parsed).rstrip("/") + "/",
            timeout=timeout_s,
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DrenaVisionClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def list_events(
        self, *, point_id: str, limit: int = 50, offset: int = 0
    ) -> list[Evidence]:
        """Consulta um ID da origem; lista vazia significa resposta válida sem eventos."""
        if not point_id or not point_id.strip():
            raise ValueError("point_id é obrigatório para delimitar a consulta")
        source_point_id = point_id.strip()
        if len(source_point_id) > 80:
            raise ValueError("point_id excede o limite da DrenaVision")
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("limit ou offset inválido")
        payload = self._get_json(
            "vision/events",
            params={"point_id": source_point_id, "limit": limit, "offset": offset},
        )
        try:
            result = _VisionEventList.model_validate(payload)
        except ValidationError as exc:
            raise SourceUnavailable("DrenaVision retornou lista inválida") from exc
        if any(item.point_id != source_point_id for item in result.items):
            raise SourceUnavailable("DrenaVision retornou evento fora do ponto solicitado")
        retrieved_at = datetime.now(timezone.utc)
        return [self._to_evidence(item, retrieved_at=retrieved_at) for item in result.items]

    def get_event(self, event_id: str) -> Evidence | None:
        """Retorna None somente quando um evento válido não foi encontrado (404)."""
        try:
            normalized_id = str(UUID(event_id))
        except (ValueError, TypeError) as exc:
            raise ValueError("event_id deve ser UUID") from exc
        payload = self._get_json(f"vision/events/{normalized_id}", allow_not_found=True)
        if payload is None:
            return None
        try:
            item = _VisionEventDetail.model_validate(payload)
        except ValidationError as exc:
            raise SourceUnavailable("DrenaVision retornou evento inválido") from exc
        if str(UUID(item.event_id)) != normalized_id:
            raise SourceUnavailable("DrenaVision retornou ID de evento divergente")
        return self._to_evidence(item, retrieved_at=datetime.now(timezone.utc))

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        allow_not_found: bool = False,
    ) -> object:
        try:
            response = self._client.get(path, params=params)
        except httpx.RequestError as exc:
            raise SourceUnavailable("DrenaVision não respondeu à consulta") from exc
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SourceUnavailable(f"DrenaVision retornou HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise SourceUnavailable("DrenaVision retornou JSON inválido") from exc

    def _to_evidence(
        self, item: _VisionEventSummary | _VisionEventDetail, *, retrieved_at: datetime
    ) -> Evidence:
        if isinstance(item, _VisionEventSummary):
            classes = item.detected_classes
            detection_count = item.detection_count
        else:
            classes = sorted({detection.class_name for detection in item.detections})
            detection_count = len(item.detections)
        review_status = {
            "sem_deteccao": "not_applicable",
            "revisao_recomendada": "pending",
            "revisado": "reviewed",
        }[item.status]
        event_id = str(UUID(item.event_id))
        return Evidence(
            source_system="drenavision",
            kind="vision_detection",
            source_record_id=event_id,
            source_point_id=item.point_id,
            canonical_point_id=self._registry.resolve("drenavision", item.point_id),
            observed_at=item.timestamp,
            collected_at=None,
            retrieved_at=retrieved_at,
            data_origin="unverified",
            review_status=review_status,
            facts={
                "event_id": event_id,
                "model_version": item.model_version,
                "input_type": item.input_type,
                "detected_classes": classes,
                "detection_count": detection_count,
                "status": item.status,
                "inspection_recommended": item.inspection_recommended,
                "evidence_uri": item.evidence_uri,
                "timestamp_scope": "analysis_time_not_capture_time",
            },
            source_uri=f"{str(self._client.base_url).rstrip('/')}/vision/events/{event_id}",
        )
