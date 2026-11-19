"""Agente V2 não consulta LLM sem evidência e não publica saída inválida."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.contracts import Evidence, SourceUnavailable
from app.response_agent import AnswerRequest, _claim_issues, answer, gather_evidence
from treino.train_lora import MODEL_ID, MODEL_REVISION


def _evidence(review_status="not_applicable"):
    return Evidence(
        source_system="drenadata",
        kind="water_level",
        source_record_id="reading:fixture-1",
        source_point_id="EXTERNO-1",
        observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
        data_origin="synthetic",
        review_status=review_status,
        facts={"water_level_cm": 8.0, "unit": "cm"},
    )


def _request():
    return AnswerRequest(question="Qual é a leitura registrada?", source="drenadata_latest", source_point_id="EXTERNO-1")


def _generated(raw, mode="adapted", adapter_active=True):
    return SimpleNamespace(
        raw_output=raw, mode=mode, model_id=MODEL_ID,
        model_revision=MODEL_REVISION, adapter_active=adapter_active,
    )


def test_no_record_does_not_invoke_model():
    class Data:
        def latest_reading(self, point_id):
            return None

    result = answer(_request(), data_source=lambda: Data(), vision_factory=None,
                    inference_factory=lambda: (_ for _ in ()).throw(AssertionError("modelo não deve carregar")))
    assert result.status == "no_record"
    assert result.refused and not result.model_invoked


def test_unavailable_source_never_calls_model():
    def unavailable():
        raise SourceUnavailable("sem exportação")

    try:
        answer(_request(), data_source=unavailable, vision_factory=None,
               inference_factory=lambda: (_ for _ in ()).throw(AssertionError("modelo não deve carregar")))
    except SourceUnavailable:
        pass
    else:
        raise AssertionError("a falha da fonte deve continuar explícita")


def test_invalid_citation_is_guarded_refusal_with_raw_audit():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    class Model:
        def generate(self, messages, **kwargs):
            return _generated('{"answer":"A leitura foi de 8 cm.","refused":false,"source_ids":["fonte:inventada"],"reason":"Consulta","review_required":false,"data_origin":"synthetic"}')

    result = answer(_request(), data_source=lambda: Data(), vision_factory=None, inference_factory=Model)
    assert result.status == "guarded_refusal"
    assert result.refused
    assert result.source_ids == []
    assert result.validation_issues == ["citation_not_in_evidence"]
    assert "fonte:inventada" in result.raw_model_output


def test_valid_model_output_remains_human_review_draft():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    class Model:
        def generate(self, messages, **kwargs):
            assert "CONTEXTO_JSON" in messages[1]["content"]
            return _generated('{"answer":"O registro sintético informa 8 cm.","refused":false,"source_ids":["drenadata:reading:fixture-1"],"reason":"Consta no registro","review_required":false,"data_origin":"synthetic"}')

    result = answer(_request(), data_source=lambda: Data(), vision_factory=None, inference_factory=Model)
    assert result.status == "draft_requires_review"
    assert result.human_review_required
    assert result.source_ids == ["drenadata:reading:fixture-1"]


def test_rain_cannot_be_requested_by_ralo_id():
    try:
        AnswerRequest(question="Quanto choveu?", source="rain_history", source_point_id="RALO-01")
    except ValueError:
        pass
    else:
        raise AssertionError("a grade meteorológica não corresponde a um ralo")


def test_synthetic_physical_claim_is_blocked_even_with_valid_json():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    class Model:
        def generate(self, messages, **kwargs):
            return _generated('{"answer":"Ela é uma medição física de 8 cm.","refused":false,"source_ids":["drenadata:reading:fixture-1"],"reason":"Consta no registro","review_required":false,"data_origin":"synthetic"}')

    result = answer(_request(), data_source=lambda: Data(), vision_factory=None, inference_factory=Model)
    assert result.status == "guarded_refusal"
    assert "synthetic_claimed_physical" in result.validation_issues
    assert "synthetic_claimed_physical" not in _claim_issues("Não é uma medição física.", [_evidence()])


def test_unverified_point_link_is_refused_before_model():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    request = AnswerRequest(
        question="Esse ID pertence ao ponto CENTRAL-01?",
        source="drenadata_latest",
        source_point_id="EXTERNO-1",
    )
    result = answer(request, data_source=lambda: Data(), vision_factory=None,
                    inference_factory=lambda: (_ for _ in ()).throw(AssertionError("modelo não deve carregar")))
    assert result.status == "guarded_refusal"
    assert result.validation_issues == ["point_link_unverified"]
    assert not result.model_invoked


def test_requested_date_outside_latest_evidence_is_refused_before_model():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    request = AnswerRequest(
        question="Qual era a leitura em 2026-11-17?",
        source="drenadata_latest",
        source_point_id="EXTERNO-1",
    )
    result = answer(request, data_source=lambda: Data(), vision_factory=None,
                    inference_factory=lambda: (_ for _ in ()).throw(AssertionError("modelo não deve carregar")))
    assert result.status == "guarded_refusal"
    assert result.validation_issues == ["requested_time_not_in_evidence"]


def test_brazilian_requested_date_is_checked_before_model():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    request = AnswerRequest(
        question="Qual era a leitura em 15/01/2025?",
        source="drenadata_latest", source_point_id="EXTERNO-1",
    )
    result = answer(request, data_source=lambda: Data(), vision_factory=None,
                    inference_factory=lambda: (_ for _ in ()).throw(AssertionError("modelo não deve carregar")))
    assert result.validation_issues == ["requested_time_not_in_evidence"]
    assert not result.model_invoked


def test_vision_detection_count_cannot_validate_water_level_cm():
    vision = Evidence(
        source_system="drenavision", kind="vision_detection", source_record_id="event-1",
        source_point_id="CAM-1", observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
        data_origin="unverified", review_status="pending", facts={"detection_count": 2},
    )
    assert "unsupported_measurement" in _claim_issues("A água tem 2 cm no ponto.", [vision])


def test_runtime_mode_mismatch_is_blocked():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    class Model:
        def generate(self, messages, **kwargs):
            return _generated('{"answer":"O registro sintético informa 8 cm.","refused":false,"source_ids":["drenadata:reading:fixture-1"],"reason":"Consta no registro","review_required":false,"data_origin":"synthetic"}', mode="base", adapter_active=False)

    result = answer(_request(), data_source=lambda: Data(), vision_factory=None, inference_factory=Model)
    assert result.status == "guarded_refusal"
    assert {"runtime_model_mismatch", "adapter_not_active"}.issubset(result.validation_issues)


def test_valid_model_refusal_has_distinct_status():
    class Data:
        def latest_reading(self, point_id):
            return _evidence()

    class Model:
        def generate(self, messages, **kwargs):
            return _generated('{"answer":"Não posso concluir risco com essa leitura sintética.","refused":true,"source_ids":["drenadata:reading:fixture-1"],"reason":"A evidência é sintética","review_required":true,"data_origin":"synthetic"}')

    result = answer(_request(), data_source=lambda: Data(), vision_factory=None, inference_factory=Model)
    assert result.status == "model_refusal_requires_review"
    assert result.refused and result.human_review_required


def test_similar_but_longer_canonical_id_is_not_accepted():
    class Data:
        def latest_reading(self, point_id):
            return _evidence().model_copy(update={"canonical_point_id": "CENTRAL-01"})

    request = AnswerRequest(
        question="Este ponto pertence a CENTRAL-010?",
        source="drenadata_latest", source_point_id="EXTERNO-1",
    )
    result = answer(request, data_source=lambda: Data(), vision_factory=None,
                    inference_factory=lambda: (_ for _ in ()).throw(AssertionError("modelo não deve carregar")))
    assert result.validation_issues == ["point_link_unverified"]


def test_snapshot_date_cannot_be_claimed_as_observation_date():
    evidence = _evidence().model_copy(update={"snapshot_at": datetime(2026, 11, 19, tzinfo=timezone.utc)})
    assert "observation_date_mismatch" in _claim_issues("A medição foi de 8 cm em 19/11/2026.", [evidence])


def test_rain_date_uses_matching_history_instead_of_latest_row():
    first = Evidence(
        source_system="drenadata", kind="precipitation", source_record_id="rain:old",
        observed_at=datetime(2026, 11, 10, tzinfo=timezone.utc), data_origin="real",
        review_status="not_applicable", facts={"precipitation_mm": 1.0},
    )
    latest = first.model_copy(update={
        "source_record_id": "rain:new", "observed_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
    })

    class Data:
        def historical_precipitation(self):
            return [first, latest]

    request = AnswerRequest(question="Quanto choveu em 10/11/2026?", source="rain_history")
    assert gather_evidence(request, lambda: Data(), None) == [first]
