# Roteiro de demonstração técnica — 4 a 5 minutos

**Observação sobre o enunciado:** os slides fornecidos pedem um **link do vídeo na conclusão do relatório no GitHub**, mas não fixam duração. Os 4 a 5 minutos são apenas uma sugestão para uma demonstração objetiva.

Grave uma única sessão contínua de tela, com o servidor e o Ollama locais ativos. Mostre as saídas originais; não substitua respostas reais por texto editado. A análise nesta etapa é demonstrativa, usa registros operacionais sintéticos e não prevê alagamentos.

## Preparação antes de gravar

1. No PowerShell, ative `.venv` e execute `ollama list`; confirme que o modelo em `DRENA_MODEL` está instalado. Deixe `ollama serve` ativo se o serviço não iniciar automaticamente.
2. Execute `python -m uvicorn app.api:app --host 127.0.0.1 --port 8001` em outro terminal. Abra a interface em `http://127.0.0.1:8001/` e confirme `http://127.0.0.1:8001/health`.
3. Execute a avaliação completa conforme `README.md` **antes** da gravação. Mantenha `avaliacao/resultados/placar.md`, `avaliacao/erros.md` e `notebooks/experimentos.ipynb` abertos.
4. Aumente a fonte do terminal. Evite mostrar caminhos pessoais, abas privadas, tokens ou arquivos `.env`.
5. Para gerar os cinco retornos HTTP reais (health e quatro perguntas) em uma única execução reproduzível, rode `.\docs\demo_api.ps1`. O script salva JSONs e manifesto com horário, HTTP e latência em uma pasta nova de `avaliacao/resultados/demo_api/`; as chamadas manuais abaixo também podem ser usadas durante a gravação.

## Sequência sugerida

| Tempo | Tela | Ação e fala |
|---|---|---|
| 0:00–0:25 | README e arquitetura | “O DrenaAssist ajuda a consultar procedimentos de drenagem e registros de manutenção. Os registros desta prova são sintéticos. Três modos usam a mesma LLM local: sem contexto, RAG e RAG com agente.” |
| 0:25–0:45 | Terminais com `ollama list`, `GET /health` | Mostrar o modelo instalado e o serviço respondendo. Abrir `docs/AMBIENTE.json` para hardware, versão e parâmetros efetivamente registrados. |
| 0:45–1:10 | `base/FONTES.md` e `base/chunks.jsonl` | Mostrar nove fontes, 41 trechos, URLs, condições de uso e um `chunk_id` real. Explicar que o índice contém documentos, não ocorrências operacionais. |
| 1:10–1:40 | Interface local, modo **Com documentos** | Fazer a pergunta “O que deve constar no registro de inspeção de drenagem?”. Mostrar resposta e fontes, abrir a URL de ao menos uma fonte citada. Se desejar expor o JSON completo, abrir `/docs`. |
| 1:40–2:00 | Interface local, modo **Com documentos** | Perguntar “Qual foi a última leitura do sensor do RALO-01?”. Mostrar a recusa `Não consta nos dados disponíveis.` e explicar que este modo não acessa registros operacionais. |
| 2:00–2:40 | Interface local, modo **Agente**, e `operational.json` | Perguntar “Por que a garagem A está com prioridade alta?” com local `GAR-A`. Expandir “Ver percurso técnico da resposta” para mostrar as ferramentas realmente executadas; confrontar IDs citados com `LE-001`, `IV-001` e `OC-001` na base sintética. No ensaio salvo, a LLM não escolheu ferramentas; o fallback determinístico as executou. |
| 2:40–3:15 | Interface local, modo **Agente** | Solicitar “Prepare um rascunho de ordem de serviço para a ocorrência OC-001”. Mostrar o pré-chamado, checklist, prioridade e evidências, pendente de aprovação humana. Confirmar que `OC-001` não foi alterada. |
| 3:15–3:50 | Interface local, seção **Avaliação**, e `recuperacao_resumo.json` | Mostrar acertos dos três modos e os resultados do teste final. Ler recall@1, recall@3 e limiar no arquivo de recuperação. **Não chamar o indicador de falta de suporte de taxa de alucinação**; a auditoria mostra seu viés e a contradição O10. |
| 3:50–4:20 | `avaliacao/erros.md` e notebook | Mostrar cinco falhas reais ligadas às respostas brutas; abrir o notebook executado com tabela e gráfico. Explicar uma limitação e uma correção proposta. |
| 4:20–4:40 | README / conclusão | “O agente consulta registros e procedimentos para apoiar uma revisão humana. Detecção visual e dados de demonstração não constituem confirmação de risco nem substituem inspeção técnica.” |

## Chamadas para demonstrar

Os exemplos abaixo geram **novas inferências reais**. A resposta pode variar da avaliação salva; mantenha os JSONs exibidos. No PowerShell:

```powershell
$api = 'http://127.0.0.1:8001'
Invoke-RestMethod "$api/health"
Invoke-RestMethod "$api/assistant/ask" -Method Post -ContentType 'application/json' -Body (@{
  question = 'O que deve constar no registro de inspeção de drenagem?'
  configuration = 'rag'
} | ConvertTo-Json) | ConvertTo-Json -Depth 12
Invoke-RestMethod "$api/assistant/ask" -Method Post -ContentType 'application/json' -Body (@{
  question = 'Qual foi a última leitura do sensor do RALO-01?'
  configuration = 'rag'
} | ConvertTo-Json) | ConvertTo-Json -Depth 12
Invoke-RestMethod "$api/assistant/ask" -Method Post -ContentType 'application/json' -Body (@{
  question = 'Por que a garagem A está com prioridade alta?'
  configuration = 'agent'
  location_id = 'GAR-A'
} | ConvertTo-Json) | ConvertTo-Json -Depth 12
Invoke-RestMethod "$api/assistant/ask" -Method Post -ContentType 'application/json' -Body (@{
  question = 'Prepare um rascunho de ordem de serviço para a ocorrência OC-001.'
  configuration = 'agent'
  point_id = 'RALO-01'
} | ConvertTo-Json) | ConvertTo-Json -Depth 12
Get-Content avaliacao/tool_calls.jsonl -Tail 8
```

Se alguma chamada falhar, mostre o erro e a providência; não a substitua por resposta pré-fabricada. O vídeo deve exibir as telas acima. A gravação de tela e a locução podem ser feitas pelo autor do trabalho; este repositório fornece o roteiro e as evidências originais, mas não contém uma gravação.
