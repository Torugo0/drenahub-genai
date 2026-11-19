"""Run retrieval and model evaluations against fixed, human-authored gold cases.

Run from the repository root: python -m avaliacao.run --phase all
The runner writes raw model responses before computing its scoreboard. Existing
raw rows are reused on restart; use --fresh to discard them for a new run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metrics import aggregate, retrieval_recall, score_answer

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "avaliacao" / "casos.json"
CHUNKS = ROOT / "base" / "chunks.jsonl"
OUTPUT = ROOT / "avaliacao" / "resultados"
CONFIGURATIONS = ("baseline", "rag", "agent")
THRESHOLDS = [round(i / 20, 2) for i in range(20)]


def _runtime_metadata() -> dict[str, Any]:
    from app.ollama_client import OllamaClient
    from app.retrieval import DEFAULT_EMBEDDING_MODEL
    client = OllamaClient()
    result: dict[str, Any] = {
        "model": client.model,
        "ollama_base_url": client.base_url,
        "generation_options": {"temperature": 0, "seed": 42, "num_predict": 512},
        "embedding_model": os.getenv("DRENA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        "ollama_version": None,
        "model_digest": None,
        "model_size_bytes": None,
    }
    try:
        with urllib.request.urlopen(client.base_url + "/api/version", timeout=3) as response:
            result["ollama_version"] = json.load(response).get("version")
        with urllib.request.urlopen(client.base_url + "/api/tags", timeout=3) as response:
            for item in json.load(response).get("models", []):
                if item.get("name") == client.model:
                    result["model_digest"] = item.get("digest")
                    result["model_size_bytes"] = item.get("size")
                    break
    except (OSError, ValueError):
        pass
    return result


def _dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    cases = value["cases"] if isinstance(value, dict) else value
    ids = [item["id"] for item in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evaluation case IDs")
    for item in cases:
        if item["split"] not in {"dev", "final"}:
            raise ValueError(f"Invalid split in {item['id']}")
        for field in ("question", "category", "expected_answer", "required_facts", "refuse", "rationale"):
            if field not in item:
                raise ValueError(f"Missing {field} in {item['id']}")
    return cases


def _retriever() -> Any:
    from app.retrieval import Retriever
    return Retriever()


def _rank(retriever: Any, question: str) -> list[dict[str, Any]]:
    matches = retriever.search(question, top_k=3, threshold=None)
    return [{"chunk_id": match.chunk.chunk_id, "score": round(float(match.score), 6)} for match in matches]


def _retrieval_rows(cases: list[dict[str, Any]], retriever: Any) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        if not case.get("retrieval_eval", False):
            continue
        rows.append({
            "case_id": case["id"], "split": case["split"], "question": case["question"],
            "gold_chunk_ids": case.get("gold_chunks", []),
            "ranking": _rank(retriever, case.get("retrieval_question") or case["question"]),
        })
    return rows


def _retrieval_summary(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    supported, unsupported = [], []
    for row in rows:
        selected = [m["chunk_id"] for m in row["ranking"] if m["score"] >= threshold]
        if row["gold_chunk_ids"]:
            supported.append((retrieval_recall(selected, row["gold_chunk_ids"], 1),
                              retrieval_recall(selected, row["gold_chunk_ids"], 3)))
        else:
            unsupported.append(not selected)
    r1 = statistics.mean(x[0] for x in supported) if supported else None
    r3 = statistics.mean(x[1] for x in supported) if supported else None
    reject = statistics.mean(unsupported) if unsupported else None
    balanced = statistics.mean(v for v in (r3, reject) if v is not None)
    return {"threshold": threshold, "supported_n": len(supported),
            "unsupported_n": len(unsupported), "mean_recall_at_1": r1,
            "mean_recall_at_3": r3, "unsupported_rejection_rate": reject,
            "balanced_score": balanced}


def run_retrieval(cases: list[dict[str, Any]], out: Path) -> float:
    retriever = _retriever()
    rows = _retrieval_rows(cases, retriever)
    dev = [row for row in rows if row["split"] == "dev"]
    final = [row for row in rows if row["split"] == "final"]
    if not dev or not final:
        raise ValueError("Retrieval cases require dev and final splits")
    grid = [_retrieval_summary(dev, threshold) for threshold in THRESHOLDS]
    # Select on development queries only. Prefer a stricter threshold in ties.
    selected = max(grid, key=lambda x: (x["balanced_score"], x["threshold"]))
    threshold = selected["threshold"]
    _dump(out / "limiar.json", {
        "method": "Fixed threshold grid; maximize (mean recall@3 + no-support rejection)/2 on development cases; ties use higher threshold. Final cases never select the threshold.",
        "selected": selected, "development_grid": grid,
        "cases_sha256": _hash(CASES), "chunks_sha256": _hash(CHUNKS),
    })
    detailed = []
    for row in rows:
        ids = [match["chunk_id"] for match in row["ranking"] if match["score"] >= threshold]
        gold = row["gold_chunk_ids"]
        detailed.append({**row, "selected_threshold": threshold, "selected_chunk_ids": ids,
                         "recall_at_1": retrieval_recall(ids, gold, 1) if gold else None,
                         "recall_at_3": retrieval_recall(ids, gold, 3) if gold else None,
                         "unsupported_rejected": not ids if not gold else None})
    _dump(out / "recuperacao_individual.json", detailed)
    _dump(out / "recuperacao_resumo.json", {
        "formula": "recall@k = |gold_chunk_ids intersect selected top-k| / |gold_chunk_ids|",
        "threshold": threshold,
        "development": _retrieval_summary(dev, threshold),
        "final": _retrieval_summary(final, threshold),
        "all": _retrieval_summary(rows, threshold),
    })
    with (out / "recuperacao_individual.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "split", "question", "gold_chunk_ids", "ranking", "selected_chunk_ids", "recall_at_1", "recall_at_3", "unsupported_rejected"])
        writer.writeheader()
        for row in detailed:
            writer.writerow({key: json.dumps(row[key], ensure_ascii=False) if isinstance(row[key], list) else row[key] for key in writer.fieldnames})
    return threshold


def _ask(case: dict[str, Any], configuration: str, threshold: float) -> dict[str, Any]:
    from app.assistant import ask
    started = time.perf_counter()
    try:
        result = ask(case["question"], configuration=configuration,
                     location_id=case.get("location_id"), point_id=case.get("point_id"),
                     threshold=threshold)
        response = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        response.setdefault("metadata", {})["evaluation_wall_latency_ms"] = elapsed
        return {"response": response, "error": None}
    except Exception as exc:
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        return {"response": {"question": case["question"], "answer": "", "supported": False,
                             "refused": False, "sources": [], "reason": "Execution error",
                             "suggested_actions": [], "draft_work_order": None,
                             "metadata": {"latency_ms": elapsed}},
                "error": {"type": type(exc).__name__, "message": str(exc)}}


def run_answers(cases: list[dict[str, Any]], out: Path, *, fresh: bool = False,
                threshold: float,
                configurations: tuple[str, ...] = CONFIGURATIONS) -> dict[str, Any]:
    # Exclude one-time embedding/index and Ollama model loading from per-case
    # latency, then preserve this separate warm-up measurement.
    from app.ollama_client import OllamaClient
    from app.retrieval import get_retriever
    warm_started = time.perf_counter()
    get_retriever().search("inspeção de drenagem", top_k=1, threshold=None)
    embedding_warmup_ms = round((time.perf_counter() - warm_started) * 1000, 2)
    warm_raw, model_warmup_ms = OllamaClient().generate_json([
        {"role": "system", "content": "Responda apenas em JSON."},
        {"role": "user", "content": "Retorne {\"ok\": true}."},
    ])
    _dump(out / "aquecimento.json", {"embedding_and_index_ms": embedding_warmup_ms,
                                     "ollama_warmup_ms": round(model_warmup_ms, 2),
                                     "raw_model_output": warm_raw})
    raw_path = out / "respostas_brutas.jsonl"
    if fresh and raw_path.exists():
        raw_path.unlink()
    old = _read_jsonl(raw_path)
    expected_hash = _hash(CASES)
    expected_chunks_hash = _hash(CHUNKS)
    runtime = _runtime_metadata()
    if any(row.get("cases_sha256") != expected_hash or
           row.get("chunks_sha256") != expected_chunks_hash or
           row.get("model") != runtime["model"] or
           row.get("model_digest") != runtime["model_digest"] or
           row.get("threshold") != threshold for row in old):
        raise ValueError("Existing responses use another gold file, corpus, model, or threshold; rerun with --fresh")
    done = {(row["case_id"], row["configuration"]) for row in old}
    for case in cases:
        for configuration in configurations:
            if (case["id"], configuration) in done:
                continue
            outcome = _ask(case, configuration, threshold)
            _append(raw_path, {"case_id": case["id"], "split": case["split"],
                               "configuration": configuration, "cases_sha256": expected_hash,
                               "chunks_sha256": expected_chunks_hash, "model": runtime["model"],
                               "model_digest": runtime["model_digest"], "threshold": threshold,
                               "timestamp_utc": datetime.now(timezone.utc).isoformat(), **outcome})
            print(f"{case['id']} {configuration}: {'error' if outcome['error'] else 'saved'}", flush=True)
    raw = _read_jsonl(raw_path)
    actual_models = {row["response"].get("metadata", {}).get("model") for row in raw if row["response"].get("metadata", {}).get("model")}
    if len(actual_models) > 1:
        raise ValueError(f"Mixed LLM models in raw responses: {actual_models}")
    actual_thresholds = {row["response"].get("metadata", {}).get("similarity_threshold") for row in raw
                         if row["configuration"] != "baseline" and row["response"].get("metadata", {}).get("similarity_threshold") is not None}
    if actual_thresholds and actual_thresholds != {threshold}:
        raise ValueError(f"Mixed retrieval thresholds in raw responses: {actual_thresholds}")
    case_index = {case["id"]: case for case in cases}
    scored = []
    for row in raw:
        if row["configuration"] not in configurations:
            continue
        item = score_answer(case_index[row["case_id"]], row["response"], row["configuration"])
        item["execution_error"] = row["error"]
        if row["error"]:
            item["correct"] = False
            item["json_valid"] = False
        scored.append(item)
    _dump(out / "pontuacao_individual.json", scored)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        grouped[row["configuration"]].append(row)
    board = {name: aggregate(rows) for name, rows in grouped.items()}
    _dump(out / "placar.json", board)
    headings = ["configuração", "n", "corretas %", "afirmações sem suporte detectadas %",
                "recusas corretas %", "JSON válido %", "citações válidas %",
                "ferramentas corretas %", "latência média ms"]
    lines = ["# Placar das três configurações", "", "| " + " | ".join(headings) + " |",
             "| " + " | ".join("---" for _ in headings) + " |"]
    for name in CONFIGURATIONS:
        if name not in board:
            continue
        b = board[name]
        lines.append("| " + " | ".join(str(v if v is not None else "—") for v in
                     [name, b["n"], b["correct_pct"], b["unsupported_claim_detected_pct"],
                      b["correct_refusal_pct"], b["json_valid_pct"], b["valid_citation_pct"],
                      b["correct_tool_use_pct"], b["mean_latency_ms"]]) + " |")
    lines.extend(["", "Métricas determinísticas calculadas com `avaliacao/metrics.py` a partir de",
                  "`casos.json` e `resultados/respostas_brutas.jsonl`. Afirmações sem suporte",
                  "detectadas são um limite inferior: a inspeção humana de alegações livres",
                  "continua necessária. Latência inclui a chamada síncrona ao assistente.", ""])
    (out / "placar.md").write_text("\n".join(lines), encoding="utf-8")
    return board


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("retrieval", "answers", "all"), default="all")
    parser.add_argument("--fresh", action="store_true", help="discard previous raw answer rows")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    cases = load_cases()
    arguments.output.mkdir(parents=True, exist_ok=True)
    _dump(arguments.output / "manifesto.json", {
        "cases_sha256": _hash(CASES), "chunks_sha256": _hash(CHUNKS),
        "case_count": len(cases), "dev_count": sum(c["split"] == "dev" for c in cases),
        "final_count": sum(c["split"] == "final" for c in cases),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": _runtime_metadata(),
    })
    if arguments.phase in ("retrieval", "all"):
        print("retrieval threshold:", run_retrieval(cases, arguments.output), flush=True)
    if arguments.phase in ("answers", "all"):
        threshold_path = arguments.output / "limiar.json"
        if not threshold_path.exists():
            raise FileNotFoundError("Run --phase retrieval first to freeze the threshold")
        threshold_result = json.loads(threshold_path.read_text(encoding="utf-8"))
        if threshold_result["cases_sha256"] != _hash(CASES) or threshold_result["chunks_sha256"] != _hash(CHUNKS):
            raise ValueError("Threshold selection uses another gold file or corpus")
        threshold = float(threshold_result["selected"]["threshold"])
        print("answer scoreboard:", json.dumps(run_answers(cases, arguments.output,
                                                            fresh=arguments.fresh,
                                                            threshold=threshold), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
