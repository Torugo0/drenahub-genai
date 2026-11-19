"""Mescla o adaptador LoRA treinado no modelo base para importar no Ollama.

O Ollama não aplica mais adaptadores LoRA soltos. Por isso os pesos do
adaptador são somados aos pesos do modelo base (merge) e o resultado é salvo
em safetensors. O Ollama importa essa pasta e quantiza com
``ollama create -q q4_K_M``.

Exemplo::

    python -m treino.mesclar_adaptador --base Qwen/Qwen2.5-3B-Instruct \\
        --adapter treino/adapter --output modelo-treinado
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Pasta local ou ID do modelo base no Hugging Face")
    parser.add_argument("--revision", default=None, help="Revisão fixa do modelo base")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base = AutoModelForCausalLM.from_pretrained(args.base, revision=args.revision, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    merged = PeftModel.from_pretrained(base, str(args.adapter)).merge_and_unload()
    args.output.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(args.output), safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base, revision=args.revision).save_pretrained(str(args.output))
    print(f"Modelo mesclado salvo em {args.output}")


if __name__ == "__main__":
    main()
