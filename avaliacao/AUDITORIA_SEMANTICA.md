# Auditoria independente das respostas e da métrica de alucinação

**Escopo:** execução congelada de 40 perguntas × três configurações, nas 120 linhas de `resultados/respostas_brutas.jsonl`. Esta auditoria não modifica o gabarito, as respostas brutas nem o placar original. `python -m avaliacao.auditar_semantica` reproduz as contagens automáticas abaixo em `resultados/auditoria_semantica.json`, com SHA-256 dos quatro arquivos de entrada. A revisão manual **por resposta** das 65 saídas substantivas foi concluída separadamente em `AUDITORIA_DOCUMENTAL_DETALHADA.md` e `AUDITORIA_OPERACIONAL_DETALHADA.md`. Ela não contou cada oração como unidade estatística nem verificou a verdade externa dos documentos originais.

## O que as medidas comprovam

| Medida, denominador explícito | Baseline | RAG | RAG + agente |
| --- | ---: | ---: | ---: |
| Casos respondíveis no gabarito | 34 | 34 | 34 |
| Acertos conforme fatos obrigatórios/recusa, em 40 | 7/40 | 16/40 | 23/40 |
| Acertos nos 34 casos respondíveis | 1/34 | 10/34 | 17/34 |
| Recusas corretas, nos seis casos sem resposta | 6/6 | 6/6 | 6/6 |
| Recusas **indevidas** nos 34 casos respondíveis | 15/34 | 18/34 | 4/34 |
| Respostas substantivas | 19 | 16 | 30 |
| Citação aprovada pelo placar, entre respostas substantivas | 0/19 | 11/16 | 25/30 |
| Sinalizadas como “afirmação sem suporte” pelo placar, em 40 | 19/40 | 5/40 | 5/40 |
| Padrões de afirmação proibida encontrados | 0 | 0 | 0 |

O ganho de acertos medido é real **segundo o gabarito fixo**: 17,5% → 40,0% → 57,5%. A metodologia usa regexes de fatos obrigatórios (`metrics.py:67-74`), por isso é uma medida de cobertura dos fatos previstos, não uma avaliação completa de toda frase. O mesmo modelo e os parâmetros de geração foram usados nas três configurações (`app/ollama_client.py:25-32`; `resultados/integridade_execucao.json`). O modo agente tem consultas operacionais reais, somente leitura, registradas em `tool_calls.jsonl` (`app/assistant.py:185-216`). Não há ajuste de pesos da LLM (`README.md:15`); a especialização é por ferramentas e contexto, como alternativa ao LoRA na rubrica.

No subconjunto **final** de 20 perguntas, os acertos são 4/20 no baseline, 7/20 no RAG e 10/20 no agente. Retirando as três recusas esperadas desse subconjunto, são respectivamente 1/17, 4/17 e 7/17 perguntas respondíveis acertadas. Isso sustenta ganho relativo, mas não desempenho alto no teste final.

O 100% de “recusa correta” considera apenas seis perguntas cujo gabarito manda recusar. É necessário mostrar também as recusas indevidas: o RAG recusou 18 das 34 perguntas respondíveis, inclusive D01 após recuperar `EPA-OM-01` (`erros.md:9-15`). O limiar de recuperação foi escolhido no desenvolvimento, mas o recall@3 caiu de 0,95 no desenvolvimento para 0,60 no teste final (`resultados/recuperacao_resumo.json`). Portanto, a qualidade observada no teste final é limitada, mesmo com ganho sobre o baseline.

## Por que 47,5% versus 12,5% não é taxa de alucinação

O prompt do baseline exige `source_ids=[]` (`app/assistant.py:32-39`). A métrica marca como “sem suporte” qualquer resposta substantiva sem citação (`metrics.py:116-120`). Assim, **todos os 19 sinais do baseline** decorrem de respostas sem fonte por construção. Isso não demonstra que cada resposta é falsa. A “citação válida” de 52,5% do baseline são **21 recusas sem fonte**, porque a métrica conta recusa sem citação como válida (`metrics.py:85-89`); nenhuma das 19 respostas substantivas do baseline traz uma citação.

Nos modos RAG e agente, as cinco respostas sinalizadas em cada modo citam IDs fora da lista de fontes admitidas no caso, e nenhum padrão de afirmação proibida disparou. Uma fonte fora dessa lista pode, contudo, sustentar uma afirmação adicional verdadeira. Exemplos verificados:

| Caso | Observação na resposta real | Confronto com a fonte |
| --- | --- | --- |
| D02, RAG e agente (`respostas_brutas.jsonl:5-6`) | A resposta explica limpeza e acrescenta registro de data/quantidade de sedimento, citando `EPA-OM-03`. O placar reprova essa citação porque `casos.json:6` não incluiu `EPA-OM-03` na lista. | `base/chunks.jsonl:3` diz expressamente que o registro deve conter data e quantidade, e que isso orienta a frequência. É um **falso negativo de citação** no placar, para essa afirmação adicional. |
| D08, RAG e agente (`respostas_brutas.jsonl:23-24`) | `EPA-CB-06` sustenta avaliação de contaminantes e destinação, mas `EPA-CB-01` foi citado sem sustentar essa orientação. | Exemplo real de citação tangencial. `EPA-OM-02` sustenta a frase adicional sobre retirada de lixo/sedimento; o problema não é uniformemente “alucinação”. |
| D10, agente (`respostas_brutas.jsonl:30`) | Menciona verificar bomba, mas os dois trechos consultados eram `EPA-SWPPP-02/03`. | A fonte da bomba (`NWS-BEFORE-03`) não foi recuperada. A frase existe no corpus, mas **não estava na evidência fornecida àquela resposta**. Isso é falha de fundamentação. |
| D14, RAG e agente (`respostas_brutas.jsonl:41-42`) | Acrescentam ruído, vibração, aquecimento e vazamentos e citam `EPA-LIFT-02`, excluído da lista do caso (`casos.json:18`). | `EPA-LIFT-02` contém exatamente esses itens. O ID extra é adequado para essa afirmação; a resposta ainda pode perder o caso por omitir o contexto de esgoto/porte exigido pelo gabarito. |

Portanto, o placar original é útil como **checagem automática de fontes esperadas**, mas seus percentuais de “afirmações sem suporte” não devem ser apresentados como prova quantitativa de que o sistema alucina 35 pontos percentuais menos. O próprio protocolo reconhece que essa detecção é um limite inferior de regras e IDs (`METODOLOGIA.md:49-65`). A regra tem vieses em direções diferentes: conta ausência de citação como erro semântico no baseline e deixa passar contradição com IDs válidos no agente.

## Contradição real que o placar não detectou

Em **O10/agente**, a resposta informa `OC-001 (aguardando manutenção)` e termina: **“Não há ocorrências aguardando manutenção no sistema.”** (`resultados/respostas_brutas.jsonl:90`). `base/operational.json` contém `OC-001` e `OC-002` com `status: aguardando_manutencao`; a própria chamada `get_recent_events` retornou `OC-001`. A última frase contradiz os dados e a primeira frase. Mesmo assim, o placar registra `correct=true`, `citation_valid=true` e `unsupported_claim_detected=false` em `resultados/pontuacao_individual.json`, porque O10 exige por regex apenas os fatos positivos e não tem padrão proibido (`casos.json:34`). O script desta auditoria detecta essa forma específica de contradição e registra os IDs que a refutam. Isso é **um exemplo confirmado**, não uma taxa exaustiva de alucinação.

Na resposta **O09/baseline** (`respostas_brutas.jsonl:85`), a ausência de obstrução é verdadeira e ajuda a distinguir prioridade média de alta, mas a explicação omite a leitura `LE-006` acima do alerta, necessária para distinguir média de baixa. É **incompletude**, não contradição comprovada. Em **D13/baseline** (`respostas_brutas.jsonl:37`), aparece “Elevatória de Prumo” e “vazamento de óleo”; `EPA-LIFT-01/02` tratam de estação elevatória de esgoto e vazamentos em geral. A especificidade não é demonstrada pelos trechos. Esses exemplos não entram na contagem determinística de contradições deste script.

## Limites técnicos ligados à rubrica

- `supported=true` na API significa somente que houve pelo menos um ID consultado e citado (`app/assistant.py:327-351`). A guarda adicional procura valores em centímetros e prioridades em registros citados (`app/assistant.py:240-259`); não verifica se cada frase é consequência de cada fonte. O10 mostra o limite.
- A ferramenta `get_sensor_readings` não aceita argumento de data (`app/operational.py:107-111,144-159`). No caso N02, o plano da LLM incluiu `timestamp: 2025-01-15`, mas `call` removeu o argumento e devolveu leituras de 2026 (`respostas_brutas.jsonl:111`). A resposta final recusou corretamente; ainda assim, perguntas históricas dependem de a LLM perceber a divergência temporal. Uma filtragem de data explícita no contrato seria mais segura.
- A base indexada tem 41 paráfrases, nove documentos e metadados de fonte/licença (`base/FONTES.md`). As URLs permitem auditoria, mas os trechos não trazem número de página/seção do documento original. A origem foi documentada; correspondência exata de todas as paráfrases com originais não foi refeita nesta auditoria.
- A API funciona localmente e o pré-chamado fica pendente de revisão humana. A Central existente não chama esta API e os dados operacionais são sintéticos (`README.md:91`; `docs/INTEGRACAO_CENTRAL.md:5-8`). Isso limita a afirmação de que a IA **já roda integrada ao produto**.
- O experimento não armazena dados pessoais no conjunto demonstrativo e usa ferramentas somente leitura, o que ajuda a cumprir privacidade no protótipo. A rota `/assistant/ask` não implementa autenticação (`app/api.py:42-48`) e a resposta expõe `metadata.tool_trace` com os registros consultados (`app/assistant.py:374-383`). O próprio contrato exige HTTPS/autorização antes de dados reais (`docs/INTEGRACAO_CENTRAL.md:128`). Portanto, conformidade LGPD para uso com dados reais **ainda não foi demonstrada**.

## Revisão factual complementar das 65 respostas substantivas

As duas revisões manuais confrontaram **cada resposta emitida** com o corpus completo ou os registros sintéticos, sem reprovar automaticamente o baseline por não citar. Classificaram a resposta principal pela afirmação mais problemática e registraram omissões à parte. Este é um julgamento de **suporte na referência**, não de verdade universal nem de segurança de intervenção.

| Classe por resposta substantiva | Baseline (19) | RAG (16) | Agente (30) |
| --- | ---: | ---: | ---: |
| Todas as afirmações verificáveis sustentadas na referência | 4 | 14 | 26 |
| Ao menos uma afirmação sem evidência na referência | 15 | 1 | 3 |
| Ao menos uma contradição explícita | 0 | 0 | 1 |
| Uma ambiguidade que impede classificação segura | 0 | 1 | 0 |

Os documentos detalhados registram as 49 respostas documentais e as 16 operacionais. O resultado **sugere menor frequência de respostas com extrapolações sem evidência** entre as respostas emitidas pelo RAG/agente frente ao baseline. Não converta esses números em “taxa de alucinação”: os modos emitiram quantidades diferentes de resposta, a base é limitada e há omissões/recusas importantes. Em particular, RAG recusou 18 dos 34 casos respondíveis no gabarito, sendo 14 consultas operacionais sem acesso a registros por desenho experimental. O agente recusou 4/34. Em quatro respostas operacionais do agente, o campo `reason` diz “Não consta nos dados disponíveis.” apesar de a resposta principal citar fatos presentes; as classes da tabela consideram a resposta principal, e esses defeitos do payload estão descritos na auditoria operacional.

**Prioridades para a entrega:** (1) apresentar o indicador automático com a ressalva correta e a revisão factual complementar; (2) mostrar O10 como falha real e explicar o limite do validador; (3) separar recusas prudentes, recusas evitáveis, omissões e erros factuais; (4) corrigir os problemas encontrados e executar novo benchmark versionado antes de apresentar novos percentuais; (5) documentar controles de acesso/privacidade e integrar a Central separada antes de alegar produto integrado e LGPD plena. Se o código ou corpus forem corrigidos após esta coleta, não substitua silenciosamente as 120 saídas congeladas.
