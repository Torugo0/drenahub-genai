"""O conector lê evidências reais da API sem disparar inferência ou mídia."""

from datetime import datetime

import httpx
import pytest

from app.contracts import PointLink, PointRegistry, SourceUnavailable
from app.drenavision import DrenaVisionClient


def test_vision_url_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="sem credenciais"):
        DrenaVisionClient(base_url="http://demo:dummy@127.0.0.1:8000", registry=PointRegistry(version="test"))


EVENT_ID = "4de69061-a4f6-4da8-877f-d107f96ed71a"
OTHER_EVENT_ID = "86e08cb6-fbd8-4d83-8f18-5f5da3ec9728"


def _summary(**changes: object) -> dict[str, object]:
    event = {
        "event_id": EVENT_ID,
        "point_id": "garagem-a-ralo-1",
        "timestamp": "2026-11-19T14:15:00+00:00",
        "input_type": "image",
        "model_version": "pipeline-4c5c993223219929",
        "detection_count": 1,
        "detected_classes": ["obstrucao_visivel"],
        "max_confidence": 0.74,
        "inspection_recommended": True,
        "status": "revisao_recomendada",
        "evidence_uri": "4de69061-a4f6-4da8-877f-d107f96ed71a.jpg",
    }
    event.update(changes)
    return event


def _detail(**changes: object) -> dict[str, object]:
    event = _summary()
    event.pop("detection_count")
    event.pop("detected_classes")
    event.pop("max_confidence")
    event["detections"] = [
        {
            "class_id": 0,
            "class_name": "obstrucao_visivel",
            "confidence": 0.74,
            "bounding_box": [12.0, 18.0, 42.0, 66.0],
        }
    ]
    event.update(changes)
    return event


def _registry() -> PointRegistry:
    return PointRegistry(
        version="v2-links-1",
        links=(
            PointLink(
                source_system="drenavision",
                source_point_id="garagem-a-ralo-1",
                canonical_point_id="point-gar-a-01",
                verified_by="operador-teste",
                verified_at=datetime.fromisoformat("2026-11-19T10:00:00-03:00"),
            ),
        ),
    )


def test_list_events_preserves_source_and_explicit_point_link():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/vision/events"
        assert request.url.params["point_id"] == "garagem-a-ralo-1"
        assert request.url.params["limit"] == "5"
        assert request.url.params["offset"] == "0"
        return httpx.Response(200, json={"items": [_summary()], "total": 1})

    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(handler),
    ) as source:
        results = source.list_events(point_id="garagem-a-ralo-1", limit=5)

    assert len(results) == 1
    evidence = results[0]
    assert evidence.citation_id == f"drenavision:{EVENT_ID}"
    assert evidence.source_point_id == "garagem-a-ralo-1"
    assert evidence.canonical_point_id == "point-gar-a-01"
    assert evidence.observed_at.isoformat() == "2026-11-19T14:15:00+00:00"
    assert evidence.collected_at is None
    assert evidence.retrieved_at is not None
    assert evidence.retrieved_at.utcoffset().total_seconds() == 0
    assert evidence.data_origin == "unverified"
    assert evidence.review_status == "pending"
    assert evidence.facts["model_version"] == "pipeline-4c5c993223219929"
    assert evidence.facts["detected_classes"] == ["obstrucao_visivel"]
    assert evidence.collected_at is None
    assert evidence.retrieved_at is not None
    assert evidence.facts["status"] == "revisao_recomendada"
    assert evidence.facts["evidence_uri"] == f"{EVENT_ID}.jpg"
    assert evidence.facts["timestamp_scope"] == "analysis_time_not_capture_time"
    assert "risk" not in evidence.facts
    assert "confidence" not in evidence.facts
    assert evidence.source_uri == f"http://vision.local:8000/vision/events/{EVENT_ID}"


def test_empty_list_is_not_source_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/vision/events"
        return httpx.Response(200, json={"items": [], "total": 0})

    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=PointRegistry(version="empty"),
        transport=httpx.MockTransport(handler),
    ) as source:
        assert source.list_events(point_id="unmapped-point") == []


def test_invalid_point_id_is_rejected_before_http():
    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("ID inválido não deve ser enviado à DrenaVision")

    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(handler),
    ) as source:
        with pytest.raises(ValueError):
            source.list_events(point_id=" ")
        with pytest.raises(ValueError):
            source.list_events(point_id="x" * 81)


def test_detail_keeps_unmapped_point_unlinked_and_404_means_missing_record():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/vision/events/")
        assert request.method == "GET"
        if request.url.path.endswith(EVENT_ID):
            return httpx.Response(200, json=_detail(point_id="unmapped-point"))
        return httpx.Response(404, json={"detail": "Evento não encontrado"})

    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(handler),
    ) as source:
        evidence = source.get_event(EVENT_ID)
        missing = source.get_event(OTHER_EVENT_ID)

    assert evidence is not None
    assert evidence.canonical_point_id is None
    assert evidence.source_point_id == "unmapped-point"
    assert evidence.facts["detection_count"] == 1
    assert evidence.facts["detected_classes"] == ["obstrucao_visivel"]
    assert missing is None


@pytest.mark.parametrize(
    "payload",
    [
        {"items": [_summary(timestamp="2026-11-19T14:15:00")], "total": 1},
        {"items": [_summary(event_id="not-an-uuid")], "total": 1},
        {"items": [_summary(detected_classes=[])], "total": 1},
        {"items": [_summary(status="sem_deteccao")], "total": 1},
        {
            "items": [
                _summary(
                    status="revisao_recomendada",
                    detection_count=0,
                    detected_classes=[],
                    inspection_recommended=False,
                )
            ],
            "total": 1,
        },
        {"items": [{"event_id": EVENT_ID}], "total": 1},
    ],
)
def test_invalid_event_contract_is_not_silently_treated_as_empty(payload: object):
    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
    ) as source:
        with pytest.raises(SourceUnavailable):
            source.list_events(point_id="garagem-a-ralo-1")


def test_list_rejects_event_from_another_point():
    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json={"items": [_summary(point_id="other-point")], "total": 1}
            )
        ),
    ) as source:
        with pytest.raises(SourceUnavailable):
            source.list_events(point_id="garagem-a-ralo-1")


@pytest.mark.parametrize("status_code", [401, 404, 503])
def test_http_error_is_source_unavailable_not_empty(status_code: int):
    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(lambda _request: httpx.Response(status_code)),
    ) as source:
        with pytest.raises(SourceUnavailable):
            source.list_events(point_id="garagem-a-ralo-1")


def test_timeout_is_source_unavailable_not_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        timeout_s=0.1,
        transport=httpx.MockTransport(handler),
    ) as source:
        with pytest.raises(SourceUnavailable):
            source.list_events(point_id="garagem-a-ralo-1")


def test_invalid_detail_id_or_response_cannot_be_cited():
    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=_detail(event_id=OTHER_EVENT_ID))
        ),
    ) as source:
        with pytest.raises(SourceUnavailable):
            source.get_event(EVENT_ID)
        with pytest.raises(ValueError):
            source.get_event("../predict")


@pytest.mark.parametrize(
    "detail",
    [
        _detail(status="sem_deteccao"),
        _detail(status="revisao_recomendada", detections=[], inspection_recommended=False),
    ],
)
def test_detail_rejects_status_conflicting_with_detections(detail: dict[str, object]):
    with DrenaVisionClient(
        base_url="http://vision.local:8000",
        registry=_registry(),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=detail)
        ),
    ) as source:
        with pytest.raises(SourceUnavailable):
            source.get_event(EVENT_ID)
