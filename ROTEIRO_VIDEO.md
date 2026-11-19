# Roteiro do vídeo (≈ 5 min)

O vídeo segue a ordem dos 8 critérios de nota, para o professor "ticar" cada um enquanto assiste. Grave a tela com o produto rodando de verdade; não edite respostas.

## Antes de gravar (5 min)

Terminal 1, na pasta do projeto:

```powershell
.\.venv\Scripts\Activate.ps1
$env:DRENA_V2_DATA_EXPORT_DIR = 'C:\Users\Vitor\OneDrive\Área de Trabalho\drenaData\mvp\dados'
python -m uvicorn app.api:app --host 127.0.0.1 --port 8001
```

1. Abra http://127.0.0.1:8001/ e faça **uma pergunta qualquer para aquecer**: a primeira demora ~20 s porque carrega os modelos; as seguintes levam 1 a 3 s.
2. Deixe abertas as abas: o README no GitHub (ou no VS Code em modo preview), `avaliacao/casos.json`, `base/chunks.jsonl`, `notebooks/lora_qwen.ipynb`.
3. Aumente o zoom do navegador para 125% e feche abas pessoais.

## Gravação

| Tempo | Tela | O que fazer e falar |
|---|---|---|
| 0:00–0:25 | README, topo | "Somos Gabriel, Lourenzo e Vítor. O DrenaAssist é a IA generativa da DrenaHub: responde a síndicos e zeladores o que fazer com a drenagem antes da chuva, citando a fonte, rodando 100% local. Eixo: segurança." |
| 0:25–0:50 | README, diagrama (seção 2) | Mostre o fluxo: documentos → trechos → embeddings → busca → LLM local → validação → resposta ou recusa → revisão humana. "Três configurações com a mesma LLM: sem contexto, RAG e RAG + agente." |
| 0:50–1:10 | `avaliacao/casos.json` | **Critério 1.** "40 perguntas com gabarito, 20 de desenvolvimento e 20 de teste. Seis delas não têm resposta e o certo é dizer *Não consta*." Mostre um caso com `"refuse": true`. |
| 1:10–1:30 | `base/chunks.jsonl` + tabela da seção 3 | **Critério 2.** "9 documentos públicos, 41 trechos; cada trecho tem ID, URL e licença." |
| 1:30–1:55 | README, seção 5 | **Critério 3.** "Recall@1 e recall@3 medidos. O limiar 0,60 foi escolhido só no desenvolvimento: é o mais alto antes de perder trechos e o que rejeita perguntas sem resposta. No teste, o recall caiu para 0,55/0,60, e mostramos isso." |
| 1:55–2:30 | Interface, **Com documentos** | **Critério 4.** Clique **Como registrar uma inspeção?** → Consultar. Mostre a resposta e as fontes citadas (abra uma URL). Depois clique **Teste de recusa** → "Não consta nos dados disponíveis." "A saída é sempre JSON validado, com citação ou recusa." Opcional: abra `/docs` e mostre o JSON. |
| 2:30–3:10 | Interface, **Com documentos** e depois **Agente** | **Critério 5.** Clique **Prioridade da Garagem A** no modo *Com documentos*: o RAG recusa, porque não acessa registros. Troque para **Agente**, local *Garagem A* e consulte: agora responde citando OC-001, LE-001 e IV-001. Abra **Ver percurso técnico** para mostrar as ferramentas executadas. "Essa é a especialização: o agente consulta o registro em vez de supor." |
| 3:10–3:35 | `notebooks/lora_qwen.ipynb` ou README seção 8 | **Critério 5 (LoRA).** "Também treinamos de verdade: QLoRA no Qwen 1.5B, numa RTX 4060, 97 segundos. JSON válido foi de 0 para 24 de 24, mas o modelo ainda inventou dados em 7 de 24. Conclusão: o treino ensinou formato, não veracidade; por isso o produto usa RAG + agente." |
| 3:35–4:15 | Interface, seção **Avaliação** + README seção 7 | **Critério 6.** "Placar com 120 respostas reais: 17,5% sem contexto, 40% com RAG, 57,5% com agente. Na revisão humana, 79% das respostas sem contexto tinham invenção; com RAG, 6%; com agente, 13%. O RAG recusa demais; o agente resolve as operacionais, mas ninguém acertou as perguntas de duas fontes." |
| 4:15–4:40 | README seção 9 | **Critério 7.** Mostre a tabela dos 5 erros. "O erro 4 apareceu agora ao vivo: o agente explicou a prioridade sem citar os 11,2 cm. A correção é montar esse valor no código, não deixar para a LLM." |
| 4:40–5:00 | http://127.0.0.1:8001/v2/console e README final | **Critério 8 + integração.** Mostre o console lendo a DrenaData. "Tudo reproduzível: requirements, 98 testes, notebooks com saídas e o comando que refaz a avaliação." Feche com a conclusão: "Contexto verificável vale mais que fine-tuning com poucos exemplos." |

## Depois de gravar

1. Suba o vídeo (YouTube não listado ou Drive com acesso por link).
2. Troque os dois **(inserir link do vídeo aqui)** do `README.md` pelo link.
3. Faça commit/push e deixe o repositório `Torugo0/drenahub-genai` **público**.
4. Envie o link do repositório no Teams da disciplina até 23h55.
