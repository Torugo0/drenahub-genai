"""Compara o checkpoint base e o adapter LoRA no holdout V2 congelado.

O conjunto final troca entidades e horários, mas compartilha templates com o
treino. Este experimento mede comportamento nesses templates; não mede RAG,
agente, generalização a documentos novos nem segurança operacional.

Uso no ambiente CUDA isolado::

    python -m lora.evaluate_lora \\
      --dataset /home/vitor/drenaassist-v2-train/dataset \\
      --adapter /home/vitor/drenaassist-v2-train/run/adapter \\
      --model-path /home/vitor/drenaassist-v2-train/model \\
      --output /home/vitor/drenaassist-v2-train/evaluation-1

O arquivo final nunca é usado em treino. Guarde as respostas brutas para
revisão humana: igualdade de campos não julga a veracidade do texto livre.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .train_lora import MODEL_ID, MODEL_REVISION


SCHEMA_KEYS = frozenset({
    "answer", "refused", "source_ids", "reason", "review_required", "data_origin",
})
METRICS = (
    "json_valid", "schema_valid", "refused_match", "source_ids_exact",
    "citations_supported", "data_origin_match", "review_required_match",
    "policy_fields_match", "answer_exact", "reason_exact",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: objeto JSON esperado")
    return value


def _rows(path: Path, split: str) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: exemplos ausentes ou inválidos")
    ids = [row.get("id") for row in rows]
    if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"{path}: IDs ausentes ou duplicados")
    for row in rows:
        messages = row.get("messages")
        if row.get("split") != split or not isinstance(row.get("family"), str):
            raise ValueError(f"{path}: split ou família inválidos")
        if not isinstance(messages, list) or [m.get("role") for m in messages] != ["system", "user", "assistant"]:
            raise ValueError(f"{path}: conversa inválida")
        if any(not isinstance(m.get("content"), str) for m in messages):
            raise ValueError(f"{path}: conteúdo inválido")
        if json.loads(messages[2]["content"]) != row.get("expected"):
            raise ValueError(f"{path}: gabarito e mensagem divergem")
    return rows


def verify_dataset(dataset: Path, adapter: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Exige hashes congelados e prova de que o adapter usou só train/dev."""
    data_manifest = _json_file(dataset / "manifest.json")
    train_manifest = _json_file(adapter.parent / "training_manifest.json")
    hashes = data_manifest.get("sha256", {})
    if set(hashes) != {"train.jsonl", "dev.jsonl", "final.jsonl"}:
        raise ValueError("Manifesto de dados sem os três hashes esperados")
    for filename, expected_hash in hashes.items():
        if _sha256(dataset / filename) != expected_hash:
            raise ValueError(f"Hash do dataset divergente: {filename}")
    if (train_manifest.get("train_sha256") != hashes["train.jsonl"]
            or train_manifest.get("dev_sha256") != hashes["dev.jsonl"]):
        raise ValueError("Adapter treinado com outro train/dev")
    if train_manifest.get("model_id") != MODEL_ID or train_manifest.get("model_revision") != MODEL_REVISION:
        raise ValueError("Checkpoint de treino diferente do checkpoint fixado")
    if not (adapter / "adapter_config.json").is_file():
        raise ValueError("Adapter LoRA ausente")
    split_rows = {name: _rows(dataset / f"{name}.jsonl", name) for name in ("train", "dev", "final")}
    id_sets = [{row["id"] for row in split_rows[name]} for name in ("train", "dev", "final")]
    if any(id_sets[i] & id_sets[j] for i, j in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("IDs de treino, desenvolvimento e final se sobrepõem")
    prompts = [{row["messages"][1]["content"] for row in split_rows[name]} for name in ("train", "dev", "final")]
    if any(prompts[i] & prompts[j] for i, j in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("Prompts de treino, desenvolvimento e final se sobrepõem")
    if len(split_rows["train"]) != train_manifest.get("train_examples") or len(split_rows["dev"]) != train_manifest.get("dev_examples"):
        raise ValueError("Contagem de exemplos divergente do treino")
    return split_rows["final"], {
        "dataset_manifest": data_manifest,
        "training_manifest": train_manifest,
    }


def parse_response(raw: str) -> dict[str, Any] | None:
    """Aceita somente o objeto JSON inteiro com esquema estrito."""
    try:
        parsed = _strict_json(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or set(parsed) != SCHEMA_KEYS:
        return None
    if (not isinstance(parsed["answer"], str) or not parsed["answer"].strip()
            or not isinstance(parsed["reason"], str) or not parsed["reason"].strip()
            or type(parsed["refused"]) is not bool
            or type(parsed["review_required"]) is not bool
            or parsed["data_origin"] not in {"real", "synthetic", "unverified"}):
        return None
    citations = parsed["source_ids"]
    if (not isinstance(citations, list)
            or any(not isinstance(item, str) or not item for item in citations)
            or len(citations) != len(set(citations))):
        return None
    return parsed


def _strict_json(raw: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Constante fora do JSON: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Chave JSON duplicada: {key}")
            result[key] = value
        return result

    return json.loads(raw.strip(), parse_constant=reject_constant, object_pairs_hook=reject_duplicate_keys)


def _evidence_ids(row: dict[str, Any]) -> set[str]:
    user = row["messages"][1]["content"]
    prefix = "CONTEXTO_JSON: "
    if not user.startswith(prefix) or "\nPERGUNTA: " not in user:
        raise ValueError(f"{row['id']}: contexto de entrada inválido")
    context = json.loads(user[len(prefix):].split("\nPERGUNTA: ", 1)[0])
    evidence = context.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError(f"{row['id']}: evidências inválidas")
    return {item["citation_id"] for item in evidence}


def score_case(row: dict[str, Any], raw: str) -> dict[str, Any]:
    """Campos verificáveis; exact text é diagnóstico, não juízo semântico."""
    try:
        _strict_json(raw)
        json_valid = True
    except (json.JSONDecodeError, TypeError, ValueError):
        json_valid = False
    response = parse_response(raw)
    expected = row["expected"]
    supported = _evidence_ids(row)
    flags: dict[str, bool] = {metric: False for metric in METRICS}
    flags["json_valid"] = json_valid
    flags["schema_valid"] = response is not None
    if response is not None:
        flags["refused_match"] = response["refused"] == expected["refused"]
        flags["source_ids_exact"] = set(response["source_ids"]) == set(expected["source_ids"])
        flags["citations_supported"] = set(response["source_ids"]).issubset(supported)
        flags["data_origin_match"] = response["data_origin"] == expected["data_origin"]
        flags["review_required_match"] = response["review_required"] == expected["review_required"]
        flags["policy_fields_match"] = all(flags[key] for key in (
            "refused_match", "source_ids_exact", "citations_supported",
            "data_origin_match", "review_required_match",
        ))
        flags["answer_exact"] = response["answer"] == expected["answer"]
        flags["reason_exact"] = response["reason"] == expected["reason"]
    predicted = set(response["source_ids"]) if response else set()
    required = set(expected["source_ids"])
    return {
        "id": row["id"], "family": row["family"], "flags": flags,
        "expected": expected, "parsed": response,
        "citation_counts": {
            "true_positive": len(predicted & required),
            "predicted": len(predicted),
            "required": len(required),
        },
    }


def _aggregate(details: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(details)
    passes = Counter(metric for detail in details for metric, passed in detail["flags"].items() if passed)
    tp = sum(detail["citation_counts"]["true_positive"] for detail in details)
    predicted = sum(detail["citation_counts"]["predicted"] for detail in details)
    required = sum(detail["citation_counts"]["required"] for detail in details)
    return {
        "cases": total,
        "metrics": {metric: {"passed": passes[metric], "total": total, "rate": passes[metric] / total} for metric in METRICS},
        "citation_precision_micro": tp / predicted if predicted else None,
        "citation_recall_micro": tp / required if required else None,
        "citation_counts": {"true_positive": tp, "predicted": predicted, "required": required},
    }


def score_predictions(rows: list[dict[str, Any]], predictions: dict[str, str]) -> dict[str, Any]:
    expected_ids = {row["id"] for row in rows}
    if set(predictions) != expected_ids:
        raise ValueError("Predições incompletas ou com IDs extras")
    details = [score_case(row, predictions[row["id"]]) for row in rows]
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detail in details:
        families[detail["family"]].append(detail)
    return {
        "overall": _aggregate(details),
        "by_family": {family: _aggregate(families[family]) for family in sorted(families)},
        "details": details,
    }


def _generate(model, tokenizer, rows: list[dict[str, Any]], output_path: Path, max_new_tokens: int) -> dict[str, str]:
    import torch
    from transformers import GenerationConfig

    model.eval()
    config = GenerationConfig(
        do_sample=False, num_beams=1, max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id,
        use_cache=True,
    )
    predictions: dict[str, str] = {}
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, row in enumerate(rows, 1):
            prompt = tokenizer.apply_chat_template(
                row["messages"][:2], tokenize=True, add_generation_prompt=True,
                return_tensors="pt",
            ).to("cuda:0")
            started = time.monotonic()
            with torch.inference_mode():
                generated = model.generate(
                    input_ids=prompt,
                    attention_mask=torch.ones_like(prompt),
                    generation_config=config,
                )
            raw = tokenizer.decode(generated[0, prompt.shape[1]:], skip_special_tokens=True)
            predictions[row["id"]] = raw
            record = {
                "id": row["id"], "family": row["family"], "raw": raw,
                "input_tokens": prompt.shape[1],
                "generated_tokens": generated.shape[1] - prompt.shape[1],
                "elapsed_s": round(time.monotonic() - started, 3),
            }
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            print(f"{output_path.name}: {index}/{len(rows)} {row['id']}", flush=True)
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Diretório train/dev/final/manifest.json")
    parser.add_argument("--adapter", type=Path, required=True, help="Diretório com adapter_config.json")
    parser.add_argument("--output", type=Path, required=True, help="Novo diretório de resultados")
    parser.add_argument("--model-path", default=MODEL_ID)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--include-adversarial", action="store_true", help="Executa seis probes manuais em seção separada")
    args = parser.parse_args()
    if args.max_new_tokens < 64 or args.max_new_tokens > 1024:
        parser.error("--max-new-tokens deve estar entre 64 e 1024")
    rows, provenance = verify_dataset(args.dataset, args.adapter)
    probes: list[dict[str, Any]] = []
    if args.include_adversarial:
        from .adversarial_probes import build_probes
        probes = build_probes()
    if args.output.exists():
        parser.error("Diretório de saída já existe; escolha outro para preservar resultados")

    import bitsandbytes
    import peft
    import torch
    import transformers
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA não está disponível")
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    args.output.mkdir(parents=True)
    run_manifest = {
        "experiment": "V2 base versus LoRA, mesmo prompt e checkpoint",
        "holdout_scope": "Entidades e horários novos nos mesmos seis templates; não prova generalização independente",
        "not_measured": ["RAG", "agente", "validade semântica do texto livre", "segurança operacional"],
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "model_path_used": args.model_path, "adapter": str(args.adapter),
        "final_sha256": provenance["dataset_manifest"]["sha256"]["final.jsonl"],
        "train_sha256": provenance["training_manifest"]["train_sha256"],
        "dev_sha256": provenance["training_manifest"]["dev_sha256"],
        "cases": len(rows), "seed": 42, "do_sample": False, "num_beams": 1,
        "adversarial_cases": len(probes),
        "max_new_tokens": args.max_new_tokens,
        "torch": torch.__version__, "transformers": transformers.__version__,
        "peft": peft.__version__, "bitsandbytes": bitsandbytes.__version__,
        "gpu": torch.cuda.get_device_name(0), "dtype": str(compute_dtype),
    }
    (args.output / "run_manifest.json").write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, revision=MODEL_REVISION, trust_remote_code=False)
    tokenizer.pad_token = tokenizer.eos_token
    quantization = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    base = AutoModelForCausalLM.from_pretrained(
        args.model_path, revision=MODEL_REVISION, quantization_config=quantization,
        device_map={"": 0}, dtype=compute_dtype, trust_remote_code=False,
        low_cpu_mem_usage=True,
    )
    base.config.use_cache = True
    baseline = _generate(base, tokenizer, rows, args.output / "base_predictions.jsonl", args.max_new_tokens)
    baseline_probes = (
        _generate(base, tokenizer, probes, args.output / "base_adversarial_predictions.jsonl", args.max_new_tokens)
        if probes else None
    )
    torch.cuda.empty_cache()
    adapted = PeftModel.from_pretrained(base, str(args.adapter), is_trainable=False)
    tuned = _generate(adapted, tokenizer, rows, args.output / "lora_predictions.jsonl", args.max_new_tokens)
    tuned_probes = (
        _generate(adapted, tokenizer, probes, args.output / "lora_adversarial_predictions.jsonl", args.max_new_tokens)
        if probes else None
    )
    results = {
        "limitations": run_manifest["not_measured"] + [run_manifest["holdout_scope"]],
        "base": score_predictions(rows, baseline),
        "lora": score_predictions(rows, tuned),
    }
    if probes:
        results["adversarial"] = {
            "scope": "Seis probes manuais: revisar texto livre e evidências; não somar ao holdout principal",
            "base": score_predictions(probes, baseline_probes),
            "lora": score_predictions(probes, tuned_probes),
        }
    (args.output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "base_policy_fields_match": results["base"]["overall"]["metrics"]["policy_fields_match"],
        "lora_policy_fields_match": results["lora"]["overall"]["metrics"]["policy_fields_match"],
        "results": str(args.output / "results.json"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
