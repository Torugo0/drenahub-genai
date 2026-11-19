# Inventário de evidências técnicas

Este inventário localiza as evidências da **etapa técnica**, executada em 19/11/2026. Os números abaixo apontam para seus arquivos de resultado; o relatório acadêmico ABNT pertence à segunda etapa.

| Requisito FIAP | Evidência e localização | Verificação |
|---|---|---|
| 1. Tarefa e gabarito, inclusive “não consta” | `avaliacao/casos.json`: 40 casos, 20 `dev` e 20 `final`, com respostas esperadas, fatos, fontes, justificativas e recusas | `python -m avaliacao.run --phase all --fresh` valida IDs e executa os casos |
| 2. Base em trechos com fontes | `base/chunks.jsonl`: 41 trechos e 9 documentos; `base/FONTES.md`: fonte, formato, condição de uso e contagem | Carregamento e IDs únicos em `app/retrieval.py`; testes em `tests/` |
| 3. Recall@1, recall@3 e limiar | `avaliacao/resultados/recuperacao_individual.json`, `recuperacao_individual.csv`, `recuperacao_resumo.json` e `limiar.json`; metodologia em `avaliacao/METODOLOGIA.md` | Medido: limiar 0,60 selecionado em `dev`; final com 10 perguntas suportadas, recall@1 0,55 e recall@3 0,60; rejeição sem suporte 2/2 no final |
| 4. JSON, citações e recusa | Respostas reais em `avaliacao/resultados/respostas_brutas.jsonl`; schema em `app/models.py`; ensaios em `avaliacao/resultados/smoke_rag.json` e `smoke_bomba_sem_registro.json`; métricas em `avaliacao/resultados/pontuacao_individual.json` | JSON bruto e resposta válidos em 100% das 120 execuções; RAG citou trechos EPA; consulta da BOMBA-01 sem registro retornou recusa canônica e fontes vazias |
| 5. Especialização por agente | Ferramentas de leitura em `app/operational.py`; orquestração em `app/assistant.py`; chamadas em `avaliacao/tool_calls.jsonl`; ensaios em `avaliacao/resultados/smoke_agent.json` e `smoke_ordem_servico.json`; registros sintéticos em `base/operational.json` | Consultas reais restritas a GAR-A; pré-chamado OC-001 produzido com prioridade, LE-001, IV-001 e aprovação humana pendente. Planejador retornou `calls=[]`; fallback executou ferramentas, identificado no rastro |
| 6. Placar de três configurações | `avaliacao/resultados/placar.json`, `placar.md`, `manifesto.json`, `integridade_execucao.json`, `aquecimento.json`, `avaliacao/ANALISE.md` e 120 linhas de respostas brutas | Acertos medidos: baseline 17,5%, RAG 40,0%, agente 57,5%. Afirmações sem suporte detectadas: 47,5%, 12,5%, 12,5%; citações válidas: 52,5%, 87,5%, 87,5% |
| 7. Cinco erros reais | `avaliacao/erros.md` com D01, D08, D10, O01 e O15, respostas observadas, causas e correções; provas em `respostas_brutas.jsonl` e rankings | Cinco falhas da execução final identificadas com linhas brutas e gabaritos, sem alterar casos finais para melhorar o placar |
| 8. README e reprodutibilidade | `README.md`, `requirements.txt`, `.env.example`, `docs/AMBIENTE.json`, notebook `notebooks/experimentos.ipynb` e testes em `tests/` | Comandos de instalação, avaliação, API, notebook e `pytest` no README |

## Evidências complementares

| Assunto | Arquivo | Estado |
|---|---|---|
| Hardware, Ollama, modelo local e inferência JSON inicial | `docs/AMBIENTE.json` | Registrado: qwen2.5:3b-instruct via Ollama 0.40.16, resposta real e tempos frio/aquecido |
| Pré-aquecimento antes de medir o placar | `avaliacao/resultados/aquecimento.json` | Registrado: embeddings/índice 12.101,09 ms; Ollama 423,38 ms; saída JSON real |
| Integridade da execução comparativa | `avaliacao/resultados/integridade_execucao.json` | SHA-256 das 120 respostas, 40 por configuração, mesmo digest Qwen e limiar 0,60, zero erros de execução |
| Diagnóstico anterior às correções | `avaliacao/resultados/diagnostico_antes_correcoes.jsonl` | 28 respostas exploratórias preservadas separadamente; não entram no placar final nem nos cinco erros de `erros.md` |
| Proveniência dos documentos e permissão de uso | `base/FONTES.md` | Registrado |
| Dados sintéticos e regras explícitas de prioridade | `base/operational.json` | Registrado |
| Contrato HTTP e integração futura com Central, DrenaVision e DrenaData | `docs/INTEGRACAO_CENTRAL.md`, adaptador de contrato em `app/integrations.py` e teste em `tests/test_app.py` | Adaptador local criado; integração HTTP externa não ativada |
| API executada e respostas | `avaliacao/resultados/smoke_api.json`, `smoke_api_resultados.json` e `demo_api/20261119T170438733Z/manifesto.json`; testes de API em `tests/` | GET /health, POST /assistant/ask nas três configurações e GET /evaluation/results responderam HTTP 200 com JSON real |
| Notebook executado com gráficos e saídas salvas | `notebooks/experimentos.ipynb` e `avaliacao/resultados/notebook_qa.json` | 9/9 células de código executadas com saídas, 0 erros, 1 gráfico PNG e rastro real de três ferramentas |
| Vídeo e demonstração técnica reproduzível | `docs/VIDEO_ROTEIRO.md`, `docs/demo_api.ps1` e cinco respostas HTTP reais em `avaliacao/resultados/demo_api/20261119T170438733Z/` | Script executado: 5/5 chamadas HTTP 200, recusa RAG, agente com ferramentas e pré-chamado. Gravação de tela pendente |
| Testes automatizados e totais aprovados | `avaliacao/resultados/testes_finais.txt`; grupos anteriores em `testes_app.txt` e `testes_avaliacao.txt` | Suíte final reexecutada após correção de citação: 21/21 aprovados em 12,96 s |

**Separação de dados:** `base/chunks.jsonl` indexa somente documentos. `base/operational.json` contém leituras, inspeções e ocorrências fictícias acessíveis apenas ao modo agente. Os exemplos da Central e DrenaData encontrados em outros checkouts não foram unidos automaticamente a essa base.
