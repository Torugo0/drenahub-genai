# Contrato de integração com a Central DrenaHub

## Estado verificado em 19/11/2026

- Este repositório expõe a API DrenaAssist. A base operacional usada na avaliação é **inteiramente sintética** (`base/operational.json`).
- O checkout local da Central em `../landing_drena_hub` é uma página HTML/JavaScript demonstrativa. Seus registros de ocorrência são fictícios e editáveis no `localStorage`; não há backend de sensores ou chamada ao DrenaAssist. Este documento especifica uma integração futura, sem afirmar que ela já ocorre.
- O checkout local da DrenaVision em `../drena_hub_avc` possui API FastAPI real, documentada em `docs/TECNICO.md` desse projeto. Ela fornece `GET /vision/events?point_id=...&limit=...&offset=...` e `GET /vision/events/{event_id}`. `app/integrations.py` normaliza um `PredictionEvent` para um registro pendente de revisão humana e rejeita campos obrigatórios ausentes; o DrenaAssist desta etapa **não busca nem ingere automaticamente** esses eventos.
- O checkout local `../drenaData` contém `amostras/sensores_sinteticos_amostra.csv` com leituras sintéticas e identificadores como `GARAGEM_A_RALO_01`. Ele não é uma API ativa. O DrenaAssist usa outro conjunto de demonstração, sem misturar os dois.

## API do DrenaAssist

| Método | Rota | Uso |
|---|---|---|
| GET | `/health` | Estado do serviço |
| GET | `/assistant/configurations` | Configurações `baseline`, `rag` e `agent` |
| POST | `/assistant/ask` | Pergunta e resposta validada |
| GET | `/evaluation/results` | Placar da avaliação disponível |

`GET /health` informa `status`, `ollama_model_available`, `model` e `operational_data`. O cliente deve verificar `ollama_model_available`; `status: "ok"` indica que o processo HTTP respondeu, não que a LLM esteja necessariamente carregada. Antes de executar a avaliação, `GET /evaluation/results` pode retornar HTTP 404.

Corpo do `POST /assistant/ask`:

```json
{
  "question": "Por que a garagem A está com prioridade alta?",
  "configuration": "agent",
  "location_id": "GAR-A",
  "point_id": "RALO-01"
}
```

`question` é obrigatória (3 a 1.000 caracteres); `configuration` aceita `baseline`, `rag` ou `agent` e assume `agent`; `location_id` e `point_id` são opcionais, com até 80 caracteres. O cliente deve passar IDs do mesmo conjunto operacional usado pelo servidor. A resposta contém `question`, `answer`, `supported`, `refused`, `sources`, `reason`, `suggested_actions`, `draft_work_order` e `metadata`. Cada fonte tem `source_id`, `source_type`, `title` e `url` opcional. O pré-chamado tem `point_id`, `event_id`, `evidence_ids`, `priority`, `checklist`, `justification`, `source_ids` e `status`. Uma recusa traz `answer: "Não consta nos dados disponíveis."`.

O rascunho **não altera ocorrência**, nem aciona dispositivo. A Central deve exigir revisão humana antes de criar ordem de serviço. Citações de documentos devem abrir a URL da fonte; IDs de registros operacionais devem apontar para telas internas da Central apenas quando houver correspondência confirmada.

## Exemplo React

O trecho abaixo mostra como uma futura Central React pode chamar a API. É um exemplo de cliente, não uma execução observada da Central atual.

```tsx
import { useState } from "react";

type Source = {
  source_id: string;
  source_type: string;
  title: string;
  url: string | null;
};

type AssistantResponse = {
  answer: string;
  refused: boolean;
  reason: string;
  sources: Source[];
  suggested_actions: string[];
  draft_work_order: null | {
    point_id: string;
    event_id: string;
    priority: string;
    checklist: string[];
    status: string;
  };
};

export function DrenaAssistPanel({ locationId, pointId }: {
  locationId?: string;
  pointId?: string;
}) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AssistantResponse | null>(null);
  const [error, setError] = useState("");

  async function ask() {
    setError("");
    setResult(null);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 300_000);
    try {
      const response = await fetch(
        `${import.meta.env.VITE_DRENAASSIST_URL}/assistant/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question,
            configuration: "agent",
            location_id: locationId,
            point_id: pointId
          }),
          signal: controller.signal
        }
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setResult(await response.json() as AssistantResponse);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha na consulta");
    } finally {
      window.clearTimeout(timer);
    }
  }

  return (
    <section>
      <label htmlFor="drena-question">Pergunte ao DrenaAssist</label>
      <input id="drena-question" value={question}
        onChange={event => setQuestion(event.target.value)} />
      <button type="button" onClick={ask} disabled={question.trim().length < 3}>
        Consultar
      </button>
      {error && <p role="alert">{error}</p>}
      {result && <article>
        <p>{result.answer}</p>
        {result.refused && <p>Motivo: {result.reason}</p>}
        <ul>{result.sources.map(source => <li key={source.source_id}>
          {source.url
            ? <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
            : <span>{source.source_id}: {source.title}</span>}
        </li>)}</ul>
        {result.draft_work_order && <p>
          Pré-chamado {result.draft_work_order.event_id}: revisão humana necessária.
        </p>}
      </article>}
    </section>
  );
}
```

Defina `VITE_DRENAASSIST_URL=http://127.0.0.1:8001` no frontend de desenvolvimento e inclua a **origem do frontend** (por exemplo, `http://localhost:5173`) em `DRENA_CORS_ORIGINS` no servidor. O limite de 300 s no exemplo cobre as duas chamadas sequenciais ao modelo que o agente pode fazer com o timeout padrão de 120 s por chamada, até seis ferramentas com 5 s por chamada e uma margem para recuperação. Em produção, use uma URL HTTPS própria e autenticação/autorização na borda da aplicação antes de expor registros operacionais. O exemplo não envia credenciais nem dados pessoais.

## Mapeamento futuro dos outros módulos

**DrenaVision.** A resposta `GET /vision/events` usa `items` e `total`. Cada item possui `event_id`, `point_id`, `timestamp`, `detected_classes`, `inspection_recommended` e `status`. `GET /vision/events/{event_id}` acrescenta `detections`; as classes são `obstrucao_visivel`, `agua_acumulada` e `animal_visivel`. O adaptador puro em `app/integrations.py` recebe esse evento detalhado, preserva ID, horário, detecções, status e URI de evidência e define `reviewed_by_human: false`. A integração HTTP futura ainda precisa buscar o evento, mapear `point_id` por tabela versionada e manter o achado como **detecção visual não confirmada** até revisão humana. A confiança do detector não é probabilidade de alagamento. A URL lógica de evidência deve ser resolvida pela própria API DrenaVision.

**DrenaData.** A amostra CSV tem `record_id`, `point_id`, `event_time`, `water_level_cm`, `sensor_status`, `is_synthetic` e `collected_at`. Uma ingestão futura precisa preservar `is_synthetic`, deduplicar `record_id`, rejeitar valores fora da faixa definida pelo módulo e versionar o mapeamento `GARAGEM_A_RALO_01` → `RALO-01` apenas se ambos se referirem ao mesmo ponto físico. Nesta etapa, os registros não foram unidos.

**Central.** O JavaScript atual persiste ocorrências em `localStorage` com IDs `DH-...`, diferentes dos IDs `OC-...` da base DrenaAssist. Não se deve inferir identidade entre esses conjuntos pelo nome da garagem. A integração exige um cadastro de unidades, pontos e ocorrências com IDs compartilhados antes de expor consultas operacionais reais.
