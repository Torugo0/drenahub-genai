# Análise da execução final

Foram executadas **120 respostas reais** (40 perguntas × três configurações)
com `qwen2.5:3b-instruct` local, temperatura 0, seed 42 e limite de 512 tokens.
Não houve erro de execução nas 120 chamadas; as saídas brutas e os rastros
estão em `resultados/respostas_brutas.jsonl`. O mesmo corpus documental de
41 trechos e o mesmo gabarito foram usados em RAG e agente; somente o agente
consultou os registros operacionais sintéticos por funções reais.

| Métrica | Baseline | RAG | RAG + agente |
| --- | ---: | ---: | ---: |
| Respostas corretas | 17,5% | 40,0% | 57,5% |
| Afirmações sem suporte detectadas | 47,5% | 12,5% | 12,5% |
| Recusas corretas | 100% | 100% | 100% |
| JSON bruto e retorno válidos | 100% | 100% | 100% |
| Citações válidas | 52,5% | 87,5% | 87,5% |
| Uso correto de ferramentas | — | — | 90,0% |
| Latência média | 1.183 ms | 1.354 ms | 1.688 ms |

O **RAG ganhou 22,5 pontos percentuais** de correção sobre o baseline. Nos
20 casos documentais, passou de 5% (1/20) para 50% (10/20). Também reduziu
a detecção de afirmações sem suporte em 35 pontos. O baseline recusou os
**seis casos que exigiam recusa** (cinco casos N e `O13`), mas muitas
respostas documentais livres foram
incompletas ou sem fonte externa.

O **agente ganhou 17,5 pontos** sobre o RAG. O ganho concentra-se nos 15 casos
operacionais: 8/15 corretos (53,3%) contra 1/15 (6,7%) no RAG e baseline.
Nos casos documentais, ambos acertaram 10/20. O agente realizou **31 chamadas
reais de ferramentas** nas 40 perguntas; 31 planos vieram diretamente da LLM,
cinco recorreram a fallback por plano vazio, três ao fallback com consultas
obrigatórias, e um plano da LLM foi complementado por consultas obrigatórias.
Os rastros registram argumentos, horário e IDs retornados. O agente não
treinou pesos: a especialização vem do RAG, do planejamento e das funções
somente leitura.

Houve pioras pontuais. Em `D06`, o RAG respondeu que a frequência anual pode
ser ajustada pelo acúmulo observado, mas o agente omitiu essa condição. O
agente foi **334 ms mais lento em média** que o RAG e errou o uso de ferramentas
em quatro casos (`D01`, `O15`, `N01`, `N03`). Dois deles tiveram recusa correta
mas consulta ausente ou desnecessária; `O15` deixou de buscar o histórico de
manutenção. Assim, o ganho global não autoriza afirmar superioridade em toda
categoria ou pergunta.

## Recuperação e limiar

O limiar de similaridade **0,60** foi escolhido apenas nas 10 perguntas
documentais e uma pergunta sem suporte do desenvolvimento, conforme a grade
e a regra em `resultados/limiar.json`. No desenvolvimento, recall@1 = 0,80 e
recall@3 = 0,95; nas 10 perguntas documentais finais, recall@1 = 0,55 e
recall@3 = 0,60. As três perguntas sem suporte documental foram rejeitadas
pela busca. O contraste entre desenvolvimento e teste final revela limite de
generalização: em `D16`, `D18` e `D19`, trechos corretos sobre segurança ou
preparo tiveram similaridade abaixo de 0,60 e acabaram filtrados. `D10`
mostrou perda de uma das duas fontes necessárias, apesar de uma fonte correta
no top 3. A escolha do limiar não foi recalibrada usando os casos finais.

## Limites do placar

“Correta” exige fatos definidos no gabarito, não uma avaliação subjetiva da
própria LLM. A taxa de afirmações sem suporte é um **limite inferior**: padrões
e IDs identificam erros conhecidos, mas não conseguem provar cada frase
livre. Uma resposta correta para o usuário pode perder pontos se omitir um
fato obrigatório; uma resposta com palavras esperadas pode exigir revisão
humana. As fontes citadas são checadas contra IDs consultados e fontes do
gabarito, mas a correspondência semântica de cada paráfrase ainda precisa de
auditoria manual. A base operacional é sintética e pequena; não demonstra
integração com sensores ou visão computacional reais nem previsão de
alagamentos. O DrenaAssist auxilia a manutenção; decisões e inspeções
permanecem humanas.

Cinco falhas específicas, com resposta real, gabarito, causa provável e
correção proposta, estão em `erros.md`.
