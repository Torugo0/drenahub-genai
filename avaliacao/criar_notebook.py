"""Build and execute the evidence notebook from measured artifacts.

The notebook reads actual evaluation results and makes one new local agent
inference. It never inserts fabricated model output into saved cells.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks" / "experimentos.ipynb"


def build() -> nbformat.NotebookNode:
    cells = [
        new_markdown_cell(
            "# DrenaAssist — experimento executado\n\n"
            "FIAP Global Solution 2026. Comparação da mesma LLM local em três configurações: "
            "baseline, RAG e RAG com agente. Os registros operacionais são **sintéticos**. "
            "As tabelas abaixo leem artefatos gerados por `python -m avaliacao.run --phase all --fresh`; "
            "o exemplo de agente faz uma chamada nova ao Ollama local."
        ),
        new_code_cell(
            "from pathlib import Path\n"
            "import json\n"
            "import pandas as pd\n"
            "from IPython.display import display, JSON, Markdown\n"
            "ROOT = Path.cwd() if (Path.cwd() / 'base').exists() else Path.cwd().parent\n"
            "RESULTS = ROOT / 'avaliacao' / 'resultados'\n"
            "manifest = json.loads((RESULTS / 'manifesto.json').read_text(encoding='utf-8'))\n"
            "print('LLM local:', manifest['runtime']['model'])\n"
            "print('Ollama:', manifest['runtime']['ollama_version'])\n"
            "print('Digest:', manifest['runtime']['model_digest'])\n"
            "print('Geração:', manifest['runtime']['generation_options'])\n"
            "print('Embeddings:', manifest['runtime']['embedding_model'])\n"
            "print('Perguntas:', manifest['case_count'], '(desenvolvimento:', manifest['dev_count'], ', final:', manifest['final_count'], ')')"
        ),
        new_markdown_cell("## Base de conhecimento e recuperação\n\nCada linha do JSONL é um trecho com ID, URL, licença e data de acesso."),
        new_code_cell(
            "chunks = [json.loads(line) for line in (ROOT / 'base' / 'chunks.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]\n"
            "docs = pd.DataFrame(chunks).groupby(['document_id','title','source','license'], as_index=False).size().rename(columns={'size':'trechos'})\n"
            "print('Documentos:', docs.shape[0], 'Trechos:', len(chunks))\n"
            "display(docs[['document_id','title','source','trechos']])"
        ),
        new_code_cell(
            "from app.retrieval import Retriever\n"
            "retriever = Retriever()\n"
            "query = 'Qual critério de sedimento da EPA indica limpar uma caixa de captação?'\n"
            "hits = retriever.search(query, top_k=3, threshold=None)\n"
            "display(pd.DataFrame([{'rank': h.rank, 'chunk_id': h.chunk.chunk_id, 'similaridade': round(h.score,4), 'texto': h.chunk.text} for h in hits]))\n"
            "threshold = json.loads((RESULTS / 'limiar.json').read_text(encoding='utf-8'))\n"
            "print('Limiar escolhido somente em desenvolvimento:', threshold['selected']['threshold'])"
        ),
        new_markdown_cell("## Recall@1, recall@3 e rejeição\n\n`recall@k = |G ∩ top-k| / |G|`. Casos sem trecho relevante medem rejeição separadamente."),
        new_code_cell(
            "retrieval = json.loads((RESULTS / 'recuperacao_resumo.json').read_text(encoding='utf-8'))\n"
            "display(pd.DataFrame([{'conjunto': split, **retrieval[split]} for split in ('development','final','all')]))\n"
            "individual = pd.read_csv(RESULTS / 'recuperacao_individual.csv')\n"
            "display(individual[['case_id','split','recall_at_1','recall_at_3','unsupported_rejected']].head(12))"
        ),
        new_markdown_cell("## JSON real e recusa\n\nAs saídas abaixo vêm das chamadas salvas da mesma LLM local."),
        new_code_cell(
            "raw = [json.loads(line) for line in (RESULTS / 'respostas_brutas.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]\n"
            "valid = next((row for row in raw if row['configuration'] == 'rag' and row['case_id'].startswith('D') and row['response']['supported']), next(row for row in raw if row['configuration'] == 'rag'))\n"
            "print('Caso:', valid['case_id'], 'Saída JSON bruta da LLM:')\n"
            "print(valid['response']['metadata']['raw_model_output'])\n"
            "print('Resposta validada pela aplicação:')\n"
            "display(JSON(valid['response']))"
        ),
        new_code_cell(
            "refusal = next(row for row in raw if row['case_id'] in ('N04','N05') and row['configuration'] == 'agent')\n"
            "print('Caso sem suporte:', refusal['case_id'])\n"
            "display(JSON(refusal['response']))"
        ),
        new_markdown_cell("## Agente executando ferramentas reais\n\nNova inferência local, com plano e rastros retornados pelo assistente. As ferramentas só consultam registros sintéticos."),
        new_code_cell(
            "from app.assistant import ask\n"
            "agent_result = ask('Por que a Garagem A está com prioridade alta?', configuration='agent', location_id='GAR-A', threshold=threshold['selected']['threshold'])\n"
            "print('Ferramentas executadas:', agent_result.metadata['tools_called'])\n"
            "display(pd.DataFrame(agent_result.metadata['tool_trace']))\n"
            "display(JSON(agent_result.model_dump(mode='json')))"
        ),
        new_markdown_cell("## Placar comparativo medido"),
        new_code_cell(
            "import matplotlib.pyplot as plt\n"
            "board = json.loads((RESULTS / 'placar.json').read_text(encoding='utf-8'))\n"
            "scoreboard = pd.DataFrame.from_dict(board, orient='index')\n"
            "display(scoreboard)\n"
            "ax = scoreboard[['correct_pct','valid_citation_pct','correct_refusal_pct']].plot.bar(figsize=(9,4), ylim=(0,100), rot=0)\n"
            "ax.set_ylabel('percentual (%)')\n"
            "ax.set_xlabel('configuração')\n"
            "ax.set_title('Métricas determinadas por gabarito e IDs de fonte')\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
        new_markdown_cell("## Cinco falhas observadas e conclusão\n\nCada falha abaixo aponta para uma linha preservada em `respostas_brutas.jsonl`."),
        new_code_cell(
            "display(Markdown((ROOT / 'avaliacao' / 'erros.md').read_text(encoding='utf-8')))\n"
            "print('Conclusão experimental:')\n"
            "print('RAG simples versus baseline:', round(board['rag']['correct_pct'] - board['baseline']['correct_pct'],2), 'pontos percentuais em respostas corretas.')\n"
            "print('Agente versus RAG simples:', round(board['agent']['correct_pct'] - board['rag']['correct_pct'],2), 'pontos percentuais em respostas corretas.')\n"
            "print('Limite: regexes e IDs não provam que toda frase livre esteja correta; revisar alegações técnicas e operacionais antes de agir.')"
        ),
    ]
    return new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "DrenaAssist (.venv)", "language": "python", "name": "drenaassist"},
                                                  "language_info": {"name": "python", "version": "3.10"}})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    notebook = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if args.execute:
        from nbclient import NotebookClient
        client = NotebookClient(notebook, timeout=600, kernel_name="drenaassist",
                                resources={"metadata": {"path": str(ROOT)}})
        notebook = client.execute()
    nbformat.write(notebook, OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
