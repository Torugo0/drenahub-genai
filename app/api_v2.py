"""Rotas locais da V2: evidências rastreáveis, sem inferência ou ação física."""

from __future__ import annotations

import os
import logging
import math
import json
import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from .contracts import Evidence, PointRegistry, SourceUnavailable
from .drenadata import load_gold_export
from .drenavision import DrenaVisionClient
from .inference_client import InferenceClient, InferenceClientError
from .response_agent import AnswerRequest, AnswerResult, answer as answer_with_evidence
from treino.train_lora import MODEL_ID, MODEL_REVISION


router = APIRouter(prefix="/v2", tags=["DrenaAssist V2 - evidências"])
LOGGER = logging.getLogger(__name__)
TRAINING_MANIFEST = Path(__file__).resolve().parents[1] / "treino" / "training_manifest.json"
ADAPTER_WEIGHTS = Path(__file__).resolve().parents[1] / "treino" / "adapter" / "adapter_model.safetensors"
ADAPTER_CONFIG = Path(__file__).resolve().parents[1] / "treino" / "adapter" / "adapter_config.json"
ARTIFACT_MANIFEST = Path(__file__).resolve().parents[1] / "treino" / "artifact_manifest.json"


def _registry() -> PointRegistry:
    configured = os.getenv("DRENA_V2_POINT_REGISTRY")
    if not configured:
        return PointRegistry(version="v2-unlinked")
    try:
        return PointRegistry.model_validate_json(Path(configured).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as exc:
        raise SourceUnavailable("Cadastro de pontos V2 ausente ou inválido") from exc


def _data():
    directory = os.getenv("DRENA_V2_DATA_EXPORT_DIR")
    if not directory:
        raise SourceUnavailable("Exportação Ouro da DrenaData não configurada")
    return load_gold_export(directory, registry=_registry())


def _vision() -> DrenaVisionClient:
    base_url = os.getenv("DRENA_V2_VISION_URL")
    if not base_url:
        raise SourceUnavailable("API DrenaVision não configurada")
    try:
        timeout_s = float(os.getenv("DRENA_V2_VISION_TIMEOUT_S", "20"))
        if not math.isfinite(timeout_s):
            raise ValueError("timeout não finito")
        return DrenaVisionClient(base_url=base_url, registry=_registry(), timeout_s=timeout_s)
    except ValueError as exc:
        raise SourceUnavailable("URL da DrenaVision inválida") from exc


def _source_failure(exc: SourceUnavailable) -> HTTPException:
    LOGGER.warning("Fonte V2 indisponível: %s", exc)
    return HTTPException(status_code=503, detail="Fonte indisponível nesta instância")


def _runtime_status() -> tuple[bool, bool, str]:
    try:
        health = InferenceClient().health()
    except (InferenceClientError, ValueError):
        return False, False, "unavailable"
    configured = (
        health.status in {"cold", "ready"}
        and health.model_path_exists
        and health.adapter_present
        and health.adapter_provenance_verified
    )
    available = configured and health.status == "ready" and health.model_loaded and health.adapter_loaded
    return available, configured, health.status


@router.get("/sources")
def sources() -> dict[str, object]:
    """Configuração, sem sugerir que uma fonte está disponível por ter URL."""
    trained = False
    model_id = None
    if TRAINING_MANIFEST.is_file() and ADAPTER_WEIGHTS.is_file() and ADAPTER_CONFIG.is_file() and ARTIFACT_MANIFEST.is_file():
        try:
            manifest = json.loads(TRAINING_MANIFEST.read_text(encoding="utf-8"))
            artifact = json.loads(ARTIFACT_MANIFEST.read_text(encoding="utf-8"))
            files = {
                "adapter/adapter_model.safetensors": ADAPTER_WEIGHTS,
                "adapter/adapter_config.json": ADAPTER_CONFIG,
                "training_manifest.json": TRAINING_MANIFEST,
            }
            trained = (isinstance(manifest, dict)
                       and isinstance(artifact, dict)
                       and isinstance(manifest.get("train_examples"), int)
                       and isinstance(manifest.get("dev_examples"), int)
                       and manifest["train_examples"] > 0 and manifest["dev_examples"] > 0
                       and manifest.get("model_id") == MODEL_ID
                       and manifest.get("model_revision") == MODEL_REVISION
                       and artifact.get("model_id") == manifest.get("model_id")
                       and artifact.get("model_revision") == manifest.get("model_revision")
                       and isinstance(artifact.get("sha256"), dict)
                       and set(artifact["sha256"]) == set(files)
                       and all(hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"][name]
                               for name, path in files.items()))
            model_id = manifest.get("model_id") if trained else None
        except (OSError, ValueError, TypeError):
            LOGGER.warning("Manifesto de treino V2 indisponível ou inválido")
    runtime_available, runtime_configured, runtime_status = _runtime_status() if trained else (False, False, "unavailable")
    return {
        "drenadata": {"configured": bool(os.getenv("DRENA_V2_DATA_EXPORT_DIR")), "mode": "snapshot_read_only"},
        "drenavision": {"configured": bool(os.getenv("DRENA_V2_VISION_URL")), "mode": "http_read_only"},
        "point_registry": {"configured": bool(os.getenv("DRENA_V2_POINT_REGISTRY")), "automatic_name_matching": False},
        "llm_training": {
            "completed": trained,
            "model_id": model_id,
            "adapter_runtime_available": runtime_available,
            "adapter_runtime_configured": runtime_configured,
            "runtime_status": runtime_status,
            "note": ("Adapter carregado no runtime local" if runtime_available
                     else "Runtime local configurado; carga do adapter sob demanda" if runtime_configured
                     else "Adapter LoRA treinado; runtime de inferência indisponível") if trained
                     else "Adapter LoRA V2 ausente nesta instância",
        },
    }


@router.get("/drenadata/points")
def drenadata_points() -> dict[str, object]:
    """IDs externos presentes no snapshot configurado, sem supor ponto físico."""
    try:
        data = _data()
    except SourceUnavailable as exc:
        raise _source_failure(exc) from exc
    return {
        "snapshot_at": data.snapshot_at.isoformat(),
        "data_origin": "synthetic",
        "point_ids": sorted({row.point_id for row in data.readings}),
    }


@router.get("/drenadata/points/{source_point_id}/latest", response_model=Evidence)
def latest_sensor_reading(source_point_id: str) -> Evidence:
    try:
        reading = _data().latest_reading(source_point_id)
    except SourceUnavailable as exc:
        raise _source_failure(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if reading is None:
        raise HTTPException(status_code=404, detail="Nenhuma leitura para este ID externo")
    return reading


@router.get("/drenadata/points/{source_point_id}/series", response_model=list[Evidence])
def sensor_series(
    source_point_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[Evidence]:
    try:
        return _data().reading_series(source_point_id, start=start, end=end)[-limit:]
    except SourceUnavailable as exc:
        raise _source_failure(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/drenadata/precipitation/history", response_model=list[Evidence])
def precipitation_history(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=168, ge=1, le=500),
) -> list[Evidence]:
    try:
        return _data().historical_precipitation(start=start, end=end)[-limit:]
    except SourceUnavailable as exc:
        raise _source_failure(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/drenavision/events", response_model=list[Evidence])
def vision_events(
    point_id: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Evidence]:
    try:
        with _vision() as client:
            return client.list_events(point_id=point_id, limit=limit, offset=offset)
    except SourceUnavailable as exc:
        raise _source_failure(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/drenavision/events/{event_id}", response_model=Evidence)
def vision_event(event_id: str) -> Evidence:
    try:
        with _vision() as client:
            event = client.get_event(event_id)
    except SourceUnavailable as exc:
        raise _source_failure(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if event is None:
        raise HTTPException(status_code=404, detail="Evento não encontrado na DrenaVision")
    return event


@router.post("/assistant/ask", response_model=AnswerResult, response_model_exclude={"raw_model_output"})
async def answer_endpoint(request: AnswerRequest) -> AnswerResult:
    """Agente de resposta V2: ferramentas de leitura e rascunho com revisão humana."""
    try:
        return await run_in_threadpool(
            answer_with_evidence,
            request,
            data_source=_data,
            vision_factory=_vision,
            inference_factory=InferenceClient,
        )
    except SourceUnavailable as exc:
        raise _source_failure(exc) from exc
    except InferenceClientError as exc:
        LOGGER.warning("Inferência V2 indisponível: %s", exc.error_type)
        raise HTTPException(status_code=503, detail="Modelo local de inferência indisponível") from exc
    except ValueError as exc:
        LOGGER.warning("Configuração de inferência V2 inválida")
        raise HTTPException(status_code=503, detail="Modelo local de inferência indisponível") from exc
