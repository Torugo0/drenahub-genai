"""Treino QLoRA local e reproduzível, sem reutilizar o benchmark V1.

Uso no ambiente CUDA isolado do WSL2::

    python -m lora.train_lora --train train.jsonl --dev dev.jsonl \
        --output /home/vitor/drenaassist-v2-train/adapter

O script recusa exemplos marcados como teste/final e salva apenas o adapter,
tokenizer e um manifesto. Pesos do modelo-base permanecem fora do repositório.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path


MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_examples(path: Path, split: str) -> list[dict]:
    if split not in {"train", "dev"}:
        raise ValueError("Somente treino e desenvolvimento podem ser carregados")
    if any(term in path.name.lower() for term in ("final", "test", "holdout")):
        raise ValueError("Arquivo final/holdout não pode entrar no treino")
    examples: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        messages = row.get("messages")
        if row.get("split") != split or not isinstance(row.get("id"), str):
            raise ValueError(f"{path}:{line_number}: split ou ID inválido")
        if not isinstance(messages, list) or [message.get("role") for message in messages] != ["system", "user", "assistant"]:
            raise ValueError(f"{path}:{line_number}: conversa inválida")
        for message in messages:
            if not isinstance(message.get("content"), str) or not message["content"].strip():
                raise ValueError(f"{path}:{line_number}: conteúdo vazio")
        answer = json.loads(messages[-1]["content"])
        if not isinstance(answer, dict) or answer != row.get("expected"):
            raise ValueError(f"{path}:{line_number}: resposta e gabarito divergem")
        examples.append(row)
    if not examples:
        raise ValueError(f"{path}: nenhum exemplo")
    ids = [row["id"] for row in examples]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: IDs duplicados")
    return examples


def _assert_disjoint(train: list[dict], dev: list[dict]) -> None:
    train_ids = {row["id"] for row in train}
    dev_ids = {row["id"] for row in dev}
    train_prompts = {row["messages"][1]["content"] for row in train}
    dev_prompts = {row["messages"][1]["content"] for row in dev}
    if train_ids & dev_ids or train_prompts & dev_prompts:
        raise ValueError("Treino e desenvolvimento compartilham ID ou prompt")


class _TokenizedExamples:
    def __init__(self, examples: list[dict], tokenizer, max_length: int):
        self.rows: list[dict[str, list[int]]] = []
        for row in examples:
            messages = row["messages"]
            prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
            full = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
            if len(full) > max_length:
                raise ValueError(f"Exemplo {row['id']} tem {len(full)} tokens; máximo {max_length}")
            if full[: len(prefix)] != prefix or len(full) <= len(prefix):
                raise ValueError(f"Template de chat incompatível no exemplo {row['id']}")
            self.rows.append({
                "input_ids": full,
                "attention_mask": [1] * len(full),
                "labels": [-100] * len(prefix) + full[len(prefix) :],
            })

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, list[int]]:
        return self.rows[index]


class _Collator:
    def __init__(self, pad_token_id: int):
        self.pad_token_id = pad_token_id

    def __call__(self, features: list[dict[str, list[int]]]) -> dict:
        import torch

        length = max(len(feature["input_ids"]) for feature in features)
        return {
            "input_ids": torch.tensor([row["input_ids"] + [self.pad_token_id] * (length - len(row["input_ids"])) for row in features], dtype=torch.long),
            "attention_mask": torch.tensor([row["attention_mask"] + [0] * (length - len(row["attention_mask"])) for row in features], dtype=torch.long),
            "labels": torch.tensor([row["labels"] + [-100] * (length - len(row["labels"])) for row in features], dtype=torch.long),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Treina um adapter QLoRA para o DrenaAssist V2")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", default=MODEL_ID, help="Checkpoint HF local ou ID oficial")
    parser.add_argument("--max-length", type=int, default=768)
    parser.add_argument("--epochs", type=float, default=2.0)
    args = parser.parse_args()
    if args.max_length < 128 or args.epochs <= 0 or not math.isfinite(args.epochs):
        parser.error("max-length ou epochs inválido")
    train_rows = _load_examples(args.train, "train")
    dev_rows = _load_examples(args.dev, "dev")
    _assert_disjoint(train_rows, dev_rows)

    import bitsandbytes
    import peft
    import torch
    import transformers
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA não está disponível; nenhum treinamento foi executado")
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, revision=MODEL_REVISION, trust_remote_code=False)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    train_dataset = _TokenizedExamples(train_rows, tokenizer, args.max_length)
    dev_dataset = _TokenizedExamples(dev_rows, tokenizer, args.max_length)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        revision=MODEL_REVISION,
        quantization_config=quantization,
        device_map={"": 0},
        torch_dtype=compute_dtype,
        trust_remote_code=False,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    ))
    model.print_trainable_parameters()
    training_args = TrainingArguments(
        output_dir=str(args.output),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        optim="paged_adamw_8bit",
        bf16=compute_dtype == torch.bfloat16,
        fp16=compute_dtype == torch.float16,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        logging_steps=5,
        report_to="none",
        seed=42,
        data_seed=42,
        max_grad_norm=0.3,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=dev_dataset,
        data_collator=_Collator(tokenizer.pad_token_id),
    )
    train_metrics = trainer.train().metrics
    eval_metrics = trainer.evaluate()
    trainer.save_model(str(args.output / "adapter"))
    tokenizer.save_pretrained(str(args.output / "adapter"))
    manifest = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_path_used": args.model_path,
        "license": "Apache-2.0",
        "method": "QLoRA NF4, r=8, alpha=16, q/k/v/o projections",
        "train_examples": len(train_rows),
        "dev_examples": len(dev_rows),
        "train_sha256": _sha256(args.train),
        "dev_sha256": _sha256(args.dev),
        "max_length": args.max_length,
        "epochs": args.epochs,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "peft": peft.__version__,
        "bitsandbytes": bitsandbytes.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "dtype": str(compute_dtype),
        "elapsed_s": round(time.monotonic() - started, 2),
        "train_metrics": train_metrics,
        "eval_metrics": eval_metrics,
    }
    (args.output / "training_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps({"adapter": str(args.output / "adapter"), "manifest": str(args.output / "training_manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
