"""Contratos operacionais e protecoes do assistente (LLM simulada nestes testes unitarios)."""

import json
from datetime import datetime

from fastapi.testclient import TestClient

from app.assistant import ask
from app.models import AskResponse
from app.ollama_client import OllamaError
from app.operational import OperationalStore, ToolNotAllowed


class FakeRetriever:
    def search(self, query, top_k=3, threshold=None):
        return []


class FakeClient:
    model = "test-local-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)

    def generate_json(self, messages):
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output, 1.0


def test_operational_data_is_synthetic_and_priorities_follow_rules():
    store = OperationalStore()
    assert store.data["synthetic"] is True
    for event in store.data["events"]:
        assert event["priority"] == store.calculated_priority(event["point_id"])
        for evidence_id in event["evidence_ids"]:
            evidence = next(row for collection in ("sensor_readings", "visual_inspections") for row in store.data[collection] if row["id"] == evidence_id)
            assert datetime.fromisoformat(evidence["timestamp"]) <= datetime.fromisoformat(event["opened_at"])
    assert store.point_id("GARAGEM_A_RALO_01") == "RALO-01"


def test_operational_events_and_readings_have_real_ids():
    store = OperationalStore()
    assert store.get_recent_events("GAR-A")[0]["id"] == "OC-001"
    assert store.get_sensor_readings("RALO-01")[0]["id"] == "LE-001"
    assert store.get_maintenance_queue("GAR-A")[0]["id"] == "OC-001"
    assert store.infer_ids("Existe obstrução no ralo 99?", None, None)[1] == "RALO-99"
    assert store.get_visual_inspections("RALO-99") == []
    assert {row["point_id"] for row in store.get_sensor_readings(location_id="GAR-A")} <= {"RALO-01", "CANALETA-02", "BOMBA-01"}
    assert {row["point_id"] for row in store.get_visual_inspections(location_id="GAR-A")} <= {"RALO-01", "CANALETA-02", "BOMBA-01"}
    try:
        store.infer_ids("Leitura do ralo 01 na garagem B", None, None)
    except ValueError:
        pass
    else:
        raise AssertionError("Ponto de outra localização foi aceito")


def test_unknown_tool_is_blocked():
    store = OperationalStore()
    try:
        store.call("delete_event", {"event_id": "OC-001"})
    except ToolNotAllowed:
        pass
    else:
        raise AssertionError("Ferramenta destrutiva foi aceita")


def test_agent_executes_tool_and_creates_draft_without_mutating_status(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    client = FakeClient([
        json.dumps({"calls": [{"name": "get_event", "arguments": {"event_id": "OC-001"}}]}),
        json.dumps({"answer": "OC-001 aguarda manutenção e tem prioridade alta.", "refused": False, "source_ids": ["OC-001"], "reason": "Ocorrência consultada.", "suggested_actions": ["Inspecionar a grelha e confirmar a obstrução."]}),
    ])
    store = OperationalStore()
    before = store.get_event("OC-001")[0]["status"]
    result = ask("Prepare um rascunho de ordem de serviço para OC-001", "agent", client=client, retriever=FakeRetriever(), store=store)
    assert isinstance(result, AskResponse)
    assert result.metadata["tools_called"] == ["get_event", "get_sensor_readings", "get_visual_inspections"]
    assert result.draft_work_order is not None
    assert result.draft_work_order.priority == "alta"
    assert result.draft_work_order.evidence_ids == ["OC-001", "LE-001", "IV-001"]
    assert result.draft_work_order.status == "rascunho_pendente_aprovacao_humana"
    assert store.get_event("OC-001")[0]["status"] == before
    logs = [json.loads(row) for row in (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert logs[0]["result_ids"] == ["OC-001"]
    assert [row["tool"] for row in logs] == ["get_event", "get_sensor_readings", "get_visual_inspections"]


def test_rag_refuses_operational_question_without_operational_records():
    client = FakeClient([json.dumps({"answer": "Há obstrução no Ralo 01.", "refused": False, "source_ids": [], "reason": "", "suggested_actions": []})])
    result = ask("Existe obstrução no ralo 01?", "rag", client=client, retriever=FakeRetriever())
    assert result.refused
    assert result.answer == "Não consta nos dados disponíveis."


def test_rag_rejects_citation_not_retrieved():
    client = FakeClient([json.dumps({"answer": "Inspecione periodicamente.", "refused": False, "source_ids": ["FAKE-001"], "reason": "", "suggested_actions": []})])
    result = ask("Como organizar a inspeção preventiva?", "rag", client=client, retriever=FakeRetriever())
    assert result.refused
    assert result.metadata["invalid_source_ids"] == ["FAKE-001"]


def test_invalid_json_and_ollama_failure_return_valid_refusal():
    invalid = ask("Qual o nível do sensor?", "baseline", client=FakeClient(["não é JSON"]))
    failed = ask("Qual o nível do sensor?", "baseline", client=FakeClient([OllamaError("offline")]))
    for result in (invalid, failed):
        assert result.refused
        assert result.metadata["error"]
        assert AskResponse.model_validate_json(result.model_dump_json()).refused


def test_agent_blocks_unlisted_name_from_llm_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    client = FakeClient([
        json.dumps({"calls": [{"name": "delete_event", "arguments": {"event_id": "OC-001"}}]}),
        json.dumps({"answer": "Sem evidência.", "refused": True, "source_ids": [], "reason": "Sem fonte.", "suggested_actions": []}),
    ])
    result = ask("Explique manutenção preventiva de drenagem", "agent", client=client, retriever=FakeRetriever())
    assert result.metadata["blocked_tool_names"] == ["delete_event"]
    assert result.metadata["tools_called"] == []
    assert not (tmp_path / "calls.jsonl").exists()


def test_agent_refuses_unsupported_numeric_sensor_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    client = FakeClient([
        json.dumps({"calls": [{"name": "get_sensor_readings", "arguments": {"point_id": "RALO-01"}}]}),
        json.dumps({"answer": "A última leitura foi 15 cm.", "refused": False, "source_ids": ["LE-001"], "reason": "Leitura consultada.", "suggested_actions": []}),
    ])
    result = ask("Qual a última leitura do sensor no ralo 01?", "agent", client=client, retriever=FakeRetriever())
    assert result.refused
    assert result.answer == "Não consta nos dados disponíveis."
    assert result.metadata["invalid_operational_claims"] == ["15 cm sem evidência"]


def test_agent_requires_cited_record_to_support_numeric_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    client = FakeClient([
        json.dumps({"calls": [{"name": "get_event", "arguments": {"event_id": "OC-001"}}]}),
        json.dumps({"answer": "A leitura foi 11,2 cm.", "refused": False, "source_ids": ["OC-001"], "reason": "Ocorrência consultada.", "suggested_actions": []}),
    ])
    result = ask("Qual a leitura da ocorrência OC-001?", "agent", client=client, retriever=FakeRetriever())
    assert result.refused
    assert result.metadata["invalid_operational_claims"] == ["11,2 cm sem evidência"]


def test_agent_overrides_wrong_point_from_model_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    client = FakeClient([
        json.dumps({"calls": [{"name": "get_sensor_readings", "arguments": {"point_id": "RALO-01"}}]}),
        json.dumps({"answer": "Sem leitura disponível.", "refused": True, "source_ids": [], "reason": "Sem registro para esse ponto.", "suggested_actions": []}),
    ])
    result = ask("Qual a leitura do sensor no ralo 99?", "agent", client=client, retriever=FakeRetriever())
    assert result.refused
    assert result.metadata["tool_trace"][0]["arguments"]["point_id"] == "RALO-99"
    assert result.metadata["tool_trace"][0]["result_count"] == 0


def test_agent_scopes_priority_evidence_to_requested_garage(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    client = FakeClient([
        json.dumps({"calls": []}),
        json.dumps({"answer": "A Garagem A tem prioridade alta por causa de LE-001 e IV-001.", "refused": False, "source_ids": ["OC-001", "LE-001", "IV-001"], "reason": "Registros consultados.", "suggested_actions": []}),
    ])
    result = ask("Por que a Garagem A está com prioridade alta?", "agent", client=client, retriever=FakeRetriever())
    assert not result.refused
    trace = result.metadata["tool_trace"]
    assert [row["tool"] for row in trace] == ["get_recent_events", "get_sensor_readings", "get_visual_inspections"]
    assert trace[1]["arguments"] == {"location_id": "GAR-A"}
    assert trace[2]["arguments"] == {"location_id": "GAR-A"}
    assert "LE-005" not in trace[1]["result_ids"]
    assert "IV-003" not in trace[2]["result_ids"]


def test_agent_queries_bomba_maintenance_even_when_planner_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    client = FakeClient([
        json.dumps({"calls": []}),
        json.dumps({"answer": "Não consta nos dados disponíveis.", "refused": True, "source_ids": [], "reason": "Sem manutenção registrada.", "suggested_actions": []}),
    ])
    result = ask("Existe manutenção concluída registrada para BOMBA-01?", "agent", client=client, retriever=FakeRetriever())
    assert result.refused
    assert result.metadata["tool_trace"][0]["tool"] == "get_maintenance_history"
    assert result.metadata["tool_trace"][0]["arguments"]["point_id"] == "BOMBA-01"
    assert result.metadata["tool_trace"][0]["result_count"] == 0


def test_api_contract_and_input_validation(monkeypatch):
    from app import api

    monkeypatch.setattr(api, "ask", lambda *args: AskResponse(question=args[0], answer="Não consta nos dados disponíveis.", supported=False, refused=True, reason="Sem dados."))
    client = TestClient(api.app)
    assert client.get("/assistant/configurations").status_code == 200
    assert client.post("/assistant/ask", json={"question": "x", "configuration": "rag"}).status_code == 422
    response = client.post("/assistant/ask", json={"question": "Pergunta válida", "configuration": "agent"})
    assert response.status_code == 200
    assert response.json()["refused"] is True


def test_drenavision_contract_adapter_rejects_incomplete_event():
    from app.integrations import normalize_drenavision_event

    event = {"event_id": "EV-1", "point_id": "GARAGEM_A_RALO_01", "timestamp": "2026-11-18T10:00:00Z", "detections": [], "status": "processed", "evidence_uri": None}
    assert normalize_drenavision_event(event)["reviewed_by_human"] is False
    event["point_id"] = None
    assert normalize_drenavision_event(event)["external_point_id"] is None
    try:
        normalize_drenavision_event({"event_id": "EV-1"})
    except ValueError:
        pass
    else:
        raise AssertionError("Contrato incompleto foi aceito")


class RecordingClient(FakeClient):
    def __init__(self, outputs, model):
        super().__init__(outputs)
        self.model = model
        self.calls = []

    def generate_json(self, messages):
        self.calls.append(messages)
        return super().generate_json(messages)


def test_trained_agent_plans_with_base_and_answers_with_trained_model(tmp_path, monkeypatch):
    monkeypatch.setenv("DRENA_TOOL_LOG_PATH", str(tmp_path / "calls.jsonl"))
    base = RecordingClient([json.dumps({"calls": [{"name": "get_sensor_readings", "arguments": {"point_id": "RALO-01"}}]})], "base")
    trained = RecordingClient([json.dumps({"answer": "A última leitura do RALO-01 foi 11,2 cm.", "refused": False, "source_ids": ["LE-001"], "reason": "Leitura consultada.", "suggested_actions": []})], "treinado")
    result = ask("Qual foi a última leitura do sensor no RALO-01?", "agent_trained", client=base, trained_client=trained, retriever=FakeRetriever(), store=OperationalStore())
    assert result.refused is False
    assert [s.source_id for s in result.sources] == ["LE-001"]
    assert result.metadata["configuration"] == "agent_trained"
    assert result.metadata["model"] == "treinado" and result.metadata["planner_model"] == "base"
    assert len(base.calls) == 1 and len(trained.calls) == 1
    # O modelo treinado recebe exatamente o prompt do agente, como no treino.
    assert "Configuração: agent." in trained.calls[0][1]["content"]
