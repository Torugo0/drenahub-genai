# Protocolo de avaliação

O gabarito em `casos.json` tem 40 perguntas: 20 de desenvolvimento e 20 finais.
São 20 perguntas documentais (incluindo duas de múltiplas fontes), 15
operacionais e cinco de ausência de resposta ou indução de alucinação.
Seis casos exigem recusa: os cinco últimos e `O13`, sem manutenção registrada.
As respostas documentais foram escritas a partir dos trechos identificados em
`base/chunks.jsonl`; as operacionais, a partir dos registros sintéticos em
`base/operational.json`, sem consultar a LLM avaliada. Cada caso guarda resposta
esperada, expressões de fatos obrigatórios, fontes admissíveis, recusa esperada
e justificativa. O SHA-256 do gabarito e do corpus acompanha cada execução.

## Recuperação

Para perguntas documentais com conjunto de trechos relevantes `G`, calcula-se
`recall@k = |G ∩ top-k selecionado| / |G|`, para `k = 1` e `k = 3`. A média
é feita por pergunta; casos sem trecho relevante não entram no denominador de
recall. Para eles, mede-se separadamente a proporção sem qualquer resultado
acima do limiar. O ranking bruto, os escores e os trechos selecionados ficam
em `resultados/recuperacao_individual.json` e `.csv`.
Os IDs em `gold_chunks` formam o conjunto específico para responder ao
enunciado integralmente (inclusive dois trechos em perguntas de múltiplas
fontes); trechos apenas tangenciais não entram no gabarito.

O limiar é selecionado numa grade fixa de 0,00 a 0,95, passo 0,05. A função
objetivo nos casos de desenvolvimento é a média entre recall@3 médio e taxa
de rejeição das perguntas sem suporte. Em empate, escolhe-se o limiar maior.
Depois mede-se o conjunto final uma única vez com o valor já escolhido. O
valor, a grade completa e a justificativa ficam em `resultados/limiar.json`.
O índice contém apenas documentação técnica; registros operacionais não são
inseridos nele.

## Geração

As três configurações recebem as mesmas 40 perguntas e usam o mesmo modelo
Ollama, temperatura e demais parâmetros do cliente. O RAG simples e o agente
usam o mesmo índice documental. O agente é a única configuração que acessa
ferramentas operacionais. A resposta bruta e os metadados (incluindo plano e
chamadas reais de ferramentas) são persistidos em
`resultados/respostas_brutas.jsonl` antes da pontuação. A execução pode ser
retomada sem repetir linhas; `--fresh` inicia nova coleta completa.

Métricas por configuração:

- **Correta:** recusa com frase exata quando o gabarito pede recusa; caso
  contrário, resposta sem recusa que satisfaz todas as expressões de fatos
  obrigatórios. Pré-chamado exige objeto `draft_work_order`.
- **Afirmação sem suporte detectada:** resposta não recusada quando deveria,
  expressão factual explicitamente proibida, ID citado fora das fontes do
  caso, ou resposta marcada como sustentada sem citação válida. Esse indicador
  mistura ausência de citação, desacordo com a lista de fontes do caso e erro
  factual. Pode sinalizar uma afirmação verdadeira sem fonte esperada e pode
  deixar passar uma contradição com fonte citada. **Não é taxa de alucinação**;
  alegações livres exigem revisão factual por afirmação. Veja
  `AUDITORIA_SEMANTICA.md`.
- **Recusa correta:** entre os casos que pedem recusa, proporção que devolve
  `refused=true` e a frase `Não consta nos dados disponíveis.`.
- **JSON válido:** proporção de objetos de resposta serializáveis em JSON.
  Também é informada a validade sintática do JSON bruto da LLM, quando há
  saída bruta.
- **Citações válidas:** cada ID citado precisa pertencer às fontes do caso,
  existir na evidência consultada já validada pela aplicação e cobrir grupos
  obrigatórios de fontes quando houver mais de uma evidência necessária.
  Recusas não devem trazer fontes.
- **Latência média:** média dos milissegundos medidos pelo assistente para
  a resposta completa, incluindo recuperação e ferramentas.
- **Ferramentas corretas:** entre as 40 respostas do agente, os nomes de
  ferramentas executadas devem cobrir os requisitos do caso e não exceder
  a lista de ferramentas pertinentes. Perguntas documentais não exigem
  ferramentas operacionais.

As métricas são verificações reproduzíveis por regex e IDs de fonte. Uma
paráfrase correta fora dos padrões pode virar falso negativo; uma frase com
palavras esperadas mas relação incorreta pode virar falso positivo. Os cinco
erros em `erros.md` são inspecionados em resposta real, gabarito e rastros.

## Execução

```powershell
python -m avaliacao.run --phase all --fresh
```

Para repetir apenas a pontuação de respostas existentes, importe
`avaliacao.metrics.score_answer` e `aggregate` no Python. Para reconstruir
o placar a partir de novas respostas, execute `python -m avaliacao.run
--phase answers --fresh`. Os artefatos de saída são gerados em
`avaliacao/resultados/`.
