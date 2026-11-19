# DrenaAssist — agente local de operações da DrenaHub

O DrenaAssist responde a perguntas sobre inspeção e manutenção de drenagem, consultando documentos técnicos e, no modo agente, registros operacionais de demonstração. É o módulo de IA generativa da DrenaHub para a FIAP Global Solution 2026, disciplina *Generative AI for Engineering*. Este repositório corresponde à **etapa técnica**: implementação, execução, avaliação e evidências. O relatório acadêmico ABNT será preparado separadamente.

**Escopo:** o sistema organiza evidências e propõe verificações para revisão humana. Não controla bombas ou dispositivos, não altera ocorrências automaticamente e não afirma prever alagamentos. Todos os registros operacionais deste repositório são **sintéticos**.

## Três configurações

| Configuração | Contexto enviado à mesma LLM local | Acesso a registros operacionais |
|---|---|---|
| `baseline` | Somente pergunta e regras de formato | Não |
| `rag` | Pergunta e trechos documentais recuperados | Não |
| `agent` | Pergunta, trechos documentais e resultados de ferramentas de leitura escolhidas conforme a solicitação | Sim |

A especialização foi feita por contexto, recuperação e ferramentas. **Não houve treinamento ou ajuste dos pesos.** A comparação usa o mesmo modelo base e os mesmos parâmetros de geração; documentos e casos são versionados neste repositório.

## Tecnologia e dados

- Python 3.10, FastAPI, Pydantic, Pytest e Jupyter Notebook.
- Ollama 0.40.16 com `qwen2.5:3b-instruct` local para as três configurações: 3,1 bilhões de parâmetros, quantização Q4_K_M, digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`. Temperatura 0, semente 42, limite de 512 tokens previstos por chamada. `ollama show` apresenta **Qwen Research License Agreement**. O modelo é usado neste experimento acadêmico; os pesos não são redistribuídos. Uso comercial ou redistribuição exigem revisão do texto integral da licença.
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` local para embeddings; busca por produto interno de vetores normalizados, equivalente à similaridade cosseno. O índice NumPy é gerado em `base/index.npz` e recriado se a base ou o modelo de embeddings mudar.
- `base/chunks.jsonl`: 41 trechos em português, derivados de 9 documentos técnicos com URL e condição de uso. Consulte [FONTES.md](base/FONTES.md).
- `base/operational.json`: unidades, pontos, leituras, inspeções, ocorrências, manutenção e regra de prioridade fictícias. Os registros não entram no índice documental.

`requirements.txt` fixa as versões de dependências diretas e das bibliotecas de inferência observadas no ambiente de execução, incluindo PyTorch, Transformers e Hugging Face Hub. Isso reduz variações ao reproduzir o experimento, embora outros sistemas operacionais e drivers ainda possam precisar de ajustes locais.

O computador utilizado para esta execução tem Windows 11 Home build 26300, AMD Ryzen 7 5700X3D (8 núcleos/16 threads), 31,9 GiB de RAM e NVIDIA RTX 4060 (8.188 MiB de VRAM). Um teste real com resposta JSON retornou `{"resposta":"4"}`; o primeiro carregamento levou 77,48 s e uma chamada já aquecida 0,823 s. `ollama ps` informou 100% GPU nesse teste. Esses tempos são apenas de verificação inicial, não as latências da avaliação. Versões e resultados de execução estão em `docs/AMBIENTE.json`. Uma GPU acelera a inferência, mas o tempo em CPU pode ser maior; não há requisito mínimo comprovado para outros computadores.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `app/` | Cliente Ollama, busca, orquestração, ferramentas, contratos Pydantic e API |
| `base/` | Trechos documentais, fontes e dados operacionais sintéticos |
| `avaliacao/` | Gabaritos, metodologia, runner, respostas brutas, métricas, placar e erros |
| `notebooks/` | Experimento executado com saídas salvas |
| `tests/` | Testes automatizados |
| `docs/` | Auditoria do ambiente, integração, roteiro de vídeo e inventário |
| `entrega_local/` | Reservada à segunda etapa; integralmente ignorada pelo Git |

## Instalação no Windows PowerShell

Clone `https://github.com/Torugo0/drenahub-genai.git` (privado nesta etapa; o avaliador precisará de acesso até que o proprietário autorize torná-lo público). Execute na raiz do repositório. É necessário Python 3.10, acesso à internet na **primeira** instalação dos pacotes e do modelo de embeddings, e [Ollama para Windows](https://ollama.com/download/windows) instalado. Depois de baixar os modelos, as respostas avaliadas não usam provedores externos.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
ollama --version
ollama pull qwen2.5:3b-instruct
ollama list
```

Se o serviço Ollama não estiver ativo, abra outro terminal e execute `ollama serve`. A URL padrão é `http://127.0.0.1:11434`. Copie `.env.example` para `.env` se quiser configurar variáveis; o arquivo `.env` é ignorado pelo Git e deve ser carregado no ambiente do processo, pois este projeto não presume leitura automática dele pelo Python. No PowerShell:

```powershell
$env:DRENA_MODEL = 'qwen2.5:3b-instruct'
$env:DRENA_OLLAMA_URL = 'http://127.0.0.1:11434'
$env:DRENA_EMBEDDING_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
$env:DRENA_SIMILARITY_THRESHOLD = '0.60'
$env:DRENA_LLM_TIMEOUT_S = '120'
$env:DRENA_CORS_ORIGINS = 'http://localhost:5173,http://localhost:3000'
```

O primeiro carregamento do Sentence Transformers baixa o modelo de embeddings. Prepare e confira o índice com:

```powershell
python -c "from app.retrieval import Retriever; r=Retriever(); print(len(r.chunks), r.build_index().shape)"
```

## Executar API

```powershell
python -m uvicorn app.api:app --host 127.0.0.1 --port 8001
```

Em outro terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8001/assistant/configurations
Invoke-RestMethod http://127.0.0.1:8001/assistant/ask -Method Post -ContentType 'application/json' -Body (@{
  question = 'Por que a garagem A está com prioridade alta?'
  configuration = 'agent'
  location_id = 'GAR-A'
} | ConvertTo-Json) | ConvertTo-Json -Depth 12
Invoke-RestMethod http://127.0.0.1:8001/evaluation/results
```

O contrato detalhado, exemplos React e o mapeamento futuro com a Central, DrenaVision e DrenaData estão em [INTEGRACAO_CENTRAL.md](docs/INTEGRACAO_CENTRAL.md). A Central disponível no workspace ainda é um protótipo HTML/JavaScript isolado; não apresente sua tela como integração ativa.

Uma execução local registrada em `avaliacao/resultados/smoke_api.json` confirmou HTTP 200 em `GET /health` e em `POST /assistant/ask` com `baseline`, com JSON válido e o modelo local disponível. Esse ensaio de integração HTTP é separado do placar de 40 casos.

## Avaliar recuperação e as três configurações

`avaliacao/casos.json` contém 40 perguntas com gabaritos independentes da LLM: 20 de desenvolvimento e 20 finais. Inclui perguntas documentais, operacionais, multifuente, sem informação disponível e indutoras de alucinação. A seleção do limiar de busca usa apenas o conjunto de desenvolvimento. A fórmula é `recall@k = |G ∩ top-k| / |G|`, onde `G` é o conjunto de trechos relevantes do gabarito. A avaliação também mede rejeição das perguntas sem suporte documental.

```powershell
python -m avaliacao.run --phase all --fresh
```

O comando produz:

- `avaliacao/resultados/limiar.json`: candidatos e limiar selecionado;
- `aquecimento.json`: execução local inicial do índice e do modelo antes de medir respostas;
- `recuperacao_individual.json`, `recuperacao_individual.csv` e `recuperacao_resumo.json`: rankings e recall;
- `respostas_brutas.jsonl`: saída real de cada configuração para cada caso;
- `pontuacao_individual.json`, `placar.json` e `placar.md`: veredictos determinísticos e agregado;
- `manifesto.json` e `integridade_execucao.json`: hashes, configuração e verificação de 120 respostas, 40 por modo, mesmo digest do modelo e ausência de erro de execução.

O pré-aquecimento é medido separadamente para que os tempos do primeiro carregamento não distorçam a comparação de latência entre as três configurações. Nesta execução, `aquecimento.json` registrou 12.101,09 ms para embeddings/índice e 423,38 ms para a chamada inicial ao Ollama, com JSON bruto `{"ok": true}`.

### Recuperação medida em 19/11/2026

O limiar **0,60** foi selecionado somente no conjunto de desenvolvimento pela média entre recall@3 e rejeição de perguntas sem suporte, com desempate pelo maior limiar. A avaliação final permaneceu separada.

| Conjunto | Perguntas documentais com gabarito | Recall@1 médio | Recall@3 médio | Rejeição sem suporte |
|---|---:|---:|---:|---:|
| Desenvolvimento | 10 | 0,80 | 0,95 | 1/1 |
| Final | 10 | 0,55 | 0,60 | 2/2 |
| Total descritivo | 20 | 0,675 | 0,775 | 3/3 |

O desempenho de recuperação caiu no conjunto final. Em D16, D18 e D19, trechos pertinentes da OSHA/NWS ficaram abaixo do limiar e nenhum trecho foi enviado à LLM. O resultado evidencia a troca entre recuperar contexto e rejeitar perguntas sem suporte; não foi reajustado com os casos finais. Rankings individuais e escores estão em `avaliacao/resultados/recuperacao_individual.csv`.

### Placar medido das três configurações

O runner executou **120 respostas reais** (40 perguntas × 3 configurações) com o mesmo `qwen2.5:3b-instruct`. O pré-aquecimento ficou em arquivo separado. As latências abaixo são médias da chamada completa do assistente, em milissegundos. Uma correção no cálculo de citações do pré-chamado foi aplicada **apenas à pontuação** das mesmas 120 respostas brutas; não houve nova inferência nem mudança no gabarito para produzir esta tabela.
As 28 linhas em `avaliacao/resultados/diagnostico_antes_correcoes.jsonl` pertencem a um ensaio exploratório anterior às correções e não entram no placar final.

| Configuração | Corretas | Afirmações sem suporte detectadas | Recusas corretas | JSON bruto / resposta válidos | Citações válidas | Ferramentas corretas | Latência média |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 17,5% | 47,5% | 100% | 100% / 100% | 52,5% | — | 1.183 ms |
| RAG | 40,0% | 12,5% | 100% | 100% / 100% | 87,5% | — | 1.354 ms |
| RAG + agente | 57,5% | 12,5% | 100% | 100% / 100% | 87,5% | 90,0% | 1.688 ms |

O RAG elevou acertos em **22,5 pontos percentuais** sobre o baseline; entre 20 perguntas documentais, passou de 1 para 10 acertos. O agente acrescentou **17,5 pontos percentuais** sobre o RAG, sobretudo nas perguntas operacionais: 8/15 acertos contra 1/15 no RAG. Nas duas perguntas de múltiplas fontes, nenhuma configuração acertou. O agente também errou as duas perguntas categorizadas como sensor e as três que combinam ocorrência, sensor e inspeção. Em relação ao RAG, empatou em afirmações sem suporte detectadas e citações válidas, mas teve maior latência média. O ganho de acertos não elimina as lacunas por categoria. Veja o julgamento por caso em `avaliacao/resultados/pontuacao_individual.json` e a interpretação detalhada em [ANALISE.md](avaliacao/ANALISE.md).

`--fresh` inicia nova execução e substitui resultados prévios; sem a opção, o runner pode reutilizar linhas já gravadas para retomar uma execução interrompida. O comando pode demorar porque cada caso passa pelo modelo local. As definições e limites das métricas ficam em `avaliacao/METODOLOGIA.md`. O placar **não usa a própria LLM como juiz**. Padrões de fatos obrigatórios, recusas, fontes permitidas e ferramentas esperadas foram definidos nos gabaritos. A detecção automática de afirmações não sustentadas é uma medida limitada; casos ambíguos exigem revisão humana.

Consulte `avaliacao/erros.md` para cinco falhas reais, com vínculos às respostas brutas e correções propostas.

## Testes e notebook

```powershell
python -m pytest -q
```

Os testes verificam contratos, carregamento da base, índice, recuperação, recall, citações, recusas, ferramentas autorizadas, API, falha do Ollama e reprodutibilidade da avaliação. O número efetivamente aprovado deve ser conferido na saída do comando e em `docs/AMBIENTE.json`. Testes com cliente ou dados substitutos não equivalem às inferências reais salvas pelo runner.

Na auditoria local, a suíte final registrou **21 testes aprovados em 12,96 s**, incluindo a verificação da correção de citações do pré-chamado; a saída está em `avaliacao/resultados/testes_finais.txt`. `requirements.txt` fixa Pytest 8.4.2 porque a versão 9.2 falhou neste caminho OneDrive com caracteres acentuados.

`notebooks/experimentos.ipynb` contém as células e saídas salvas: modelo, base, busca, recall, resposta JSON, recusa, chamadas do agente, comparação, gráficos e cinco erros. Para recriá-lo e executá-lo após a avaliação, use:

```powershell
python -m ipykernel install --user --name drenaassist --display-name "DrenaAssist (.venv)"
python -m avaliacao.criar_notebook --execute
```

O script executa uma nova consulta real ao agente dentro do notebook e salva as saídas. Também é possível abrir o arquivo já gerado em Jupyter instalado no ambiente.
O notebook entregue foi executado: `avaliacao/resultados/notebook_qa.json` confirma 9/9 células de código com saída, nenhum erro, um gráfico PNG e o rastro real de três ferramentas.

## Limites e segurança

- A base documental é pequena e composta sobretudo de orientações norte-americanas. Ela não substitui normas locais, projeto hidráulico nem avaliação profissional do local.
- A ficha de bombas da EPA descreve estação elevatória de esgoto; qualquer transferência ao contexto de drenagem exige verificar o equipamento e o manual do fabricante.
- Leituras, inspeções e prioridades em `base/operational.json` foram criadas para comparação experimental. Não representam sensores ativos ou clientes.
- A DrenaVision possui API real em outro checkout, mas seus eventos não são importados automaticamente. A amostra da DrenaData também permanece separada. IDs da Central, DrenaVision, DrenaData e deste repositório não devem ser unidos por semelhança textual.
- Saídas do modelo podem variar e podem errar. Respostas sem evidência suficiente devem recusar. Um pré-chamado fica pendente de revisão humana.
- No ensaio real de prioridade da Garagem A, a LLM propôs `calls=[]`; o agente executou três consultas reais por **fallback determinístico** de evidências obrigatórias (`tool_selection_method: fallback_empty_plan+required_evidence`). Não atribuímos essa seleção à LLM. Uma versão inicial fez duas consultas amplas e trouxe registros de outros locais; o defeito foi corrigido para filtrar as ferramentas por `location_id: GAR-A`. Os dois rastros permanecem em `avaliacao/resultados/smoke_agent_initial.json` e `smoke_agent.json`.
- Este repositório não armazena credenciais, modelos grandes, documentos completos das fontes ou dados pessoais.

O [inventário de evidências](docs/INVENTARIO_EVIDENCIAS.md) relaciona cada critério da rubrica ao arquivo verificável. O [roteiro de vídeo](docs/VIDEO_ROTEIRO.md) indica as telas e as chamadas para uma demonstração sem respostas pré-fabricadas.
Com a API ativa em `127.0.0.1:8001`, `.\docs\demo_api.ps1` executa as quatro perguntas do roteiro e salva os retornos HTTP originais, um manifesto e as novas chamadas de ferramentas em uma pasta com horário sob `avaliacao/resultados/demo_api/`. Cada execução cria uma pasta própria e não substitui o benchmark.
Uma execução em 19/11/2026 salvou os cinco retornos em `avaliacao/resultados/demo_api/20261119T170438733Z/`: todos responderam HTTP 200; a segunda pergunta recusou, a terceira executou três ferramentas e a quarta gerou um pré-chamado. O manifesto preserva horários e latências observados.
