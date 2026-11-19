# treino/ — como treinamos a LLM

Aqui ficam os dois treinos de pesos feitos pela equipe, com dados, scripts, histórico da perda e os adaptadores treinados. Os resultados estão na seção 9 do [README principal](../README.md).

| | Treino da central (atual) | Treino do agente conectado (primeiro) |
|---|---|---|
| Modelo base | `Qwen/Qwen2.5-3B-Instruct`, revisão `aa8e725`, Qwen Research License | `Qwen/Qwen2.5-1.5B-Instruct`, revisão `989aa79`, Apache-2.0 |
| Tarefa | A resposta final da central: pergunta + documentos + registros → JSON com fonte ou recusa | Evidência da DrenaData/DrenaVision → JSON com origem e revisão humana |
| Dados | `dados_central/`: 98 treino, 34 validação | `dados/`: 84 treino, 18 validação, 24 teste |
| Execução | 2 épocas, 50 passos, 220 s; validação 0,345 → 0,243 | 2 épocas, 42 passos, 97 s; validação 0,639 → 0,436 |
| Pesos | `adapter_central/` (14,8 MB) | `adapter/` (8,7 MB) |
| Histórico e manifesto | `historico_treino_central.json`, `training_manifest_central.json` | `historico_treino.json`, `training_manifest.json` |
| Onde roda | Modo "Agente treinado" da central | `/v2/console`, opção "Adaptado" |
| Avaliação | `avaliacao/treinado/` (40 perguntas do gabarito) | `avaliacao/lora/` (24 casos + 6 adversariais) |
| Notebook | `notebooks/treino_central.ipynb` | `notebooks/treino_lora.ipynb` |

Os dois usam QLoRA: o modelo base é carregado em 4 bits (NF4) e só os adaptadores LoRA (r=8, alpha=16, nas projeções q, k, v e o da atenção) são treinados, numa RTX 4060 de 8 GB.

## Como os dados da central foram feitos

[`dados_central.py`](dados_central.py) gera os exemplos. Cada um é a conversa exata que a central envia ao modelo, capturada do pipeline real: busca nos documentos, plano de ferramentas e consulta aos registros. Só o modelo é trocado por um capturador. A resposta-alvo é escrita por regra a partir dos dados, sem LLM.

Para não contaminar a avaliação:
- os registros vêm de um prédio fictício só do treino ([`operacional_treino.json`](dados_central/operacional_treino.json): Garagem C, Garagem D e Doca Sul, com IDs RALO-11, OC-101 etc.), diferente da base avaliada;
- só entram os 15 trechos de documentos que não são resposta de nenhuma das 40 perguntas do gabarito;
- o gerador recusa qualquer pergunta idêntica a uma pergunta avaliada;
- a validação usa outro local (Doca Sul) e outros trechos.

As respostas-alvo ensinam o que os erros do agente mostraram: citar o valor medido e o limite, listar ocorrências sem se contradizer, recusar quando o dado não existe (data sem leitura, nome de pessoa, previsão do tempo, pedido para inventar) e usar só IDs que aparecem nas evidências.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `dados_central.py`, `dados_central/` | Gerador e dados do treino da central |
| `training_data.py`, `dados/` | Gerador e dados do primeiro treino |
| `train_lora.py` | Script de treino (os dois treinos) |
| `adapter_central/`, `adapter/` | Os pesos treinados |
| `servidor_treinado.py` | Serve o 3B com o adaptador da central numa API igual à do Ollama (`/api/chat`, porta 8766) |
| `mesclar_adaptador.py` | Soma o adaptador ao modelo base e salva um modelo inteiro |
| `evaluate_lora.py`, `adversarial_probes.py`, `inference_service.py`, `inference_contracts.py` | Avaliação e serviço do primeiro treino |
| `criar_notebook_central.py`, `criar_notebook.py` | Geram os notebooks a partir dos arquivos salvos |
| `requirements.txt` | Dependências de treino e do servidor (GPU NVIDIA) |

## Por que um servidor próprio e não o Ollama

O Ollama 0.40 não aplica mais adaptadores LoRA ("LoRA adapters are no longer supported") e não importa o Qwen2 a partir de safetensors ("unsupported MLX architecture"). Por isso o `servidor_treinado.py` carrega o modelo com `transformers` + `peft` e responde no mesmo formato do Ollama. A central usa o mesmo cliente HTTP, só muda o endereço (`DRENA_TRAINED_URL`).

## Rodar o modelo treinado (GPU NVIDIA; Linux, WSL2 ou Windows com CUDA)

```bash
python -m venv .venv-treino && source .venv-treino/bin/activate
pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r treino/requirements.txt
python -m treino.servidor_treinado     # baixa o Qwen2.5-3B (6 GB) na primeira vez
```

Com o servidor ativo, a opção "Agente treinado" é liberada na central.

## Refazer o treino da central

```bash
python -m treino.dados_central         # no ambiente da central (.venv); gera treino/dados_central/
python -m treino.train_lora --train treino/dados_central/train.jsonl --dev treino/dados_central/dev.jsonl \
  --model-path Qwen/Qwen2.5-3B-Instruct --model-id Qwen/Qwen2.5-3B-Instruct \
  --model-revision aa8e72537993ba99e69dfaafa59ed015b17504d1 --license "Qwen Research License" \
  --output run-central --epochs 2 --max-length 3072
python -m avaliacao.avaliar_treinado   # com o servidor e o Ollama ativos
```

O primeiro treino se refaz com `python -m treino.train_lora --train treino/dados/train.jsonl --dev treino/dados/dev.jsonl --output run1`.
