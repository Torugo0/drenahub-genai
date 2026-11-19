# Placar das três configurações

| configuração | n | corretas % | afirmações sem suporte detectadas % | recusas corretas % | JSON válido % | citações válidas % | ferramentas corretas % | latência média ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 40 | 17.5 | 47.5 | 100 | 100 | 52.5 | — | 1183.08 |
| rag | 40 | 40.0 | 12.5 | 100 | 100 | 87.5 | — | 1353.64 |
| agent | 40 | 57.5 | 12.5 | 100 | 100 | 87.5 | 90.0 | 1688.11 |

Métricas determinísticas calculadas com `avaliacao/metrics.py` a partir de
`casos.json` e `resultados/respostas_brutas.jsonl`. Afirmações sem suporte
detectadas são um limite inferior: a inspeção humana de alegações livres
continua necessária. Latência inclui a chamada síncrona ao assistente.
