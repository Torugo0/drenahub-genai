"""Gera e executa ``notebooks/treino_central.ipynb`` a partir dos arquivos salvos.

Não treina nem chama modelos: lê os dados de treino, o histórico de perda, os
pesos do adaptador e o placar de ``avaliacao/treinado/``.

Exemplo::

    python treino/criar_notebook_central.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks" / "treino_central.ipynb"


def _md(text: str):
    import nbformat
    return nbformat.v4.new_markdown_cell(textwrap.dedent(text).strip())


def _code(text: str):
    import nbformat
    return nbformat.v4.new_code_cell(textwrap.dedent(text).strip())


def build():
    import nbformat
    cells = [
        _md("""
        # Treino da LLM da central (Qwen2.5-3B + QLoRA)

        Este notebook só lê arquivos salvos: dados de treino, histórico de perda, pesos do adaptador
        e o placar das 40 perguntas do gabarito. O treino rodou em `treino/train_lora.py` numa RTX 4060.
        """),
        _code("""
        import hashlib, json
        from pathlib import Path
        import numpy as np
        import matplotlib.pyplot as plt
        from IPython.display import Markdown, display
        from safetensors.numpy import load_file

        ROOT = Path.cwd().resolve()
        if not (ROOT / "treino").is_dir():
            ROOT = ROOT.parent
        DADOS = ROOT / "treino" / "dados_central"
        ADAPTER = ROOT / "treino" / "adapter_central"
        read = lambda p: json.loads(p.read_text(encoding="utf-8"))
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        """),
        _md("""
        ## 1. Dados de treino

        Prédio fictício próprio do treino (Garagem C, Garagem D e Doca Sul) e só os trechos de documentos
        que não são resposta de nenhuma pergunta avaliada. Os hashes conferem com o manifesto.
        """),
        _code("""
        manifest = read(DADOS / "manifest.json")
        for name, expected in manifest["sha256"].items():
            assert sha(DADOS / name) == expected, name
        rows = [json.loads(l) for l in (DADOS / "train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        from collections import Counter
        display(Markdown(f"Treino: **{manifest['counts']['train']}** exemplos, validação: **{manifest['counts']['dev']}**. "
                         f"Exemplos descartados por falta de evidência no contexto: {len(manifest['skipped'])}."))
        display(Markdown("| Família | Exemplos de treino |\\n|:--|--:|\\n" + "\\n".join(f"| {k} | {v} |" for k, v in sorted(Counter(r['family'] for r in rows).items()))))
        exemplo = next(r for r in rows if r["family"] == "prioridade")
        print("Pergunta e evidências (trecho):", exemplo["messages"][1]["content"][:600], "...")
        print("\\nResposta-alvo:", exemplo["messages"][2]["content"])
        """),
        _md("## 2. Treino: curva de perda e prova de que os pesos mudaram"),
        _code("""
        treino = read(ROOT / "treino" / "training_manifest_central.json")
        display(Markdown("| Item | Valor |\\n|:--|:--|\\n" + "\\n".join(f"| {k} | {treino[k]} |" for k in
                         ["model_id", "model_revision", "license", "method", "train_examples", "dev_examples", "epochs", "gpu", "elapsed_s"])))
        hist = read(ROOT / "treino" / "historico_treino_central.json")["log_history"]
        tr = [(h["step"], h["loss"]) for h in hist if "loss" in h]
        ev = [(h["step"], h["eval_loss"]) for h in hist if "eval_loss" in h]
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.plot(*zip(*tr), marker="o", label="treino"); ax.plot(*zip(*ev), marker="s", label="validação")
        ax.set_xlabel("passo"); ax.set_ylabel("perda"); ax.set_title("QLoRA · Qwen2.5-3B-Instruct"); ax.legend(); plt.tight_layout(); plt.show()
        pesos = load_file(str(ADAPTER / "adapter_model.safetensors"))
        b = [k for k in pesos if "lora_B" in k]
        alteradas = sum(bool(np.any(pesos[k] != 0)) for k in b)
        print(f"Matrizes lora_B diferentes de zero: {alteradas}/{len(b)} (o PEFT as cria zeradas)")
        assert alteradas == len(b) > 0
        """),
        _md("""
        ## 3. Agente base × agente treinado nas 40 perguntas do gabarito

        Mesmo limiar de busca, mesmo plano de ferramentas e mesmas regras de pontuação. Só a resposta
        final muda de modelo.
        """),
        _code("""
        placar = read(ROOT / "avaliacao" / "treinado" / "placar.json")
        nomes = {"agent": "Agente (base)", "agent_trained": "Agente treinado"}
        linhas = ["| Configuração | Corretas % | Teste final | Citações válidas % | Recusas corretas % | Tempo médio (s) |", "|:--|--:|--:|--:|--:|--:|"]
        for k in ("agent", "agent_trained"):
            p = placar[k]
            linhas.append(f"| {nomes[k]} | {p['correct_pct']} | {p['final_correct']}/{p['final_n']} | {p['valid_citation_pct']} | {p['correct_refusal_pct']} | {p['mean_latency_ms']/1000:.1f} |")
        display(Markdown("\\n".join(linhas)))
        display(Markdown("Casos que mudaram: " + (", ".join(f"{c['case_id']} ({'ganhou' if c['agente_treinado'] else 'perdeu'})" for c in placar["mudancas_por_caso"]) or "nenhum")))
        """),
        _code("""
        brutas = [json.loads(l) for l in (ROOT / "avaliacao" / "treinado" / "respostas_brutas.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        for caso in ("O01", "O10", "N04"):
            r = next(x for x in brutas if x["case_id"] == caso)["response"]
            print(f"{caso}: {r['question']}\\n  -> {r['answer']}\\n  fontes: {[s['source_id'] for s in r['sources']]}\\n")
        """),
    ]
    return nbformat.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})


def main() -> None:
    import nbformat
    from nbclient import NotebookClient

    notebook = build()
    NotebookClient(notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    sys.exit(main())
