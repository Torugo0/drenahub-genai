# Revisão factual manual das respostas documentais D01–D20

Esta revisão usa **somente** as 60 respostas congeladas dos casos D01–D20 em `resultados/respostas_brutas.jsonl` e os 41 trechos de `../base/chunks.jsonl`. Conferi o conteúdo de cada resposta com o **corpus inteiro**, mesmo no baseline e mesmo quando a resposta não citou a fonte. `S` significa que todas as afirmações factuais verificáveis da resposta são sustentadas por texto expresso ou inferência curta dos trechos; `E` significa que há ao menos uma afirmação específica **sem evidência no corpus**; `I` significa que uma frase é ambígua demais para julgamento seguro; `C` exigiria conflito explícito com os trechos. `E` não significa que a afirmação seja falsa no mundo real. A categoria de uma resposta é a mais severa encontrada (`C > E > I > S`); as demais partes sustentadas são indicadas na coluna de evidência. **Omissão** de fato esperado e **recusa** de caso respondível aparecem separadamente e não viram “alucinação”. Esta auditoria não reavalia a fidelidade dos 41 trechos aos documentos originais.

Cada linha abaixo corresponde a **uma resposta substantiva**. `B` = baseline, `R` = RAG e `A` = agente. O número da linha identifica o JSONL original. Os trechos nomeados em “Evidência” foram localizados independentemente dos `source_ids` que o modelo retornou. A coluna “Lacuna” registra a afirmação não demonstrada ou a omissão importante; para `S`, pode haver apenas omissão.

## D01–D10

| Caso/modo, linha JSONL | Estado | Evidência no corpus para o texto da resposta | Afirmação sem evidência, ambiguidade ou omissão |
| --- | :---: | --- | --- |
| D01/B, 1 | E | Inspeções regulares e manutenção preventiva/corretiva são compatíveis com `EPA-OM-01`, `EPA-PM-01` e `EPA-PM-04`. | O corpus não exige **operação diária**, plano de resposta a emergências ou sistema de comunicação como partes desse plano de O&M. Omite responsáveis, recursos, cronograma e limpeza de entradas/saídas de `EPA-OM-01`. |
| D02/B, 4 | E | Limpeza e inspeção de caixa de captação constam em `EPA-OM-02` e `EPA-CB-03`. | **Reparo de tubulações** e **substituição de filtros** não são descritos como trabalhos típicos da caixa; não há filtro nesse conjunto de trechos. Omite lixo, sedimentos e treinamento. |
| D02/R, 5 | S | Retirada de lixo e sedimentos: `EPA-OM-02`; data, quantidade e uso do histórico: `EPA-OM-03`. | Omite operadores treinados. `EPA-OM-03` sustenta a frase adicional, apesar de ficar fora da lista de fontes do gabarito. |
| D02/A, 6 | S | Mesma resposta e mesmo suporte de D02/R: `EPA-OM-02` e `EPA-OM-03`. | Omite operadores treinados; a citação adicional `EPA-OM-03` é semanticamente adequada. |
| D03/B, 7 | E | Data e quantidade removida estão em `EPA-OM-03`. | Hora e funcionários responsáveis constam de **outro tipo de relatório** (`EPA-SWPPP-04`, inspeção industrial), não do registro específico da limpeza da caixa. “Resíduos” é mais amplo que o sedimento solicitado. |
| D03/R, 8 | S | Data da limpeza e quantidade de sedimento: `EPA-OM-03`. | Sem omissão essencial para “o que registrar”. |
| D03/A, 9 | S | Mesma resposta de D03/R: `EPA-OM-03`. | Sem omissão essencial. |
| D04/B, 10 | E | O mapeamento de estruturas e histórico de sedimento consta em `EPA-OM-04`. | Capacidade de captação e **prever mudanças no fluxo** não são finalidades documentadas em `EPA-OM-04` ou outro trecho. Omite priorizar/otimizar limpeza. |
| D04/R, 11 | S | Priorizar e otimizar limpeza pelo mapeamento: `EPA-OM-04`. | Sem omissão essencial. |
| D04/A, 12 | S | Mesma resposta de D04/R: `EPA-OM-04`. | Sem omissão essencial. |
| D05/B, 13 | E | A abertura da grelha, sozinha, não resolve detritos internos: `EPA-CB-02`. | “Obstruções **permanentes**” acrescenta característica não descrita; o restante transmite a necessidade de limpeza interna. |
| D05/R, 14 | I | A segunda frase, sobre remover detritos internos, é sustentada por `EPA-CB-02`. | “**Não desobstruir** a grelha é insuficiente” é redação ambígua: pode querer dizer “não, desobstruir a grelha é insuficiente”. O trecho diz que **desobstruir só a grelha** não basta; não permite decidir com segurança o sentido da primeira frase. |
| D05/A, 15 | E | A segunda frase, que pede considerar detritos internos além da grelha, é sustentada por `EPA-CB-02`. | A equivalência “**não desobstruir a grelha equivale a não limpar a caixa**” não decorre de `EPA-CB-02`; o trecho afirma a implicação inversa, de que limpar **apenas** a abertura não equivale à limpeza completa. |
| D06/R, 17 | S | Inspeção ao menos anual, decisão de limpar e ajuste pelo acúmulo: `EPA-CB-03`. | Sem omissão essencial. |
| D06/A, 18 | S | Inspeção anual para decidir limpeza: `EPA-CB-03`. | Omite que a frequência real depende do acúmulo observado; resposta verdadeira, mas incompleta. |
| D07/R, 20 | S | Critério de um terço e referência da ficha de 1999: `EPA-CB-04`. | Não explicita que é referência norte-americana, e não norma brasileira; não chega a afirmar universalidade. |
| D07/A, 21 | S | Mesmo critério: `EPA-CB-04`. | Mesma ressalva de escopo omitida. |
| D08/B, 22 | E | `EPA-CB-06` requer destinação adequada e avaliação de possível contaminação. | Recipientes, **armazenamento seco/protegido** e possibilidade de **reciclagem** não aparecem nos trechos. Não menciona a avaliação antes de escolher o descarte; a omissão não equivale a dizer explicitamente que se deve dispensá-la. |
| D08/R, 23 | E | Contaminação e avaliação: `EPA-CB-06`; remoção típica de lixo/sedimento: `EPA-OM-02`. | “Armazenados adequadamente” especifica **armazenamento**, que `EPA-CB-06` não prescreve. `EPA-CB-01` foi citado, mas descreve função da caixa, não destinação. |
| D08/A, 24 | E | Mesma resposta de D08/R: `EPA-CB-06` e `EPA-OM-02` sustentam as demais frases. | Mesma lacuna de armazenamento e citação tangencial `EPA-CB-01`. |
| D09/B, 25 | E | A data aparece em registro de limpeza (`EPA-OM-03`); documentação de testes/inspeções em manutenção preventiva consta de `EPA-PM-05`. | Hora, descrição livre, responsável, equipamento e resultados **como campos obrigatórios desse registro preventivo** não são listados no corpus. Omite testes, inspeções e medidas de acompanhamento. |
| D09/R, 26 | S | Testes, inspeções, acompanhamento, atualização/revisão: `EPA-PM-05`; data e quantidade da limpeza: `EPA-OM-03`. | Sem omissão essencial. |
| D09/A, 27 | S | Testes, inspeções, acompanhamento e atualização: `EPA-PM-05`. O corpus é geral e não contém registros da instalação específica. | A ressalva final é epistemicamente correta; não afirma um fato operacional local. |
| D10/B, 28 | S | Verificar funcionamento da bomba: `NWS-BEFORE-03`; inspecionar controles e identificar correções: `EPA-SWPPP-02/03` e `EPA-PM-04`. | Omite **corrigir** controles ineficazes antes da chuva. A resposta é genérica, mas não contradiz o corpus. |
| D10/R, 29 | S | Pontos de descarga/controles e manutenção ou substituição: `EPA-SWPPP-02/03`. | Omite a bomba (`NWS-BEFORE-03`) e troca a **correção** dos controles por mera verificação. |
| D10/A, 30 | S | Bomba: `NWS-BEFORE-03`; inspeção de pontos e controles: `EPA-SWPPP-02/03`. | `NWS-BEFORE-03` sustenta a frase no **corpus inteiro**, embora não estivesse entre os trechos recuperados/citados naquela execução. Omite corrigir controles ineficazes antes da chuva. |

## D11–D20

| Caso/modo, linha JSONL | Estado | Evidência no corpus para o texto da resposta | Afirmação sem evidência, ambiguidade ou omissão |
| --- | :---: | --- | --- |
| D11/B, 31 | E | Cor da água é observação visual em `EPA-SWPPP-06`; condição dos pontos de descarga e controles em `EPA-SWPPP-02`. | **Quantidade e fluxo da água**, mais obstrução/dano específicos **nos pontos de descarga**, não são os itens registrados pelos trechos sobre essa inspeção. Omite lixo, manchas, descarga indevida e controles. |
| D11/R, 32 | S | Lixo, manchas, descarga indevida, controles: `EPA-SWPPP-02`; película, sedimento, espuma e extravasamento: `EPA-SWPPP-05`. | A frase adicional de sinais visuais é sustentada, embora vá além do mínimo pedido. |
| D11/A, 33 | S | Mesmos trechos de D11/R: `EPA-SWPPP-02` e `EPA-SWPPP-05`. | Sem lacuna factual relevante. |
| D12/B, 34 | S | Extravasamento de drenos/bacias (`EPA-SWPPP-05`) e vazamentos como defeitos (`EPA-PM-01`) dão suporte amplo a alagamento/vazamento como sinais de problema. | Omite os sinais específicos que o trecho pedido enumera: película oleosa, sedimento escuro, espuma e lixo. “Enchentes” é genérico, não um item literal da ficha. |
| D12/R, 35 | S | Lista de sinais corresponde a `EPA-SWPPP-05`. | Sem omissão essencial. |
| D12/A, 36 | S | Mesma lista: `EPA-SWPPP-05`. | Sem omissão essencial. |
| D13/B, 37 | E | Ruído, vibração, aquecimento e vazamentos genéricos: `EPA-LIFT-02`; inspeção preventiva pode antecipar falhas: `EPA-PM-01`. | “**Elevatória de Prumo**” não é o título da fonte indexada e **vazamento de óleo** especifica um fluido que `EPA-LIFT-02` não informa. Não distingue elevatória de **esgoto** de bomba de garagem (`EPA-LIFT-01`). |
| D13/R, 38 | S | Todos os sinais mecânicos citados: `EPA-LIFT-02`. | Não explica que a ficha é de elevatória de esgoto e serve só como referência para garagem; não afirma que se aplica automaticamente. |
| D13/A, 39 | S | Mesmo suporte: `EPA-LIFT-02`. | Mesma ressalva de aplicação local omitida. |
| D14/R, 41 | S | A ficha não impõe periodicidade semanal universal à garagem: `EPA-LIFT-01/04`; sinais mecânicos adicionais: `EPA-LIFT-02`. | Omite dizer explicitamente que a ficha trata de **esgoto** e que a frequência depende do **porte**. `EPA-LIFT-02` sustenta a frase adicional, embora a lista do caso não o admitisse. |
| D14/A, 42 | S | Mesmos trechos de D14/R: `EPA-LIFT-01/02/04`. | Mesma omissão de contexto, sem afirmação contraditória. |
| D15/B, 43 | S | Desligar energia antes de contato com água/circuitos tem apoio em `OSHA-FLOOD-01`. | Omite a condição **“quando seguro”**, o disjuntor principal e não entrar/tocar equipamento em piso molhado. Essa omissão é relevante para segurança, mas não é afirmação explícita de que se deve desligar em condição insegura. |
| D15/R, 44 | S | Disjuntor principal, evitar área alagada e equipamento molhado: `OSHA-FLOOD-01`. | Troca “quando **seguro**” por “quando **possível**”; é uma imprecisão de segurança que requer ajuste, sem afirmar claramente o contrário da fonte. |
| D15/A, 45 | S | Mesma orientação central: `OSHA-FLOOD-01`. | Mesma imprecisão “quando possível” no lugar de “quando seguro”. |
| D16/B, 46 | E | Não há trecho que especifique “local seguro” de forma verificável; `OSHA-FLOOD-03` prescreve **ar livre** e veda espaço confinado por monóxido de carbono. | **Incêndio/explosão** como motivo apresentado não aparece no corpus. Omite ar livre, espaço confinado e monóxido de carbono, que são a resposta documentada. Isso não prova que esses outros riscos sejam falsos fora da base. |
| D17/B, 49 | E | Colete apropriado como proteção pessoal: `OSHA-FLOOD-05`. | **Treinamento em emergências aquáticas** não consta dos trechos OSHA. Omite não trabalhar sozinho e colete na água ou perto dela. |
| D17/R, 50 | S | Não atuar sozinho, usar colete e risco de afogamento: `OSHA-FLOOD-05`. | Sem omissão essencial. |
| D17/A, 51 | S | Mesma resposta e suporte: `OSHA-FLOOD-05`. | Sem omissão essencial. |
| D18/B, 52 | E | Testar funcionamento da bomba antes da chuva: `NWS-BEFORE-03`. | **Limpeza de filtros de entrada** não aparece no trecho da bomba nem em outro trecho. Omite reserva, disjuntores e serviço profissional na válvula. |
| D19/B, 55 | E | Não caminhar/dirigir em área alagada: `NWS-DURING-03`. | Solo frágil, deslizamento de terra e quedas **não são os motivos listados no corpus** para esta orientação. Omite fios, objetos cortantes, químicos e dano à via; os riscos adicionais podem ser reais em outro contexto. |
| D20/B, 58 | E | Data e localização: `EPA-CHECK-04`; tipos de dano/obstrução: `EPA-CHECK-01`; inspeção preventiva: `EPA-PM-01/04`. | “**Data de início**” do defeito não é o mesmo campo de **data da inspeção**; “desgaste” não é o termo específico do checklist. Omite nome do inspetor e depósitos internos. |
| D20/R, 59 | S | Data, inspetor, frequência/localização: `EPA-CHECK-04`; rachaduras/vazamentos como defeitos de manutenção preventiva: `EPA-PM-01`, com caixa de captação incluída no programa em `EPA-PM-02`. | A transferência de sinais genéricos para a captação é uma inferência curta, não o checklist específico pedido. Omite distinguir grelha, entrada entupida e depósito interno de `EPA-CHECK-01`. |
| D20/A, 60 | E | Campos do formulário: `EPA-CHECK-04`; manutenção preventiva, rachaduras/vazamentos: `EPA-PM-01`. | Manchas, lixo acumulado e descargas indevidas vêm da inspeção de **pontos de descarga industriais** (`EPA-SWPPP-02`), não do checklist de **captação** (`EPA-CHECK-01`); a transferência de local não é sustentada diretamente. Omite grelha/entrada/depósito. |

## Recusas e completude

Os 20 casos documentais têm resposta no corpus. Portanto, as seguintes **11 recusas são indevidas** e não contêm afirmação factual para classificar como `S/E/I/C`:

| Modo | Casos recusados | Evidência que permitiria resposta |
| --- | --- | --- |
| Baseline | D06 (linha 16), D07 (19), D14 (40) | `EPA-CB-03`, `EPA-CB-04`, `EPA-LIFT-01/04` |
| RAG | D01 (2), D16 (47), D18 (53), D19 (56) | `EPA-OM-01`, `OSHA-FLOOD-03`, `NWS-BEFORE-03`, `NWS-DURING-03` |
| Agente | D01 (3), D16 (48), D18 (54), D19 (57) | Mesmos trechos do RAG |

Em D01/RAG e D01/agente, o trecho `EPA-OM-01` foi recuperado, mas a regra de intenção operacional impôs recusa a uma pergunta geral (`app/assistant.py:59-68,341-344`; `erros.md`). Em D16/D18/D19, a recuperação com limiar 0,60 não entregou o trecho correto à geração; isso explica a recusa na execução, embora o corpus completo contenha a resposta. Falta de resposta completa também ocorre em saídas factualmente `S`, como D06/agente e D20/RAG; esta auditoria não converte omissão em alucinação.

## Contagens desta revisão

| Classe de resposta, denominador | Baseline | RAG | Agente |
| --- | ---: | ---: | ---: |
| Perguntas documentais | 20 | 20 | 20 |
| Respostas substantivas classificadas | 17 | 16 | 16 |
| Todas as afirmações verificáveis sustentadas (`S`) | 3/17 | 14/16 | 13/16 |
| Pelo menos uma afirmação sem evidência no corpus (`E`) | 14/17 | 1/16 | 3/16 |
| Frase ambígua que impede julgamento seguro (`I`) | 0/17 | 1/16 | 0/16 |
| Afirmação explicitamente contradita pelo corpus (`C`) | 0/17 | 0/16 | 0/16 |
| Recusas indevidas, **separadas** das classes factuais | 3/20 | 4/20 | 4/20 |

As classes acima são **por resposta**: uma resposta `E` pode conter várias frases corretas, identificadas na tabela. Não há, neste subconjunto documental, contradição explícita suficientemente comprovada pelos trechos; há extrapolações e detalhes sem suporte. A comparação sugere que contexto documental reduz afirmações **sem evidência nesta base** nas respostas emitidas, mas os denominadores substantivos diferem por causa das recusas. Também não equivale a medir verdade externa ou conformidade da fonte original. No teste final, o RAG e o agente recusaram três perguntas de segurança/preparo respondíveis, um custo importante para o uso prático.
