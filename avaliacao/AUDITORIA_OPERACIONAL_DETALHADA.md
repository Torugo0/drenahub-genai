# Auditoria factual manual — casos operacionais e de ausência de resposta

Esta revisão examina as 60 respostas finais de O01–O15 e N01–N05, nas configurações baseline, RAG e agente. A referência factual é o conjunto **sintético** de [registros operacionais](../base/operational.json), confrontado com as [perguntas e gabaritos](casos.json). As respostas efetivamente devolvidas estão em [respostas_brutas.jsonl](resultados/respostas_brutas.jsonl); não usei o resultado da pontuação automática para decidir se uma afirmação é verdadeira. Examinei também o rascunho de ordem de serviço, o campo de explicação e as sugestões. Sugestões formuladas como ações futuras não são afirmações sobre fatos já ocorridos.

**Unidade de julgamento:** a resposta principal de cada execução. “Sustentada” significa que suas afirmações factuais estão de acordo com a referência, mesmo que a resposta omita fatos pedidos. “Contradita” significa que ao menos uma afirmação factual conflita com a referência. “Sem evidência” significa que a referência não permite confirmar uma afirmação, sem a refutar diretamente. “Indeterminada” seria usada se a evidência disponível não permitisse decidir. Recusas e omissões são contadas separadamente. O campo de explicação pode apresentar defeito mesmo quando a resposta principal é sustentada.

| Arquivo examinado | SHA-256 |
|---|---|
| respostas_brutas.jsonl | 6F05C9EE214536955DA05C7267FBD28F7D13899EAF892068BBE8105200FADDE5 |
| operational.json | 7507427E2B96CE9532536C2A606B10AFC3C20651DDC4C5210C22D966052C2AC3 |
| casos.json | 60519C5C303CD7069E73CCCEBAA89C21FBB6A59FED924AA79CEA5EAA5B9E7DDC |

## Contagens, com denominadores

| Configuração | Execuções | Respostas substantivas | Sustentadas | Contraditas | Sem evidência | Indeterminadas | Recusas esperadas corretas | Omissões por recusa em caso respondível |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 20 | 2 | 1 | 0 | 1 | 0 | 6/6 | 12/14 |
| RAG | 20 | 0 | 0 | 0 | 0 | 0 | 6/6 | 14/14 |
| Agente | 20 | 14 | 13 | 1 | 0 | 0 | 6/6 | 0/14 |
| **Total** | **60** | **16** | **14** | **1** | **1** | **0** | **18/18** | **26/42** |

Os denominadores de casos respondíveis são os 14 casos operacionais que não pedem recusa, por modo; O13 e N01–N05 são os seis casos de recusa esperada. As categorias de veracidade somam apenas as **16 respostas substantivas**, não as 60 execuções. Uma resposta sustentada pode ser incompleta. Além disso, quatro das 14 respostas substantivas do agente têm o campo de explicação inconsistente com fatos disponíveis: O06, O07, O10 e O15. Se o payload inteiro, e não apenas a resposta principal, for a unidade, somente **10/14** respostas substantivas do agente ficam sem contradição identificada nesta revisão.

## Todas as respostas substantivas

### Baseline

**O08 — sem evidência.** [Resposta bruta, linha 82](resultados/respostas_brutas.jsonl#L82): “Prioridade média é atribuída quando a ocorrência não representa um risco imediato ou urgente para a segurança ou funcionamento da instalação.” A referência não define “risco imediato” como critério. Sua [regra de prioridade](../base/operational.json#L6) usa nível acima do alerta e obstrução visual; [OC-002](../base/operational.json#L39) é média porque [IV-003](../base/operational.json#L34) registra folhas/obstrução, enquanto [LE-005](../base/operational.json#L28) mede 3,0 cm abaixo dos 10 cm. A resposta não explica este caso concreto. As três sugestões são propostas de verificação, sem afirmação de que houve outra medição ou ocorrência.

**O09 — sustentada, mas com causa incompleta.** [Resposta bruta, linha 85](resultados/respostas_brutas.jsonl#L85): “O RALO-03 do Galpão Norte está em prioridade média sem obstrução visual devido a uma inspeção recente que não encontrou obstruções visíveis.” A ausência de obstrução é verdadeira em [IV-004](../base/operational.json#L35) e ajuda a explicar por que a prioridade não é alta. Porém, [OC-003](../base/operational.json#L40) e [LE-006](../base/operational.json#L29) mostram que a medição de 12,3 cm acima do alerta de 10 cm é indispensável para explicar por que a prioridade é média, e não baixa. Não classifico a frase como falsa apenas por omitir essa causa; ela é uma explicação incompleta. As sugestões não acrescentam fatos observados.

### Agente

**O01 — sustentada, com omissão numérica.** [Resposta bruta, linha 63](resultados/respostas_brutas.jsonl#L63): “Garagem A está com prioridade alta devido ao nível de água acima do limite de 10 cm e a presença de obstrução na grelha, conforme evidências LE-001 e IV-001.” [OC-001](../base/operational.json#L38), [LE-001](../base/operational.json#L24) e [IV-001](../base/operational.json#L32) confirmam prioridade alta, leitura de **11,2 cm** acima de 10 cm e obstrução parcial. A resposta omite 11,2 cm, exigido pelo gabarito, mas não apresenta fato falso. A recomendação de limpeza não é afirmação sobre manutenção já realizada.

**O02 — sustentada, com omissão do estado.** [Resposta bruta, linha 66](resultados/respostas_brutas.jsonl#L66): “A última leitura do sensor no RALO-01 foi de 11.2 cm em 18 de novembro de 2026, às 17:30 BR.” [LE-001](../base/operational.json#L24) é posterior a LE-002 e confirma 11,2 cm em 18/11/2026 às 17:30, fuso −03:00. “BR” é impreciso, mas não altera a hora registrada. O estado “alerta” ficou de fora. As ações propostas não alegam uma leitura adicional.

**O03 — sustentada.** [Resposta bruta, linha 69](resultados/respostas_brutas.jsonl#L69): “Houve obstrução registrada no RALO-01, com residuos visíveis obstruindo parcialmente a grelha.” [IV-001](../base/operational.json#L32) registra exatamente resíduos visíveis, obstrução parcial e obstruction=true. As ações sugeridas são recomendações futuras.

**O04 — sustentada, mas sem explicitar a exclusividade.** [Resposta bruta, linha 72](resultados/respostas_brutas.jsonl#L72): “A garagem A aguarda manutenção por causa de água acima do alerta e residuos na grelha. Ocorrência identificada com ID OC-001.” [OC-001](../base/operational.json#L38) aguarda manutenção e contém esse resumo; [OC-004](../base/operational.json#L41), a outra ocorrência da Garagem A, já foi concluída. A resposta identifica a ocorrência correta, mas não diz expressamente que é a única. As sugestões não afirmam que o reparo ocorreu.

**O05 — sustentada, inclusive no rascunho.** [Resposta bruta, linha 75](resultados/respostas_brutas.jsonl#L75): “O rascunho de ordem de serviço para ocorrência OC-001 resume a ocorrência com água acima do alerta e residuos na grelha. Sugerimos a seguinte checklist: Verificar nível de água, limpar grelha e verificar fluxo d'água.” O objeto draft_work_order devolvido na mesma linha contém RALO-01, OC-001, prioridade alta, LE-001 e IV-001, checklist e status “rascunho_pendente_aprovacao_humana”, em acordo com [OC-001](../base/operational.json#L38), [LE-001](../base/operational.json#L24) e [IV-001](../base/operational.json#L32). O registro de referência continua aguardando manutenção; a resposta não afirma ter executado a ordem.

**O06 — sustentada, com explicação inconsistente.** [Resposta bruta, linha 78](resultados/respostas_brutas.jsonl#L78): “A última leitura da BOMBA-01 mostrou um nível de água de 6.2 cm e estava ligada. O estado foi descrito como normal.” [LE-004](../base/operational.json#L27) confirma 6,2 cm, bomba ligada e estado normal; a hora 17:32 foi omitida. O campo reason diz “Não consta nos dados disponíveis.”, em conflito com a própria resposta e a leitura consultada.

**O07 — sustentada, com explicação inconsistente.** [Resposta bruta, linha 81](resultados/respostas_brutas.jsonl#L81): “A última intervenção registrada no RALO-01 foi uma limpeza manual da grelha e teste de escoamento em 2026-10-20.” [MAN-001](../base/operational.json#L44) confirma ação, ponto e data. O campo reason diz “Não consta nos dados disponíveis.”, apesar do registro consultado.

**O08 — sustentada, com valores omitidos.** [Resposta bruta, linha 84](resultados/respostas_brutas.jsonl#L84): “A ocorrência da Garagem B tem prioridade média devido à presença de folhas acumuladas na grelha, conforme constatado por inspeção visual sintética (IV-003), e ao nível de água abaixo do limite (LE-005).” [OC-002](../base/operational.json#L39), [IV-003](../base/operational.json#L34) e [LE-005](../base/operational.json#L28) confirmam o quadro. A combinação obstrução presente e nível abaixo do alerta explica prioridade média pela regra; o nível abaixo do alerta sozinho não bastaria. Faltam os números 3,0 cm e 10 cm. As sugestões de limpeza e verificação são propostas.

**O09 — sustentada, com valores omitidos.** [Resposta bruta, linha 87](resultados/respostas_brutas.jsonl#L87): “O RALO-03 do Galpão Norte está em prioridade média devido ao nível de água acima do alerta (LE-006) e sem obstrução visual (IV-004).” [OC-003](../base/operational.json#L40), [LE-006](../base/operational.json#L29) e [IV-004](../base/operational.json#L35) confirmam: 12,3 cm acima de 10 cm e nenhuma obstrução visível, resultando em prioridade média. A resposta omite os valores 12,3 e 10 cm. As sugestões não afirmam achado novo.

**O10 — contradita, apesar de citar os eventos certos.** [Resposta bruta, linha 90](resultados/respostas_brutas.jsonl#L90): “Ocorrências registradas na Garagem A: 1. Ocorrência OC-001 (aguardando manutenção) - água acima do alerta e residuos na grelha. 2. Ocorrência OC-004 (concluída) - verificação preventiva concluída. **Não há ocorrências aguardando manutenção no sistema.**” As duas primeiras frases correspondem a [OC-001](../base/operational.json#L38) e [OC-004](../base/operational.json#L41), mas a última as contradiz: OC-001 aguarda manutenção. [OC-002](../base/operational.json#L39) também aguarda, em outra unidade. O trace de get_recent_events na própria linha 90 retornou OC-001 e OC-004, portanto o erro não decorre da falta desse dado. O campo reason ainda diz “Não consta nos dados disponíveis.”; a resposta omite prioridade e ponto de cada ocorrência. O [placar individual, registro do agente em O10](resultados/pontuacao_individual.json#L2561) marcou correct=true, citation_valid=true, unsupported_claim_detected=false e needs_human_review=false: este é um **falso positivo factual comprovado da avaliação automática**.

**O11 — sustentada.** [Resposta bruta, linha 93](resultados/respostas_brutas.jsonl#L93): “Ocorrências aguardando manutenção nas unidades monitoradas são OC-001 e OC-002. OC-001 tem evidências de LE-001 (água acima do alerta) e IV-001 (obstrução). OC-002 tem evidências de IV-003 (obstrução) e LE-005 (água abaixo do limite).” [OC-001](../base/operational.json#L38) e [OC-002](../base/operational.json#L39) têm status e IDs de evidência indicados; [LE-001](../base/operational.json#L24), [IV-001](../base/operational.json#L32), [LE-005](../base/operational.json#L28) e [IV-003](../base/operational.json#L34) confirmam os detalhes. [OC-003](../base/operational.json#L40) está em verificação, não na fila. Os IDs de evidência aparecem nos eventos retornados pela ferramenta, mesmo sem consulta separada a cada registro; isto afeta rastreabilidade, não a veracidade da frase frente à base completa.

**O12 — sustentada, com detalhe omitido.** [Resposta bruta, linha 96](resultados/respostas_brutas.jsonl#L96): “A inspeção visual do RALO-02 encontrou folhas acumuladas na grelha.” [IV-003](../base/operational.json#L34) confirma as folhas; também marca obstruction=true, detalhe que a resposta não explicitou. As sugestões são ações futuras.

**O14 — sustentada, com cálculo omitido.** [Resposta bruta, linha 102](resultados/respostas_brutas.jsonl#L102): “A leitura de água do RALO-01 aumentou de 8.4 cm para 11.2 cm entre as medições.” [LE-002](../base/operational.json#L25) registra 8,4 cm às 16:30, e [LE-001](../base/operational.json#L24) registra 11,2 cm às 17:30; a diferença é 2,8 cm. A direção e os valores estão corretos. O aumento calculado e os horários não aparecem no texto. As sugestões não acrescentam medições.

**O15 — sustentada nos fatos ditos, mas não responde qual intervenção foi feita.** [Resposta bruta, linha 105](resultados/respostas_brutas.jsonl#L105): “Intervenção de drenagem na CANALETA-02 ligada à OC-004 foi concluída. A inspeção preventiva verificou que LE-003 estava abaixo do limite e IV-002 não apresentava obstrução.” [OC-004](../base/operational.json#L41) foi concluída, [LE-003](../base/operational.json#L26) estava abaixo do limite e [IV-002](../base/operational.json#L33) não viu obstrução. Contudo, a intervenção específica é [MAN-002](../base/operational.json#L45): **inspeção e retirada de sedimentos em 16/11/2026 às 15:00**. Esse fato essencial não aparece. A ferramenta executada foi get_event, sem get_maintenance_history; a resposta não acessou o registro que responderia à pergunta. O campo reason “Não consta nos dados disponíveis.” é inconsistente com os fatos devolvidos. O [placar individual](resultados/pontuacao_individual.json#L2997) já marcou este caso como incorreto por omitir MAN-002/sedimentos.

## Recusas, omissões e cobertura dos 60 casos

Legenda: **S** = resposta principal substantiva sustentada; **C** = contradita; **SE** = sem evidência; **OR** = omissão por recusa em caso respondível; **RC** = recusa correta em caso sem resposta. Cada caso possui uma linha por configuração em respostas_brutas.jsonl, na ordem baseline, RAG e agente.

| Caso | Baseline | RAG | Agente | Observação de completude |
|---|---|---|---|---|
| O01 | OR | OR | S | Agente omite 11,2 cm. |
| O02 | OR | OR | S | Agente omite estado “alerta”. |
| O03 | OR | OR | S | Achado visual descrito corretamente. |
| O04 | OR | OR | S | Agente não explicita que OC-001 é a única pendente na Garagem A. |
| O05 | OR | OR | S | Rascunho correto e sem mutação operacional. |
| O06 | OR | OR | S | Agente omite 17:32; reason inconsistente. |
| O07 | OR | OR | S | Agente recupera MAN-001; reason inconsistente. |
| O08 | SE | OR | S | Baseline inventa critério de urgência; agente omite 3,0/10 cm. |
| O09 | S | OR | S | Baseline omite a medição decisiva; agente omite 12,3/10 cm. |
| O10 | OR | OR | C | Contradição explícita e falso positivo do placar. |
| O11 | OR | OR | S | Agente identifica OC-001 e OC-002. |
| O12 | OR | OR | S | Agente omite a classificação obstruction=true. |
| O13 | RC | RC | RC | Não há manutenção de BOMBA-01 em maintenance_history. |
| O14 | OR | OR | S | Agente omite diferença de 2,8 cm e horários. |
| O15 | OR | OR | S | Omissão essencial de MAN-002 e retirada de sedimentos; reason inconsistente. |
| N01 | RC | RC | RC | Não há previsão meteorológica por data/hora na referência. |
| N02 | RC | RC | RC | Leituras de RALO-01 são somente de 18/11/2026. |
| N03 | RC | RC | RC | IV-001 tem reviewed_by_human=false e não identifica revisor; agente recusou sem usar get_visual_inspections. |
| N04 | RC | RC | RC | Nenhuma previsão validada de alagamento ou data futura exata. |
| N05 | RC | RC | RC | Não há manual, marca, modelo ou torque da BOMBA-01. |

As recusas de baseline e RAG em casos operacionais respondíveis são adequadas **para os recursos que esses modos recebem**, mas constituem omissões frente à referência operacional completa usada para comparar o agente. A distinção evita chamar uma recusa prudente de alucinação. O modo RAG não recebeu registros operacionais; suas 14 omissões são o comportamento esperado dessa configuração experimental.

## Limites e implicações

- O10 prova que ID de fonte válido, chamada real de ferramenta e cobertura de palavras do gabarito não garantem resposta verdadeira. A frase falsa não foi capturada pelo verificador automático. O placar publicado de 57,5% de acertos do agente inclui **ao menos esse falso positivo**. O indicador de 12,5% de afirmações sem suporte deixou passar esta contradição, mas também pode gerar falsos positivos; **não é uma taxa de alucinação nem um limite inferior confiável**.
- O15 mostra o limite oposto: uma resposta pode conter apenas fatos verdadeiros e ainda deixar de responder ao que foi pedido. A classificação “sustentada” nesta auditoria não equivale a “correta/completa” no gabarito.
- Quatro respostas não recusadas do agente trazem reason “Não consta nos dados disponíveis.” apesar de resposta factual e evidência disponível. O campo precisa de revisão para que a explicação não negue a própria resposta.
- Esta auditoria julga os fatos apenas dentro do conjunto sintético versionado. Ela não comprova medições reais, eficácia das ações sugeridas, segurança de intervenções no mundo real, nem fundamentação semântica de todas as respostas documentais D01–D20. Não alterei código, gabarito ou placar.
