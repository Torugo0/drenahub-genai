# Agente base × agente treinado

| configuração | corretas % | corretas no teste final | citações válidas % | ferramentas corretas % | recusas corretas % | tempo médio ms |
| --- | --- | --- | --- | --- | --- | --- |
| Agente (modelo base) | 57.5 | 10/20 | 87.5 | 90.0 | 100 | 1688.11 |
| Agente treinado (LoRA) | 50.0 | 8/20 | 90.0 | 87.5 | 100 | 16602.29 |

Casos que mudaram de resultado:

- D05: agente acertou, treinado errou
- D08: agente acertou, treinado errou
- O02: agente errou, treinado acertou
- O06: agente errou, treinado acertou
- O07: agente acertou, treinado errou
- O10: agente acertou, treinado errou
- O14: agente acertou, treinado errou
