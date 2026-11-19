"""Avalia o agente com o modelo treinado nas mesmas 40 perguntas do gabarito.

Usa o mesmo limiar de busca, o mesmo gabarito e as mesmas regras de pontuação
das três configurações. Grava em ``avaliacao/treinado/`` e não altera o placar
congelado em ``avaliacao/resultados/``. Requer o servidor
``treino/servidor_treinado.py`` ativo e o Ollama (o plano de ferramentas usa o
modelo base, como no agente).

Exemplo::

    python -m avaliacao.avaliar_treinado
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .metrics import aggregate, score_answer
from .run import CASES, CHUNKS, OUTPUT, _ask, _hash, _read_jsonl, load_cases

TRAINED_OUT = Path(__file__).resolve().parent / "treinado"
CONFIG = "agent_trained"


def main() -> None:
    from app.assistant import trained_model_client

    client = trained_model_client()
    if not client.available():
        raise SystemExit(f"Modelo treinado indisponível em {client.base_url}. Inicie treino/servidor_treinado.py.")
    threshold = json.loads((OUTPUT / "limiar.json").read_text(encoding="utf-8"))["selected"]["threshold"]
    cases = load_cases()
    TRAINED_OUT.mkdir(parents=True, exist_ok=True)
    raw_path = TRAINED_OUT / "respostas_brutas.jsonl"
    done = {row["case_id"] for row in _read_jsonl(raw_path)}
    for case in cases:
        if case["id"] in done:
            continue
        outcome = _ask(case, CONFIG, threshold)
        row = {"case_id": case["id"], "split": case["split"], "configuration": CONFIG,
               "cases_sha256": _hash(CASES), "chunks_sha256": _hash(CHUNKS), "threshold": threshold,
               "timestamp_utc": datetime.now(timezone.utc).isoformat(), **outcome}
        with raw_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{case['id']}: {'erro' if outcome['error'] else 'ok'}", flush=True)

    index = {case["id"]: case for case in cases}
    scored = []
    for row in _read_jsonl(raw_path):
        item = score_answer(index[row["case_id"]], row["response"], CONFIG)
        item["split"] = row["split"]
        item["execution_error"] = row["error"]
        if row["error"]:
            item["correct"] = False
            item["json_valid"] = False
        scored.append(item)
    (TRAINED_OUT / "pontuacao_individual.json").write_text(json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8")

    reference = [row for row in json.loads((OUTPUT / "pontuacao_individual.json").read_text(encoding="utf-8"))]
    split_of = {case["id"]: case["split"] for case in cases}
    board = {}
    for name, rows in (("agent", [r for r in reference if r["configuration"] == "agent"]), (CONFIG, scored)):
        summary = aggregate(rows)
        summary["final_correct"] = sum(1 for r in rows if split_of[r["case_id"]] == "final" and r["correct"])
        summary["final_n"] = sum(1 for r in rows if split_of[r["case_id"]] == "final")
        board[name] = summary
    changed = []
    agent_by_case = {r["case_id"]: r["correct"] for r in reference if r["configuration"] == "agent"}
    for row in scored:
        before, after = agent_by_case.get(row["case_id"]), row["correct"]
        if before != after:
            changed.append({"case_id": row["case_id"], "agente": before, "agente_treinado": after})
    board["mudancas_por_caso"] = changed
    board["errors"] = sum(1 for r in scored if r["execution_error"])
    (TRAINED_OUT / "placar.json").write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = {"agent": "Agente (modelo base)", CONFIG: "Agente treinado (LoRA)"}
    lines = ["# Agente base × agente treinado", "",
             "| configuração | corretas % | corretas no teste final | citações válidas % | ferramentas corretas % | recusas corretas % | tempo médio ms |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for name in ("agent", CONFIG):
        b = board[name]
        lines.append(f"| {labels[name]} | {b['correct_pct']} | {b['final_correct']}/{b['final_n']} | {b['valid_citation_pct']} | "
                     f"{b['correct_tool_use_pct']} | {b['correct_refusal_pct']} | {b['mean_latency_ms']} |")
    lines += ["", "Casos que mudaram de resultado:", ""]
    lines += [f"- {c['case_id']}: agente {'acertou' if c['agente'] else 'errou'}, treinado {'acertou' if c['agente_treinado'] else 'errou'}" for c in changed] or ["- nenhum"]
    (TRAINED_OUT / "placar.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
