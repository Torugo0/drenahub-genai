"""Independent gold integrity, real embeddings, and evaluation arithmetic."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.retrieval import Retriever, load_chunks
from avaliacao.metrics import retrieval_recall, score_answer
from avaliacao import run
from avaliacao.run import load_cases


ROOT = Path(__file__).resolve().parents[1]


def test_gold_is_fixed_and_refs_exist():
    cases = load_cases()
    assert len(cases) == 40
    assert sum(case["split"] == "dev" for case in cases) == 20
    assert sum(case["split"] == "final" for case in cases) == 20
    assert sum(case["refuse"] for case in cases) >= 5
    chunk_ids = {chunk.chunk_id for chunk in load_chunks()}
    operational = json.loads((ROOT / "base/operational.json").read_text(encoding="utf-8"))
    operational_ids = {record["id"] for value in operational.values() if isinstance(value, list)
                       for record in value if isinstance(record, dict) and "id" in record}
    for case in cases:
        assert set(case.get("gold_chunks", [])) <= chunk_ids, case["id"]
        assert set(case.get("supporting_sources", [])) <= chunk_ids | operational_ids, case["id"]
        if case.get("retrieval_eval") and not case["refuse"]:
            assert case.get("gold_chunks"), case["id"]


def test_recall_uses_gold_denominator():
    found = ["X", "B", "A"]
    gold = ["A", "B"]
    assert retrieval_recall(found, gold, 1) == 0
    assert retrieval_recall(found, gold, 3) == 1
    assert retrieval_recall(["A", "X", "Y"], gold, 3) == 0.5
    with pytest.raises(ValueError):
        retrieval_recall(found, [], 3)


def test_fabricated_source_is_detected_even_with_correct_words():
    case = {"id": "CHECK", "required_facts": ["11[.,]2", "obstrucao"],
            "supporting_sources": ["LE-001", "IV-001"],
            "required_source_groups": [["LE-001"], ["IV-001"]],
            "required_tools": ["get_sensor_readings", "get_visual_inspections"],
            "allowed_tools": ["get_sensor_readings", "get_visual_inspections"],
            "refuse": False}
    response = {"answer": "11,2 cm e obstrução", "supported": True, "refused": False,
                "sources": [{"source_id": "LE-001"}, {"source_id": "INVENTADO"}],
                "metadata": {"tools_called": ["get_sensor_readings", "get_visual_inspections"]}}
    score = score_answer(case, response, "agent")
    assert score["correct"]
    assert not score["citation_valid"]
    assert score["unsupported_claim_detected"]
    assert score["invalid_source_ids"] == ["INVENTADO"]


def test_work_order_sources_count_as_citations():
    case = {"id": "DRAFT", "required_facts": ["RALO-01"],
            "supporting_sources": ["OC-001", "LE-001", "IV-001"],
            "required_source_groups": [["OC-001"], ["LE-001"], ["IV-001"]],
            "expect_draft": True, "refuse": False}
    response = {"answer": "Rascunho para RALO-01", "supported": True, "refused": False,
                "sources": [{"source_id": "OC-001"}],
                "draft_work_order": {"source_ids": ["OC-001", "LE-001", "IV-001"]},
                "metadata": {"retrieval": [], "tool_trace": [{"result_ids": ["OC-001", "LE-001", "IV-001"]}]}}
    score = score_answer(case, response, "agent")
    assert score["citation_valid"]
    assert score["correct"]


def test_final_queries_cannot_change_development_threshold(monkeypatch, tmp_path):
    cases = [
        {"id": "DEV-S", "split": "dev", "question": "supported", "gold_chunks": ["A"], "retrieval_eval": True},
        {"id": "DEV-N", "split": "dev", "question": "unsupported", "gold_chunks": [], "retrieval_eval": True},
        {"id": "FIN-S", "split": "final", "question": "final", "gold_chunks": ["A"], "retrieval_eval": True},
    ]
    def match(source_id, score):
        return SimpleNamespace(chunk=SimpleNamespace(chunk_id=source_id), score=score)
    class FakeRetriever:
        final_score = 0.2
        def search(self, question, top_k=3, threshold=None):
            if question == "supported":
                return [match("A", 0.7)]
            if question == "unsupported":
                return [match("X", 0.3)]
            return [match("A", self.final_score)]
    fake = FakeRetriever()
    monkeypatch.setattr(run, "_retriever", lambda: fake)
    first = run.run_retrieval(cases, tmp_path / "first")
    fake.final_score = 0.9
    second = run.run_retrieval(cases, tmp_path / "second")
    assert first == second


def test_real_local_embedding_index_and_ranking(tmp_path):
    retriever = Retriever(index_path=tmp_path / "index.npz")
    matrix = retriever.build_index()
    assert matrix.shape[0] == len(retriever.chunks) >= 25
    assert matrix.shape[1] >= 100
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=0.01)
    results = retriever.search("Como limpar sedimentos de caixa de captação?", top_k=3)
    assert len(results) == 3
    assert results[0].score >= results[1].score >= results[2].score
    assert all(row.chunk.chunk_id for row in results)
