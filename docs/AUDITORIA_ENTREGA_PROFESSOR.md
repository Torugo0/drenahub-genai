# Auditoria da entrega segundo os slides fornecidos

**Data da conferência:** 19/11/2026. **Escopo:** somente os três slides enviados pelo autor (páginas 29 a 31 de *Generative AI for Engineering*), comparados com o repositório e a execução salva. Esta análise não é uma nota atribuída pelo professor.

## Exigências de entrega dos slides

| Pedido explícito | Estado verificado | Evidência ou providência |
|---|---|---|
| Repositório **público** no GitHub | **Pendente**: `Torugo0/drenahub-genai` continua privado | A instrução anterior do autor proíbe alterar a visibilidade sem autorização. Tornar público antes da correção, após revisar o conteúdo. |
| `notebooks/` com saídas salvas | Presente | `notebooks/experimentos.ipynb`; `avaliacao/resultados/notebook_qa.json` confirma 9/9 células executadas, sem erro. |
| `base/` com trechos e fontes | Presente | `base/chunks.jsonl`, `base/FONTES.md`: 41 trechos, nove documentos. |
| `avaliacao/` com teste e placar | Presente | 40 casos em `avaliacao/casos.json`, 120 respostas em `avaliacao/resultados/respostas_brutas.jsonl`, placar e análise. |
| API e README | Presente | `app/api.py`, `README.md`; 22 testes passaram, a interface local foi verificada no navegador e a demonstração HTTP anterior retornou HTTP 200 nas cinco chamadas. |
| **Relatório técnico no GitHub** | **Pendente** | O conteúdo está distribuído entre README, `avaliacao/ANALISE.md`, `avaliacao/erros.md`, `base/FONTES.md` e inventário. Falta consolidar os campos exigidos no slide 31. O slide não exige formato ABNT. |
| Link do **vídeo** na conclusão do relatório | **Pendente** | Há roteiro e JSONs reais em `docs/VIDEO_ROTEIRO.md` e `avaliacao/resultados/demo_api/`, mas não há gravação nem link. Os slides não fixam duração ou formato. |
| Link do repositório no Teams até **19/11, 23h55** | **Sem comprovação** | O slide 29 traz esse prazo. Não há evidência de envio no projeto. |

O relatório técnico pedido no slide 31 deve conter: **nome completo e RM dos integrantes**, ficha técnica da tarefa, diagrama do pipeline de IA e dos documentos, tabela da base (fonte, formato, licença e número de trechos), performance das configurações, cinco erros com causa e correção, conclusão técnica e links do repositório e do vídeo. Nomes e RMs não estão disponíveis neste repositório. O relatório acadêmico ABNT foi expressamente reservado pelo autor para uma segunda etapa; a exigência do slide é um relatório no GitHub, sem formato ABNT especificado nas imagens.

## Oito critérios de pontuação

| Critério e peso | Evidência técnica observada | Julgamento prudente |
|---|---|---|
| 1. Tarefa e gabarito, inclusive “não consta” (0,5) | 40 casos fixos, 20 de desenvolvimento e 20 finais; seis recusas esperadas | Evidência presente. |
| 2. Base em trechos com fonte (1,0) | 41 trechos, nove documentos, URLs e condições de uso | Evidência presente; orientações predominantemente norte-americanas têm limites de aplicação. |
| 3. Recall@1/@3 e limiar (1,0) | Limiar 0,60 escolhido apenas em desenvolvimento; recall final 0,55/0,60; rankings salvos | Evidência presente, com queda de recuperação no conjunto final. |
| 4. JSON, citação e recusa (2,0) | JSON bruto válido e seis recusas esperadas corretas: 100%; citações aprovadas pelo gabarito no RAG/agente: 87,5% | Implementado e medido, mas o RAG recusou 18 dos 34 casos com resposta na referência: 14 eram operacionais, fora do acesso desse modo, e quatro eram documentais evitáveis. IDs/gabarito não provam suporte semântico de cada frase. Veja `avaliacao/AUDITORIA_SEMANTICA.md`. |
| 5. LoRA **ou agente** contra RAG (2,0) | Mesma LLM local nas três configurações; agente executa ferramentas reais, com 90% de uso correto | A alternativa por agente é permitida pelo slide. Os pesos não foram treinados; a especialização é por contexto, plano e ferramentas. |
| 6. Placar de três configurações (2,0) | 120 respostas: 17,5% / 40,0% / 57,5% corretas pela regra automática; no subconjunto final: 4/20, 7/20 e 10/20 | Comparação executada. O indicador de “afirmações sem suporte” penaliza a falta de fonte do baseline e **não equivale a taxa comprovada de alucinação**. A revisão manual das 65 respostas substantivas observou 15/19, 1/16 e 3/30 com ao menos uma afirmação sem evidência na referência, além de uma contradição no agente que o placar aprovou. |
| 7. Cinco erros reais (1,0) | Cinco respostas finais com linha, gabarito, causa e correção em `avaliacao/erros.md` | Evidência presente. |
| 8. README e reprodução (0,5) | `README.md`, versões fixadas, notebook executado, 22/22 testes | Evidência presente no ambiente usado; outro hardware pode exigir ajustes locais. |

## Objetivo geral do slide 29

O problema de drenagem se enquadra em **segurança** e a LLM roda localmente. O ganho de acerto pelo placar automático é observável. A [auditoria adicional](../avaliacao/AUDITORIA_SEMANTICA.md) e as revisões [documental](../avaliacao/AUDITORIA_DOCUMENTAL_DETALHADA.md) e [operacional](../avaliacao/AUDITORIA_OPERACIONAL_DETALHADA.md) confrontaram as 65 respostas substantivas com a referência. Elas sugerem menos extrapolações sem evidência nos modos com contexto, mas usam corpus limitado, registros sintéticos e quantidades diferentes de respostas emitidas. O indicador automático original mistura falta de citação com erro factual e deixou passar uma contradição. Logo, **não há prova quantitativa de menor taxa de alucinação no mundo real**, e não se deve anunciar “10/10 garantido”.

A API, o RAG e o agente estão integrados entre si. A **Central DrenaHub separada** ainda não chama esta API, conforme `docs/INTEGRACAO_CENTRAL.md`. Os registros sintéticos e ferramentas somente de leitura reduzem riscos na demonstração; a API não tem autenticação própria e não há comprovação ampla de conformidade com a LGPD para dados reais. Uma interface local para o DrenaAssist melhora a demonstração do módulo, mas não deve ser descrita como integração já concluída com a Central.

## Próximas entregas indispensáveis

1. Consolidar o relatório técnico no GitHub com os campos do slide 31, quando nomes, RMs e link do vídeo estiverem disponíveis.
2. Gravar demonstração real e inserir seu link no relatório. `docs/VIDEO_ROTEIRO.md` indica exatamente as telas e chamadas; a sugestão anterior de 4–5 minutos não vem dos slides.
3. Revisar o conteúdo e tornar o repositório público **somente com autorização do proprietário**, antes da correção.
4. Enviar o link ao Teams da disciplina até o prazo do slide; o projeto não comprova esse envio.
5. Caso se alegue menor alucinação e integração segura ao produto, aprofundar a validação factual por afirmação e demonstrar integração com a Central, ou declarar os limites das revisões atuais com precisão.
