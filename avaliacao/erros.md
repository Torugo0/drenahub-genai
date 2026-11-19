# Cinco erros observados nas execuções reais

As respostas abaixo são transcritas de `resultados/respostas_brutas.jsonl`
(linhas indicadas, ordem D01…N05 × baseline/RAG/agente). Os gabaritos e as
fontes admissíveis foram fixados em `casos.json` antes da execução. O placar
usa as respostas da execução final congelada; não mistura o diagnóstico
anterior a duas correções do agente.

## 1. D01 — recusa indevida por classificação de intenção

- **Pergunta / configuração:** “O que deve constar em um plano de operação e manutenção da drenagem?” / RAG simples.
- **Resposta real:** “Não consta nos dados disponíveis.” (`respostas_brutas.jsonl`, linha 2).
- **Gabarito:** Responsáveis, cronograma, frequência, recursos e atividades de inspeção e limpeza; `EPA-OM-01`.
- **Evidência da falha:** `EPA-OM-01` foi recuperado em primeiro lugar, similaridade 0,798253, mas o motivo de recusa foi “Os documentos técnicos não contêm registros operacionais desta instalação.” A pergunta é sobre um procedimento geral, sem instalação específica.
- **Causa provável:** A regra de classificação operacional inclui a expressão genérica “manutenção da”, confundindo tema técnico com consulta a uma instalação.
- **Correção proposta:** Exigir ID de ponto, unidade identificada ou pedido explícito de registro antes de aplicar o bloqueio de respostas operacionais no RAG; testar perguntas gerais sobre manutenção separadamente.

## 2. O10 — contradição factual ignorada pelo placar

- **Pergunta / configuração:** “Gere um resumo das ocorrências registradas da Garagem A e seus status.” / RAG + agente.
- **Resposta real:** “Ocorrência OC-001 (aguardando manutenção) [...] Não há ocorrências aguardando manutenção no sistema.” (`respostas_brutas.jsonl`, linha 90).
- **Gabarito:** Na Garagem A, `OC-001` aguarda manutenção e `OC-004` está concluída. `base/operational.json` também registra `OC-002` aguardando manutenção em outro local.
- **Evidência da falha:** O agente chamou `get_recent_events` para `GAR-A`, recebeu `OC-001` com `status: aguardando_manutencao`, citou essa ocorrência e depois negou a existência de qualquer ocorrência nesse estado. O placar original ainda marcou `correct=true`, `citation_valid=true` e `unsupported_claim_detected=false` porque verificou os fatos positivos do gabarito, sem inspecionar a frase contraditória.
- **Causa provável:** A síntese acrescentou uma conclusão global incompatível com os registros consultados; o validador aceitou os IDs e não fez checagem de contradição por afirmação.
- **Correção proposta:** Confrontar as frases de status com os registros retornados antes de liberar a resposta, impedir uma negação global quando houver um registro ativo e acrescentar esse caso à auditoria factual independente. Não alterar retroativamente as 120 respostas congeladas.

## 3. D10 — resposta incompleta em pergunta de duas fontes

- **Pergunta / configuração:** “Antes da próxima chuva, que duas verificações práticas aparecem nos documentos para controles pluviais industriais e bomba de drenagem?” / RAG simples.
- **Resposta real:** “Verificar os pontos de descarga e os controles pluviais para manutenção ou substituição antes da próxima chuva.” Citou `EPA-SWPPP-02` e `EPA-SWPPP-03` (`respostas_brutas.jsonl`, linha 29).
- **Gabarito:** Corrigir controles ineficazes antes da precipitação prevista (`EPA-SWPPP-03`) **e** verificar o funcionamento da bomba (`NWS-BEFORE-03`).
- **Evidência da falha:** A busca trouxe apenas `EPA-SWPPP-02` e `EPA-SWPPP-03` acima do limiar 0,60; não trouxe `NWS-BEFORE-03`. O trecho da bomba foi omitido. Recall@3 do caso: 0,5.
- **Causa provável:** Uma consulta vetorial única concentrou os resultados no tema industrial e perdeu a segunda parte do enunciado.
- **Correção proposta:** Decompor perguntas com dois tópicos em até duas buscas controladas, combinar os trechos distintos e exigir cobertura de cada tópico antes de gerar a resposta.

## 4. O01 — omissão do valor que fundamenta prioridade

- **Pergunta / configuração:** “Por que a Garagem A está com prioridade alta?” / RAG + agente.
- **Resposta real:** “Garagem A está com prioridade alta devido ao nível de água acima do limite de 10 cm e a presença de obstrução na grelha, conforme evidências LE-001 e IV-001.” Citou `OC-001`, `LE-001` e `IV-001` (`respostas_brutas.jsonl`, linha 63).
- **Gabarito:** `OC-001` tem prioridade alta porque `LE-001` mediu **11,2 cm**, acima de 10 cm, e `IV-001` registrou obstrução parcial.
- **Evidência da falha:** O agente executou `get_recent_events`, `get_sensor_readings` e `get_visual_inspections`, mas não reproduziu o valor 11,2 cm presente em `LE-001`. O caso falhou no fato obrigatório `11[.,]2`.
- **Causa provável:** A síntese da LLM resumiu o comparativo como “acima do limite” e perdeu a medição específica.
- **Correção proposta:** Para justificativas de prioridade, compor deterministicamente o valor medido e o limiar a partir dos registros consultados, mantendo a LLM para explicação e checklist.

## 5. O15 — ferramenta inadequada para histórico de intervenção

- **Pergunta / configuração:** “Qual intervenção foi concluída na CANALETA-02 ligada à OC-004?” / RAG + agente.
- **Resposta real:** “Intervenção de drenagem na CANALETA-02 ligada à OC-004 foi concluída. A inspeção preventiva verificou que LE-003 estava abaixo do limite e IV-002 não apresentava obstrução.” Citou apenas `OC-004` (`respostas_brutas.jsonl`, linha 105).
- **Gabarito:** `MAN-002`, em 16/11/2026 às 15:00, registra **inspeção e retirada de sedimentos** na CANALETA-02, vinculada à `OC-004`.
- **Evidência da falha:** O rastro mostra só `get_event`; `get_maintenance_history` não foi chamado. A resposta descreve a ocorrência, não o trabalho registrado em `MAN-002`.
- **Causa provável:** O planejador interpretou “ligada à OC-004” como consulta à ocorrência e não considerou a intenção “intervenção concluída”.
- **Correção proposta:** Para perguntas sobre intervenção executada, consultar obrigatoriamente `get_maintenance_history` do ponto e conferir `event_id` antes de responder; manter a ocorrência como contexto complementar.

## Escopo da análise

Esses cinco casos são falhas reais, com texto bruto e rastros preservados. A
checagem determinística usa fatos obrigatórios e fontes do gabarito; não
substitui revisão humana de todas as alegações livres. Nenhuma correção
proposta acima foi aplicada depois de consultar o conjunto final; o placar
publicado conserva o comportamento medido.
