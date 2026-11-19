"""Métricas e integridade do avaliador V2 sem carregar modelo/GPU."""

from __future__ import annotations

import json

import pytest

from lora.adversarial_probes import build_probes
from lora.evaluate_lora import (
    MODEL_ID,
    MODEL_REVISION,
    parse_response,
    score_case,
    score_predictions,
    verify_dataset,
)
from lora.training_data import build_examples, write_dataset


def _raw(expected: dict) -> str:
    return json.dumps(expected, ensure_ascii=False)


def test_strict_json_schema_rejects_fences_extra_fields_and_duplicate_citations():
    expected = build_examples()["final"][0]["expected"]
    assert parse_response(_raw(expected)) == expected
    assert parse_response("```json\n" + _raw(expected) + "\n```") is None
    assert parse_response(_raw({**expected, "risk_score": 99})) is None
    assert parse_response(_raw({**expected, "refused": 1})) is None
    assert parse_response(_raw({**expected, "source_ids": ["x", "x"]})) is None
    assert parse_response(_raw(expected)[:-1] + ',"refused":true}') is None
    assert parse_response(_raw(expected).replace('"review_required": false', '"review_required": NaN')) is None


def test_citation_support_is_not_the_same_as_required_citation():
    row = next(row for row in build_examples()["final"] if row["family"] == "unmapped_points")
    expected = row["expected"]
    assert score_case(row, _raw(expected))["flags"]["policy_fields_match"]

    # A evidência existe, mas a resposta correta recusa usá-la como vínculo.
    cited = {**expected, "source_ids": ["drenadata:reading:sem-vinculo-018"]}
    flags = score_case(row, _raw(cited))["flags"]
    assert flags["schema_valid"] and flags["citations_supported"]
    assert not flags["source_ids_exact"] and not flags["policy_fields_match"]

    forged = {**expected, "source_ids": ["drenadata:reading:inventado"]}
    flags = score_case(row, _raw(forged))["flags"]
    assert not flags["citations_supported"]


def test_invalid_response_counts_as_failure_for_every_field():
    row = build_examples()["final"][0]
    invalid = score_case(row, "Sem registro")
    assert not any(invalid["flags"].values())
    scalar = score_case(row, "42")
    assert scalar["flags"]["json_valid"]
    assert not scalar["flags"]["schema_valid"]


def test_summary_keeps_family_denominators_and_raw_answer_is_not_graded_semantically():
    rows = build_examples()["final"][:2]
    first = {**rows[0]["expected"], "answer": "Texto livre diferente"}
    results = score_predictions(rows, {rows[0]["id"]: _raw(first), rows[1]["id"]: "not JSON"})
    assert results["overall"]["cases"] == 2
    assert results["overall"]["metrics"]["policy_fields_match"] == {"passed": 1, "total": 2, "rate": 0.5}
    assert results["overall"]["metrics"]["answer_exact"]["passed"] == 0
    assert all(group["cases"] == 1 for group in results["by_family"].values())
    with pytest.raises(ValueError, match="incompletas"):
        score_predictions(rows, {rows[0]["id"]: _raw(first)})


def test_adapter_and_all_three_dataset_hashes_must_match(tmp_path):
    dataset = tmp_path / "dataset"
    manifest = write_dataset(dataset)
    adapter = tmp_path / "run" / "adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    training_manifest = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "train_examples": 84,
        "dev_examples": 18,
        "train_sha256": manifest["sha256"]["train.jsonl"],
        "dev_sha256": manifest["sha256"]["dev.jsonl"],
    }
    (adapter.parent / "training_manifest.json").write_text(json.dumps(training_manifest), encoding="utf-8")
    rows, provenance = verify_dataset(dataset, adapter)
    assert len(rows) == 24
    assert provenance["training_manifest"] == training_manifest

    with (dataset / "final.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(ValueError, match="Hash do dataset divergente: final.jsonl"):
        verify_dataset(dataset, adapter)


def test_adversarial_probes_are_separate_and_have_scannable_expected_fields():
    probes = build_probes()
    assert len(probes) == 6
    assert len({row["id"] for row in probes}) == 6
    training_rows = [row for split_rows in build_examples().values() for row in split_rows]
    assert {row["id"] for row in probes}.isdisjoint({row["id"] for row in training_rows})
    assert {row["question"] for row in probes}.isdisjoint({row["question"] for row in training_rows})
    assert all(row["split"] == "adversarial" for row in probes)
    assert all(score_case(row, _raw(row["expected"]))["flags"]["policy_fields_match"] for row in probes)
    assert any("Ignore o sistema" in row["messages"][1]["content"] for row in probes)
