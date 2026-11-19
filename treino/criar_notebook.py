"""Gera e executa um notebook V2 a partir de artefatos já produzidos.

Não carrega modelo, não treina e não gera novas respostas. Antes de escrever o
notebook, confere hashes, contagens e a correspondência entre respostas brutas
e métricas. As células são executadas com nbclient e suas saídas ficam salvas.

Exemplo::

    python treino/criar_notebook.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from treino.adversarial_probes import build_probes  # noqa: E402
from treino.evaluate_lora import score_predictions  # noqa: E402


@dataclass(frozen=True)
class Sources:
    training: Path
    dataset: Path
    adapter: Path
    results: Path
    final_rows: list[dict[str, Any]]
    training_manifest: dict[str, Any]
    dataset_manifest: dict[str, Any]
    run_manifest: dict[str, Any]
    evaluation: dict[str, Any]
    adapter_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: objeto JSON esperado")
    return data


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: JSONL vazio ou inválido")
    return rows


def _raw_predictions(path: Path, expected_rows: list[dict[str, Any]]) -> dict[str, str]:
    records = _jsonl(path)
    expected = {row["id"]: row["family"] for row in expected_rows}
    if len(records) != len(expected):
        raise ValueError(f"{path}: número de predições divergente")
    predictions: dict[str, str] = {}
    for record in records:
        case_id = record.get("id")
        if case_id not in expected or case_id in predictions or record.get("family") != expected[case_id]:
            raise ValueError(f"{path}: ID/família ausente, extra ou duplicado")
        if not isinstance(record.get("raw"), str):
            raise ValueError(f"{path}: resposta bruta ausente")
        predictions[case_id] = record["raw"]
    return predictions


def validate_sources(training: Path, dataset: Path, adapter: Path, results: Path) -> Sources:
    """Falha antes de gerar o notebook se qualquer evidência estiver incompleta."""
    training = training.resolve()
    dataset = dataset.resolve()
    adapter = adapter.resolve()
    results = results.resolve()
    training_manifest = _json(training)
    dataset_manifest = _json(dataset / "manifest.json")
    run_manifest = _json(results / "run_manifest.json")
    evaluation = _json(results / "results.json")
    hashes = dataset_manifest.get("sha256", {})
    if set(hashes) != {"train.jsonl", "dev.jsonl", "final.jsonl"}:
        raise ValueError("Manifesto do dataset não contém os três splits")
    for filename, expected in hashes.items():
        if _sha256(dataset / filename) != expected:
            raise ValueError(f"Hash do dataset divergente: {filename}")
    if (training_manifest.get("train_sha256") != hashes["train.jsonl"]
            or training_manifest.get("dev_sha256") != hashes["dev.jsonl"]):
        raise ValueError("Manifesto de treino não corresponde ao dataset")
    if (run_manifest.get("train_sha256") != hashes["train.jsonl"]
            or run_manifest.get("dev_sha256") != hashes["dev.jsonl"]
            or run_manifest.get("final_sha256") != hashes["final.jsonl"]):
        raise ValueError("Avaliação não corresponde ao dataset congelado")
    if (run_manifest.get("model_id") != training_manifest.get("model_id")
            or run_manifest.get("model_revision") != training_manifest.get("model_revision")):
        raise ValueError("Avaliação e treino usam checkpoints diferentes")
    if training_manifest.get("train_examples") != dataset_manifest.get("counts", {}).get("train"):
        raise ValueError("Contagem de treino divergente")
    if training_manifest.get("dev_examples") != dataset_manifest.get("counts", {}).get("dev"):
        raise ValueError("Contagem de desenvolvimento divergente")
    final_rows = _jsonl(dataset / "final.jsonl")
    if len(final_rows) != dataset_manifest.get("counts", {}).get("final"):
        raise ValueError("Contagem final divergente")
    weights = adapter / "adapter_model.safetensors"
    if not weights.is_file() or weights.stat().st_size == 0:
        raise ValueError("Pesos LoRA ausentes")
    config = _json(adapter / "adapter_config.json")
    if config.get("peft_type") != "LORA" or config.get("r") != 8 or config.get("lora_alpha") != 16:
        raise ValueError("Configuração do adapter divergente do treino")
    if not isinstance(training_manifest.get("train_metrics", {}).get("train_loss"), (float, int)):
        raise ValueError("Perda do treino ausente")
    if not isinstance(training_manifest.get("eval_metrics", {}).get("eval_loss"), (float, int)):
        raise ValueError("Perda da validação ausente")

    for model in ("base", "lora"):
        predictions = _raw_predictions(results / f"{model}_predictions.jsonl", final_rows)
        computed = score_predictions(final_rows, predictions)
        if computed != evaluation.get(model):
            raise ValueError(f"Métricas {model} não correspondem às respostas brutas")
        if run_manifest.get("cases") != len(final_rows):
            raise ValueError("Número de casos da execução divergente")

    if "adversarial" in evaluation:
        probes = build_probes()
        if run_manifest.get("adversarial_cases") != len(probes):
            raise ValueError("Número de probes divergente")
        for model in ("base", "lora"):
            predictions = _raw_predictions(results / f"{model}_adversarial_predictions.jsonl", probes)
            computed = score_predictions(probes, predictions)
            if computed != evaluation["adversarial"].get(model):
                raise ValueError(f"Métricas dos probes {model} não correspondem às respostas brutas")
    elif run_manifest.get("adversarial_cases", 0):
        raise ValueError("Probes declarados sem avaliação completa")

    return Sources(
        training, dataset, adapter, results, final_rows, training_manifest,
        dataset_manifest, run_manifest, evaluation, _sha256(weights),
    )


def _path_expression(path: Path) -> str:
    try:
        relative = path.relative_to(ROOT)
        return f"ROOT / {relative.as_posix()!r}"
    except ValueError:
        return f"Path({str(path)!r})"


def _code(source: str):
    import nbformat
    return nbformat.v4.new_code_cell(textwrap.dedent(source).strip())


def _markdown(source: str):
    import nbformat
    return nbformat.v4.new_markdown_cell(textwrap.dedent(source).strip())


def build_notebook(sources: Sources):
    """Células leem arquivos e recriam tabelas; nbclient salva saídas reais."""
    import nbformat

    training_expr = _path_expression(sources.training)
    dataset_expr = _path_expression(sources.dataset)
    adapter_expr = _path_expression(sources.adapter)
    results_expr = _path_expression(sources.results)
    notebook = nbformat.v4.new_notebook()
    notebook.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
    notebook.metadata.language_info = {"name": "python"}
    notebook.cells = [
        _markdown("""
        <div style="background:#102637;color:#fff;padding:28px 32px;border-radius:14px;border-left:8px solid #118f89">
          <div style="font-size:13px;letter-spacing:.15em;color:#8ce5d8">DRENAHUB · GENERATIVE AI FOR ENGINEERING</div>
          <h1 style="margin:10px 0 6px;color:#fff">DrenaAssist V2 · Treino e avaliação</h1>
          <div style="color:#d9e9ea">Evidências locais, comparação base × LoRA e análise dos limites do experimento</div>
        </div>

        Este notebook **não treina nem chama modelos**. Ele executa apenas leitura, verificação e apresentação
        dos artefatos registrados pelo treino e pela avaliação. Cada tabela abaixo é recalculada desses arquivos.
        """),
        _code(f"""
        from pathlib import Path
        import hashlib, html, json
        from IPython.display import display, HTML, Markdown
        import sys

        ROOT = Path.cwd().resolve()
        if not (ROOT / "treino" / "adapter").is_dir():
            ROOT = ROOT.parent
        assert (ROOT / "treino" / "adapter").is_dir(), "Abra o notebook no repositório DrenaAssist"
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from treino.evaluate_lora import score_predictions
        from treino.adversarial_probes import build_probes
        TRAINING_FILE = {training_expr}
        DATASET_DIR = {dataset_expr}
        ADAPTER_DIR = {adapter_expr}
        RESULTS_DIR = {results_expr}

        def read_json(path):
            return json.loads(path.read_text(encoding="utf-8"))
        def read_jsonl(path):
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        def sha256(path):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()

        training = read_json(TRAINING_FILE)
        dataset = read_json(DATASET_DIR / "manifest.json")
        run = read_json(RESULTS_DIR / "run_manifest.json")
        results = read_json(RESULTS_DIR / "results.json")
        final_rows = read_jsonl(DATASET_DIR / "final.jsonl")
        """),
        _markdown("""
        ## 1 · Integridade dos dados e dos artefatos

        O adapter foi ajustado com treino e desenvolvimento; o conjunto final só aparece na avaliação.
        Os hashes abaixo ligam os arquivos presentes aos manifestos de treino e execução.
        """),
        _code("""
        hashes = dataset["sha256"]
        for filename, expected_hash in hashes.items():
            assert sha256(DATASET_DIR / filename) == expected_hash, filename
        assert training["train_sha256"] == run["train_sha256"] == hashes["train.jsonl"]
        assert training["dev_sha256"] == run["dev_sha256"] == hashes["dev.jsonl"]
        assert run["final_sha256"] == hashes["final.jsonl"]
        assert len(final_rows) == run["cases"] == dataset["counts"]["final"]
        assert (ADAPTER_DIR / "adapter_model.safetensors").stat().st_size > 0
        lines = ["| Partição | Casos | SHA-256 |", "|:--|--:|:--|"]
        for split in ("train", "dev", "final"):
            lines.append(f"| {split} | {dataset['counts'][split]} | `{hashes[split + '.jsonl']}` |")
        lines.append(f"| Adapter LoRA | arquivo presente | `{sha256(ADAPTER_DIR / 'adapter_model.safetensors')}` |")
        display(Markdown("\\n".join(lines)))
        """),
        _markdown("""
        ## 2 · Ajuste de pesos realizado

        O registro abaixo vem do processo QLoRA concluído. `train_loss` e `eval_loss` medem a
        otimização do objetivo supervisionado; **não** são taxa de acerto ou prova de redução de alucinações.
        """),
        _code("""
        values = [
            ("Checkpoint", f"{training['model_id']} @ {training['model_revision']}"),
            ("Licença", training["license"]),
            ("Método", training["method"]),
            ("Exemplos de treino / desenvolvimento", f"{training['train_examples']} / {training['dev_examples']}"),
            ("Épocas", str(training["epochs"])),
            ("Perda de treino", f"{training['train_metrics']['train_loss']:.4f}"),
            ("Perda de desenvolvimento", f"{training['eval_metrics']['eval_loss']:.4f}"),
            ("Duração registrada", f"{training['elapsed_s']:.1f} s"),
            ("GPU", training["gpu"]),
            ("Bibliotecas", f"torch {training['torch']}; transformers {training['transformers']}; peft {training['peft']}"),
        ]
        display(Markdown("| Item | Valor |\\n|:--|:--|\\n" + "\\n".join(f"| {a} | {b} |" for a, b in values)))
        """),
        _markdown("""
        ### Prova de que os pesos foram treinados

        1. **Curva de perda**: `treino/historico_treino.json` é o `trainer_state.json` salvo pelo
           Hugging Face Trainer no passo 42. A perda cai a cada registro.
        2. **Pesos alterados**: o PEFT cria toda matriz `lora_B` com **zeros**. Se o treino não tivesse
           acontecido, o adaptador seria nulo. Abaixo contamos quantas matrizes `lora_B` deixaram de ser zero.
        """),
        _code("""
        import matplotlib.pyplot as plt
        import numpy as np
        from safetensors.numpy import load_file

        history = read_json(ROOT / "treino" / "historico_treino.json")["log_history"]
        train_points = [(h["step"], h["loss"]) for h in history if "loss" in h]
        eval_points = [(h["step"], h["eval_loss"]) for h in history if "eval_loss" in h]
        display(Markdown("| Passo | Perda de treino |\\n|--:|--:|\\n" + "\\n".join(f"| {s} | {l:.4f} |" for s, l in train_points)
                         + "\\n\\n**Perda de validação:** " + ", ".join(f"passo {s}: {l:.4f}" for s, l in eval_points)))
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.plot(*zip(*train_points), marker="o", label="treino")
        ax.plot(*zip(*eval_points), marker="s", label="validação")
        ax.set_xlabel("passo"); ax.set_ylabel("perda"); ax.set_title("QLoRA · Qwen2.5-1.5B-Instruct"); ax.legend()
        plt.tight_layout(); plt.show()

        weights = load_file(str(ROOT / "treino" / "adapter" / "adapter_model.safetensors"))
        lora_b = [name for name in weights if "lora_B" in name]
        changed = sum(bool(np.any(weights[name] != 0)) for name in lora_b)
        print(f"Matrizes lora_B diferentes de zero: {changed}/{len(lora_b)}")
        assert changed == len(lora_b) > 0
        """),
        _markdown("""
        ## 3 · Mesmo checkpoint, base × LoRA

        As duas configurações receberam os mesmos 24 prompts finais, sem amostragem. A métrica
        `policy_fields_match` exige simultaneamente JSON estrito, recusa, IDs de citação, origem e
        sinalização de revisão iguais ao gabarito. `answer_exact` é só coincidência literal de texto.
        As métricas abaixo **não julgam** se todo o texto livre é factual.
        """),
        _code("""
        raw = {}
        for model in ("base", "lora"):
            records = read_jsonl(RESULTS_DIR / f"{model}_predictions.jsonl")
            raw[model] = {record["id"]: record["raw"] for record in records}
            assert score_predictions(final_rows, raw[model]) == results[model]
        labels = {
            "schema_valid": "JSON + esquema válidos",
            "refused_match": "Decisão de recusa",
            "source_ids_exact": "Citações exatas",
            "citations_supported": "Citações dentro do contexto",
            "data_origin_match": "Origem dos dados",
            "review_required_match": "Revisão humana",
            "policy_fields_match": "Todos os campos verificados",
            "answer_exact": "Texto da resposta idêntico (diagnóstico)",
        }
        lines = ["| Campo verificado | Base | LoRA |", "|:--|--:|--:|"]
        for key, label in labels.items():
            entries = [results[model]["overall"]["metrics"][key] for model in ("base", "lora")]
            cells = [f"{value['passed']}/{value['total']} ({value['rate']:.1%})" for value in entries]
            lines.append(f"| {label} | {cells[0]} | {cells[1]} |")
        display(Markdown("\\n".join(lines)))
        """),
        _code("""
        lines = ["| Família | Casos | Base: todos os campos | LoRA: todos os campos |", "|:--|--:|--:|--:|"]
        for family, base_group in results["base"]["by_family"].items():
            tuned_group = results["lora"]["by_family"][family]
            b = base_group["metrics"]["policy_fields_match"]
            t = tuned_group["metrics"]["policy_fields_match"]
            lines.append(f"| `{family}` | {base_group['cases']} | {b['passed']}/{b['total']} | {t['passed']}/{t['total']} |")
        display(Markdown("**Por família**\\n\\n" + "\\n".join(lines)))
        """),
        _markdown("""
        ## 4 · Respostas brutas para inspeção

        A seleção abaixo é determinística: mostra primeiro até três falhas de campos do LoRA na ordem do
        conjunto final. Se não houver, mostra até três falhas da base. Compare a resposta inteira com o
        contexto antes de concluir que uma afirmação é segura.
        """),
        _code("""
        by_id = {row["id"]: row for row in final_rows}
        lora_errors = [d for d in results["lora"]["details"] if not d["flags"]["policy_fields_match"]]
        base_errors = [d for d in results["base"]["details"] if not d["flags"]["policy_fields_match"]]
        selected = (lora_errors or base_errors)[:3]
        display(Markdown(f"Falhas nos campos: **base {len(base_errors)}/{len(final_rows)}**, "
                         f"**LoRA {len(lora_errors)}/{len(final_rows)}**. Exibindo {len(selected)} caso(s)."))
        for detail in selected:
            row = by_id[detail["id"]]
            expected = json.dumps(row["expected"], ensure_ascii=False, indent=2)
            body = "".join(
                f"<h4>{html.escape(label)}</h4><pre style='white-space:pre-wrap'>{html.escape(value)}</pre>"
                for label, value in (
                    ("Gabarito", expected),
                    ("Base · saída bruta", raw["base"][row["id"]]),
                    ("LoRA · saída bruta", raw["lora"][row["id"]]),
                )
            )
            display(HTML(
                "<div style='border:1px solid #bedbd6;border-left:5px solid #118f89;"
                "border-radius:8px;padding:16px;margin:12px 0;background:#f8fcfb'>"
                f"<b>{html.escape(row['id'])}</b> · {html.escape(row['family'])}<br>"
                f"<small>{html.escape(row['question'])}</small>{body}</div>"
            ))
        """),
        _markdown("""
        ## 5 · Probes adversariais manuais

        Estes casos foram escritos separadamente dos templates do conjunto final e **não são somados ao placar principal**.
        Inspecione especialmente instruções dentro dos dados, observações antigas, detecção visual sem revisão,
        IDs parecidos, inferência de chuva e indisponibilidade da fonte. Os campos automáticos não substituem leitura humana.
        """),
        _code("""
        if "adversarial" not in results:
            display(Markdown("Os probes não foram executados nesta avaliação; nenhuma saída é apresentada."))
        else:
            probes = build_probes()
            probe_raw = {}
            for model in ("base", "lora"):
                records = read_jsonl(RESULTS_DIR / f"{model}_adversarial_predictions.jsonl")
                probe_raw[model] = {record["id"]: record["raw"] for record in records}
                assert score_predictions(probes, probe_raw[model]) == results["adversarial"][model]
            lines = ["| Probe | Base: campos | LoRA: campos |", "|:--|--:|--:|"]
            for row in probes:
                family = row["family"]
                cells = []
                for model in ("base", "lora"):
                    metric = results["adversarial"][model]["by_family"][family]["metrics"]["policy_fields_match"]
                    cells.append(f"{metric['passed']}/{metric['total']}")
                lines.append(f"| `{family}` | {cells[0]} | {cells[1]} |")
            display(Markdown("\\n".join(lines)))
            for row in probes:
                expected = json.dumps(row["expected"], ensure_ascii=False, indent=2)
                body = "".join(
                    f"<h4>{html.escape(label)}</h4><pre style='white-space:pre-wrap'>{html.escape(value)}</pre>"
                    for label, value in (
                        ("Gabarito de campos", expected),
                        ("Base · saída bruta", probe_raw["base"][row["id"]]),
                        ("LoRA · saída bruta", probe_raw["lora"][row["id"]]),
                    )
                )
                display(HTML(
                    "<div style='border:1px solid #d8e7e4;border-left:5px solid #176d7c;"
                    "border-radius:8px;padding:16px;margin:12px 0;background:#f8fcfb'>"
                    f"<b>{html.escape(row['id'])}</b><br><small>{html.escape(row['question'])}</small>{body}</div>"
                ))
        """),
        _markdown("""
        ## 6 · Limites e próximos testes

        - O conjunto final troca **IDs e horários**, mas mantém os seis templates do treino. O resultado não estima
          generalização para documentos, bairros, tarefas ou redações independentes.
        - Este notebook compara **modelo base vs. base + LoRA com contexto fornecido**. Não testa recuperação RAG,
          agente com ferramentas nem o placar A/B/C/D pedido para comparação completa.
        - Leituras de sensores e cenários visuais de treino são **sintéticos**. A chuva histórica citada vem da
          Open-Meteo, mas não demonstra alagamento em um ralo.
        - Igualdade de JSON e campos é uma verificação limitada. Afirmações livres, recusa fundamentada,
          rastreabilidade e cinco erros reais exigem revisão manual adicional com evidência e correção proposta.
        - Este experimento não estabelece prontidão para decisão automática de manutenção ou alerta público.
        """),
    ]
    return notebook


def write_notebook(sources: Sources, output: Path) -> Path:
    import nbformat
    from nbclient import NotebookClient

    notebook = build_notebook(sources)
    NotebookClient(
        notebook, timeout=120, kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute()
    nbformat.validate(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if any(cell.execution_count is None or any(item.output_type == "error" for item in cell.outputs) for cell in code_cells):
        raise RuntimeError("Notebook sem execução completa")
    if sum(bool(cell.outputs) for cell in code_cells) < 5:
        raise RuntimeError("Notebook sem saídas suficientes para auditoria")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    nbformat.write(notebook, temporary)
    temporary.replace(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-manifest", type=Path, default=ROOT / "treino" / "training_manifest.json")
    parser.add_argument("--dataset", type=Path, default=ROOT / "treino" / "dados")
    parser.add_argument("--adapter", type=Path, default=ROOT / "treino" / "adapter")
    parser.add_argument("--results", type=Path, default=ROOT / "avaliacao" / "lora")
    parser.add_argument("--output", type=Path, default=ROOT / "notebooks" / "treino_lora.ipynb")
    args = parser.parse_args()
    sources = validate_sources(args.training_manifest, args.dataset, args.adapter, args.results)
    output = write_notebook(sources, args.output.resolve())
    print(json.dumps({
        "notebook": str(output), "code_cells": sum(cell.cell_type == "code" for cell in __import__("nbformat").read(output, as_version=4).cells),
        "final_cases": len(sources.final_rows), "probes": sources.run_manifest.get("adversarial_cases", 0),
        "adapter_sha256": sources.adapter_sha256,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
