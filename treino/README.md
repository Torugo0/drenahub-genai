# treino/ — como treinamos a LLM local

Esta pasta contém o **treino real dos pesos** do DrenaAssist. O resumo e as provas estão na seção 8 do [README principal](../README.md). O teste do modelo treinado fica em [`avaliacao/lora/`](../avaliacao/lora/).

## O que foi treinado

| Item | Valor |
|---|---|
| Modelo base | [`Qwen/Qwen2.5-1.5B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct), revisão `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, Apache-2.0 |
| Método | QLoRA: modelo em 4 bits NF4 com adaptadores LoRA r=8, alpha=16 nas projeções q/k/v/o, bf16 |
| Dados | 84 treino / 18 validação / 24 teste, congelados no commit `afd15fb` **antes** do treino |
| Hardware | RTX 4060 8 GB, WSL2, torch 2.8.0+cu128, transformers 4.57.1, peft 0.17.1, bitsandbytes 0.48.1 |
| Execução | 2 épocas, 42 passos, 97 s; perda de treino 1,18 → 0,28; perda de validação 0,639 → **0,436** |
| Resultado | `adapter/adapter_model.safetensors` (8,7 MB, SHA-256 `fed4b6ce…07bf`); o modelo base não é redistribuído |

**O que o modelo aprende:** recebe uma evidência e responde em JSON com recusa, citação, origem do dado e "requer revisão humana". As evidências podem ser uma leitura sintética de sensor, um evento de visão pendente, chuva histórica real, ausência de registro, uma fonte fora do ar ou IDs sem vínculo. As seis famílias vêm de templates determinísticos ([`training_data.py`](training_data.py)). Os 21 valores de chuva são observações reais da Open-Meteo (CC BY 4.0).

## Arquivos

| Arquivo | Para quê |
|---|---|
| `dados/` | `train.jsonl`, `dev.jsonl`, `final.jsonl` (teste) e `manifest.json` com os hashes |
| `train_lora.py` | Script de treino |
| `historico_treino.json` | Perda a cada 5 passos e validação por época, salvo pelo Hugging Face Trainer |
| `training_manifest.json`, `artifact_manifest.json` | Versões, GPU, duração, perdas e hashes |
| `adapter/` | **Os pesos treinados** e a configuração LoRA |
| `evaluate_lora.py`, `adversarial_probes.py` | Teste antes × depois e 6 perguntas fora do padrão; as saídas ficam em `avaliacao/lora/` |
| `inference_service.py`, `inference_contracts.py` | Serviço local que carrega o modelo + adaptador para a rota `/v2/assistant/ask` |
| `criar_notebook.py` | Gera `notebooks/treino_lora.ipynb` a partir dos arquivos salvos (confere os hashes) |

## Refazer o treino (Linux/WSL2 com CUDA)

```bash
uv venv --python 3.11 .venv-train
uv pip install --python .venv-train/bin/python torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv-train/bin/python transformers==4.57.1 peft==0.17.1 accelerate==1.11.0 bitsandbytes==0.48.1 'numpy<3' pydantic==2.11.10 safetensors
# baixe o checkpoint na revisão fixa (huggingface_hub.snapshot_download) para $MODEL

PYTHON=.venv-train/bin/python
$PYTHON -m treino.train_lora --train treino/dados/train.jsonl --dev treino/dados/dev.jsonl --model-path "$MODEL" --output run1 --epochs 2 --max-length 768
$PYTHON -m treino.evaluate_lora --dataset treino/dados --adapter run1/adapter --model-path "$MODEL" --output avaliacao-nova --include-adversarial
$PYTHON -m treino.inference_service   # serve o modelo treinado em 127.0.0.1:8765
```

O avaliador recusa dados com hash diferente e não sobrescreve pastas existentes.

## Limite

O teste troca IDs e horários, mas usa os mesmos seis templates do treino. Ele mede comportamento, não generalização. O formato melhorou (JSON válido de 0/24 para 24/24), mas o modelo continuou inventando em 7/24 respostas.
