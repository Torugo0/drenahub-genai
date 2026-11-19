"""Serve o Qwen2.5-3B com o adaptador LoRA treinado, imitando a API do Ollama.

A versão atual do Ollama não aceita adaptadores LoRA nem importa o Qwen2 a
partir de safetensors. Este servidor carrega o modelo base em 4 bits (como no
treino), aplica o adaptador de ``treino/adapter_central`` e responde em
``/api/chat`` e ``/api/tags``, no mesmo formato do Ollama. Assim a central usa
o mesmo cliente HTTP, apenas com outro endereço.

Requer GPU NVIDIA com CUDA e as bibliotecas do treino (torch, transformers,
peft, bitsandbytes). Exemplo, na raiz do repositório::

    python -m treino.servidor_treinado --model-path Qwen/Qwen2.5-3B-Instruct
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "treino" / "adapter_central"
MODEL_NAME = "drenaassist-treinado"
BASE_REVISION = "aa8e72537993ba99e69dfaafa59ed015b17504d1"


class TrainedModel:
    def __init__(self, model_path: str, adapter: Path):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        revision = None if Path(model_path).exists() else BASE_REVISION
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, revision=revision)
        quantization = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16
        )
        base = AutoModelForCausalLM.from_pretrained(
            model_path, revision=revision, quantization_config=quantization, device_map={"": 0}, dtype=torch.bfloat16
        )
        self.model = PeftModel.from_pretrained(base, str(adapter)).eval()
        self.lock = threading.Lock()

    def chat(self, messages: list[dict[str, str]], max_new_tokens: int) -> str:
        inputs = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True).to(self.model.device)
        with self.lock, self.torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=self.tokenizer.eos_token_id)
        text = self.tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text


def make_handler(model: TrainedModel):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/api/tags":
                self._send(200, {"models": [{"name": MODEL_NAME}]})
            else:
                self._send(404, {"error": "rota inexistente"})

        def do_POST(self) -> None:
            if self.path != "/api/chat":
                self._send(404, {"error": "rota inexistente"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    raise ValueError("corpo inválido")
                body = json.loads(self.rfile.read(length))
                messages = body["messages"]
                if not isinstance(messages, list) or not all(isinstance(m, dict) and isinstance(m.get("content"), str) for m in messages):
                    raise ValueError("messages inválido")
                max_new = int((body.get("options") or {}).get("num_predict", 512))
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})
                return
            content = model.chat(messages, max(16, min(max_new, 1024)))
            self._send(200, {"model": MODEL_NAME, "message": {"role": "assistant", "content": content}, "done": True})

        def log_message(self, *_args) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default="Qwen/Qwen2.5-3B-Instruct", help="Pasta local ou ID do modelo base")
    parser.add_argument("--adapter", type=Path, default=ADAPTER_PATH)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    model = TrainedModel(args.model_path, args.adapter)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(model))
    print(f"Modelo treinado pronto em http://{args.host}:{args.port} (nome: {MODEL_NAME})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
