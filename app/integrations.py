"""Adaptadores dos contratos publicados por modulos DrenaHub.

Nao conecta automaticamente a outros servicos: o experimento usa dados sinteticos.
"""

from datetime import datetime
from typing import Any


def normalize_drenavision_event(event: dict[str, Any]) -> dict[str, Any]:
    """Normaliza PredictionEvent de GET /vision/events/{event_id} do DrenaVision.

    Contrato de origem: event_id, point_id, timestamp, detections, status,
    evidence_uri. A deteccao automatica e preservada como observacao pendente
    de revisao humana, nunca como confirmacao de obstrucao.
    """
    required = {"event_id", "point_id", "timestamp", "detections", "status", "evidence_uri"}
    missing = required - event.keys()
    if missing:
        raise ValueError(f"Campos ausentes em PredictionEvent: {sorted(missing)}")
    datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
    if not isinstance(event["detections"], list):
        raise ValueError("detections deve ser lista")
    return {
        "external_event_id": str(event["event_id"]),
        "external_point_id": str(event["point_id"]) if event["point_id"] is not None else None,
        "timestamp": str(event["timestamp"]),
        "detections": event["detections"],
        "status": str(event["status"]),
        "evidence_uri": event["evidence_uri"],
        "reviewed_by_human": False,
        "source_system": "DrenaVision",
    }
