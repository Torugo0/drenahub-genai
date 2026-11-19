"""O notebook só aceita artefatos íntegros e salva saídas de células executadas."""

from __future__ import annotations

import json

import nbformat
import pytest

from lora.criar_notebook import ROOT, validate_sources, write_notebook
from lora.adversarial_probes import build_probes
from lora.evaluate_lora import score_predictions
from lora.training_data import build_examples, write_dataset


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _fixture(tmp_path):
    dataset_dir = tmp_path / "dataset"
    dataset_manifest = write_dataset(dataset_dir)
    actual_training = json.loads((ROOT / "lora" / "training_manifest.json").read_text(encoding="utf-8"))
    training_file = tmp_path / "training_manifest.json"
    _write_json(training_file, actual_training)

    adapter = tmp_path / "adapter"
    _write_json(adapter / "adapter_config.json", {"peft_type": "LORA", "r": 8, "lora_alpha": 16})
    (adapter / "adapter_model.safetensors").write_bytes(b"mock-for-integrity-test")

    results_dir = tmp_path / "results"
    final_rows = build_examples()["final"]
    probes = build_probes()
    run_manifest = {
        "train_sha256": dataset_manifest["sha256"]["train.jsonl"],
        "dev_sha256": dataset_manifest["sha256"]["dev.jsonl"],
        "final_sha256": dataset_manifest["sha256"]["final.jsonl"],
        "model_id": actual_training["model_id"],
        "model_revision": actual_training["model_revision"],
        "cases": len(final_rows),
        "adversarial_cases": len(probes),
    }
    _write_json(results_dir / "run_manifest.json", run_manifest)
    result = {}
    for model in ("base", "lora"):
        predictions = {row["id"]: json.dumps(row["expected"], ensure_ascii=False) for row in final_rows}
        probe_predictions = {row["id"]: json.dumps(row["expected"], ensure_ascii=False) for row in probes}
        result[model] = score_predictions(final_rows, predictions)
        result.setdefault("adversarial", {"scope": "fixture"})[model] = score_predictions(probes, probe_predictions)
        for name, rows, raw in (
            (f"{model}_predictions.jsonl", final_rows, predictions),
            (f"{model}_adversarial_predictions.jsonl", probes, probe_predictions),
        ):
            content = "".join(json.dumps({"id": row["id"], "family": row["family"], "raw": raw[row["id"]]}, ensure_ascii=False) + "\n" for row in rows)
            (results_dir / name).write_text(content, encoding="utf-8")
    _write_json(results_dir / "results.json", result)
    return training_file, dataset_dir, adapter, results_dir


def test_validator_recomputes_metrics_from_saved_raw_responses(tmp_path):
    files = _fixture(tmp_path)
    sources = validate_sources(*files)
    assert len(sources.final_rows) == 24
    assert sources.run_manifest["adversarial_cases"] == 6

    raw_path = files[3] / "lora_predictions.jsonl"
    records = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    records[0]["raw"] = "Saída alterada depois da avaliação"
    raw_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    with pytest.raises(ValueError, match="Métricas lora não correspondem"):
        validate_sources(*files)


def test_validator_rejects_modified_final_split(tmp_path):
    files = _fixture(tmp_path)
    with (files[1] / "final.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(ValueError, match="Hash do dataset divergente: final.jsonl"):
        validate_sources(*files)


def test_notebook_executes_read_only_cells_and_preserves_outputs(tmp_path):
    sources = validate_sources(*_fixture(tmp_path))
    output = tmp_path / "relatorio_v2.ipynb"
    write_notebook(sources, output)
    notebook = nbformat.read(output, as_version=4)
    nbformat.validate(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert len(code_cells) >= 7
    assert all(cell.execution_count is not None for cell in code_cells)
    assert sum(bool(cell.outputs) for cell in code_cells) >= 5
    assert not any(output.output_type == "error" for cell in code_cells for output in cell.outputs)
    combined = "\n".join(cell.source for cell in notebook.cells)
    assert "não treina nem chama modelos" in combined
    assert "não são somados ao placar principal" in combined
