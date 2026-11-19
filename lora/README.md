# lora/ — treino QLoRA da LLM e agente V2 conectado

Aqui está o **treino real de pesos** do DrenaAssist e o agente que usa o modelo ajustado com dados da DrenaData e da DrenaVision. O resumo dos resultados está na seção 8 do [README principal](../README.md).

## O que foi treinado

| Item | Valor |
|---|---|
| Modelo base | [`Qwen/Qwen2.5-1.5B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct), revisão `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, Apache-2.0 |
| Método | QLoRA NF4, r=8, alpha=16, projeções q/k/v/o, bf16 |
| Dados | 84 treino / 18 validação / 24 final, congelados no commit `afd15fb` **antes** do treino; o teste V1 não foi usado |
| Hardware | RTX 4060 8 GB, WSL2, torch 2.8.0+cu128, transformers 4.57.1, peft 0.17.1, bitsandbytes 0.48.1 |
| Treino | 2 épocas, 42 passos, 97 s; perda de treino 0,624, perda de validação **0,436** |
| Saída | `adapter/adapter_model.safetensors` (8,7 MB, SHA-256 `fed4b6ce…07bf`); o checkpoint base não é redistribuído |

O que o modelo aprende: dada uma evidência (leitura sintética de sensor, evento de visão pendente, chuva histórica real, ausência de registro, fonte fora do ar ou IDs sem vínculo), responder em JSON com recusa, citação, origem e "requer revisão humana". As seis famílias vêm de templates determinísticos ([`training_data.py`](training_data.py)); 21 valores de chuva são observações reais Open-Meteo (CC BY 4.0).

## Arquivos

| Arquivo | Para quê |
|---|---|
| `dataset/` | `train.jsonl`, `dev.jsonl`, `final.jsonl` e `manifest.json` com hashes |
| `adapter/`, `training_manifest.json`, `artifact_manifest.json` | Pesos treinados, configuração, métricas e hashes |
| `train_lora.py` / `evaluate_lora.py` / `adversarial_probes.py` | Treino, avaliação base × LoRA e 6 perguntas fora do padrão |
| `resultados/piloto1/` | Respostas brutas e métricas da avaliação |
| `AUDITORIA_PILOTO1.md`, `ERROS_PILOTO1.md` | Revisão humana das 30 saídas e os 5 erros reais do LoRA |
| `criar_notebook.py` | Gera `notebooks/lora_qwen.ipynb` a partir dos resultados salvos (confere hashes) |
| `contracts.py`, `drenadata.py`, `drenavision.py` | Contrato de evidência e conectores somente leitura para a exportação Ouro da DrenaData e a API da DrenaVision |
| `response_agent.py`, `api.py`, `inference_*.py` | Agente V2, rotas `/v2/*` da API e serviço local que carrega base + adaptador |

## Reproduzir (Linux/WSL2 com CUDA)

```bash
uv venv --python 3.11 .venv-train
uv pip install --python .venv-train/bin/python torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv-train/bin/python transformers==4.57.1 peft==0.17.1 accelerate==1.11.0 bitsandbytes==0.48.1 'numpy<3' pydantic==2.11.10
# baixar o checkpoint na revisão fixa (huggingface_hub.snapshot_download) para $MODEL

PYTHON=.venv-train/bin/python
$PYTHON -m lora.train_lora --train lora/dataset/train.jsonl --dev lora/dataset/dev.jsonl --model-path "$MODEL" --output run1 --epochs 2 --max-length 768
$PYTHON -m lora.evaluate_lora --dataset lora/dataset --adapter run1/adapter --model-path "$MODEL" --output evaluation-2 --include-adversarial
```

O avaliador recusa dataset com hash diferente e não sobrescreve diretórios existentes. Para servir o modelo ajustado ao console `/v2/console`:

```bash
$PYTHON -m lora.inference_service   # escuta em 127.0.0.1:8765 (GET /health, POST /generate)
```

A API no Windows usa `DRENA_V2_INFERENCE_URL` (padrão `http://127.0.0.1:8765`). O cliente valida citações, origem e revisão pendente; se a saída não passar, devolve recusa protegida.

## Limites

O conjunto final troca IDs e horários, mas usa os mesmos seis templates do treino: mede comportamento, não generalização. JSON melhor (0/24 → 24/24) **não** significou menos invenção: 7/24 respostas tinham afirmação sem evidência, e 4 inventaram uma "última medição em 2023" com a fonte indisponível.
