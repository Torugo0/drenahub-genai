"""Geração supervisionada V2: splits, proveniência e respostas determinísticas."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from lora.training_data import (
    FAMILIES,
    SYSTEM_PROMPT,
    WEATHER_OBSERVATIONS,
    build_examples,
    write_dataset,
)


def _context(row):
    content = row["messages"][1]["content"]
    prefix, question = content.split("\nPERGUNTA: ", 1)
    assert prefix.startswith("CONTEXTO_JSON: ")
    assert question == row["question"]
    return json.loads(prefix.removeprefix("CONTEXTO_JSON: "))


def test_splits_have_disjoint_ids_questions_and_all_policy_families():
    splits = build_examples()
    assert {name: len(rows) for name, rows in splits.items()} == {"train": 84, "dev": 18, "final": 24}
    ids = [row["id"] for rows in splits.values() for row in rows]
    questions = [row["question"] for rows in splits.values() for row in rows]
    user_prompts = [row["messages"][1]["content"] for rows in splits.values() for row in rows]
    assert len(ids) == len(set(ids))
    assert len(questions) == len(set(questions))
    assert len(user_prompts) == len(set(user_prompts))
    for name, rows in splits.items():
        assert all(row["split"] == name for row in rows)
        assert Counter(row["family"] for row in rows) == {family: len(rows) // len(FAMILIES) for family in FAMILIES}
    assert len(WEATHER_OBSERVATIONS) == 21
    assert len({moment for moment, _ in WEATHER_OBSERVATIONS}) == 21


def test_assistant_json_has_fixed_schema_and_cites_only_supplied_evidence():
    for rows in build_examples().values():
        for row in rows:
            messages = row["messages"]
            assert [message["role"] for message in messages] == ["system", "user", "assistant"]
            assert messages[0]["content"] == SYSTEM_PROMPT
            expected = row["expected"]
            assert json.loads(messages[2]["content"]) == expected
            assert set(expected) == {"answer", "refused", "source_ids", "reason", "review_required", "data_origin"}
            assert isinstance(expected["answer"], str) and expected["answer"]
            assert isinstance(expected["refused"], bool)
            assert isinstance(expected["review_required"], bool)
            assert expected["data_origin"] in {"real", "synthetic", "unverified"}
            assert isinstance(expected["source_ids"], list)
            context = _context(row)
            evidence_ids = {item["citation_id"] for item in context["evidence"]}
            assert set(expected["source_ids"]).issubset(evidence_ids)
            assert all(source_id.startswith(("drenadata:", "drenavision:")) for source_id in expected["source_ids"])


def test_policy_examples_keep_origin_review_and_failure_states_distinct():
    examples = [row for rows in build_examples().values() for row in rows]
    for row in examples:
        expected = row["expected"]
        context = _context(row)
        family = row["family"]
        if family == "sensor_synthetic":
            assert expected["data_origin"] == "synthetic"
            assert "Não é uma medição física" in expected["answer"]
            assert context["evidence"][0]["data_origin"] == "synthetic"
        elif family == "vision_pending_review":
            assert expected["review_required"] is True
            assert "não foi confirmado por uma pessoa" in expected["answer"]
            assert context["evidence"][0]["review_status"] == "pending"
        elif family == "historical_rain":
            assert expected["data_origin"] == "real"
            assert "não confirma nível de água, obstrução ou risco" in expected["answer"]
            assert context["evidence"][0]["license"] == "CC BY 4.0"
            assert context["evidence"][0]["source_uri"].startswith("https://open-meteo.com/")
        elif family == "no_evidence":
            assert context["source_status"] == "available"
            assert context["evidence"] == []
            assert expected["answer"] == "Não consta nos dados disponíveis."
            assert expected["refused"] is True
        elif family == "source_unavailable":
            assert context["source_status"] == "unavailable"
            assert expected["answer"] != "Não consta nos dados disponíveis."
            assert "não significa que o registro não exista" in expected["reason"]
        elif family == "unmapped_points":
            assert context["point_registry_links"] == []
            assert context["evidence"][0]["canonical_point_id"] is None
            assert expected["refused"] and expected["review_required"]
            assert "Não há vínculo verificado" in expected["answer"]
        assert not re.search(r"alagamento confirmado|risco comprovado|monitoramos em tempo real|sensor físico ativo", expected["answer"], re.I)
        assert not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", messages_text(row))
        assert "responsavel_hash" not in messages_text(row)


def messages_text(row) -> str:
    return "\n".join(message["content"] for message in row["messages"])


def test_questions_do_not_repeat_v1_evaluation_prompts():
    # O arquivo V1 é lido apenas nesta asserção; o gerador não o importa.
    root = Path(__file__).resolve().parents[1]
    v1 = json.loads((root / "avaliacao" / "casos.json").read_text(encoding="utf-8"))
    v1_questions = {case["question"].strip().casefold() for case in v1["cases"]}
    v2_questions = {row["question"].strip().casefold() for rows in build_examples().values() for row in rows}
    assert v1_questions.isdisjoint(v2_questions)


def test_jsonl_and_manifest_are_byte_reproducible(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest_a = write_dataset(first)
    manifest_b = write_dataset(second)
    assert manifest_a == manifest_b
    assert manifest_a["counts"] == {"train": 84, "dev": 18, "final": 24}
    assert manifest_a["v1_evaluation_used_for_generation"] is False
    assert manifest_a["personal_data_used"] is False
    for filename, digest in manifest_a["sha256"].items():
        data_a = (first / filename).read_bytes()
        data_b = (second / filename).read_bytes()
        assert data_a == data_b
        assert hashlib.sha256(data_a).hexdigest() == digest
        rows = [json.loads(line) for line in data_a.decode("utf-8").splitlines()]
        assert len(rows) == manifest_a["counts"][filename.removesuffix(".jsonl")]
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
