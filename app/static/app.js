(() => {
  "use strict";

  const form = document.querySelector("#ask-form");
  const question = document.querySelector("#question");
  const locationSelect = document.querySelector("#location-id");
  const pointSelect = document.querySelector("#point-id");
  const contextFields = document.querySelector("#context-fields");
  const askButton = document.querySelector("#ask-button");
  const cancelButton = document.querySelector("#cancel-button");
  const requestStatus = document.querySelector("#request-status");
  const answerPanel = document.querySelector("#answer-panel");
  const answerEmpty = document.querySelector("#answer-empty");
  const answerContent = document.querySelector("#answer-content");
  const modeDescription = document.querySelector("#mode-description");
  const stepConsultation = document.querySelector("#step-consultation");

  const modes = {
    baseline: { name: "Sem contexto", step: "Nenhum documento ou registro é consultado." },
    rag: { name: "Com documentos", step: "Trechos técnicos são recuperados por busca." },
    agent: { name: "Agente", step: "Documentos e ferramentas de leitura podem ser consultados." }
  };
  const modeDescriptions = {
    baseline: "A mesma LLM responde sem receber documentos ou registros operacionais. Ela deve recusar fatos sobre instalações específicas que não pode verificar.",
    rag: "A mesma LLM recebe trechos técnicos recuperados por busca. Registros operacionais ainda não estão disponíveis para ela.",
    agent: "A mesma LLM usa documentos técnicos e pode consultar registros operacionais sintéticos por ferramentas somente de leitura."
  };
  const points = [
    { id: "RALO-01", name: "Ralo 01", location: "GAR-A" },
    { id: "CANALETA-02", name: "Canaleta 02", location: "GAR-A" },
    { id: "BOMBA-01", name: "Bomba 01", location: "GAR-A" },
    { id: "RALO-02", name: "Ralo 02", location: "GAR-B" },
    { id: "RALO-03", name: "Ralo 03", location: "GAL-1" }
  ];
  const examples = {
    inspection: { mode: "rag", question: "O que deve constar no registro de inspeção de drenagem?", location: "", point: "" },
    refusal: { mode: "rag", question: "Qual foi a última leitura do sensor do RALO-01?", location: "", point: "" },
    priority: { mode: "agent", question: "Por que a Garagem A está com prioridade alta?", location: "GAR-A", point: "" },
    "work-order": { mode: "agent", question: "Prepare um rascunho de ordem de serviço para a ocorrência OC-001.", location: "GAR-A", point: "RALO-01" }
  };
  const toolNames = {
    get_sensor_readings: "Leituras de sensores",
    get_recent_events: "Ocorrências recentes",
    get_visual_inspections: "Inspeções visuais",
    get_maintenance_history: "Histórico de manutenção",
    get_event: "Detalhe da ocorrência",
    get_points: "Pontos de drenagem",
    get_maintenance_queue: "Fila de manutenção"
  };
  const recordLabels = {
    point_id: "Ponto",
    location_id: "Local",
    event_id: "Ocorrência",
    timestamp: "Data",
    opened_at: "Abertura",
    water_level_cm: "Nível de água (cm)",
    status: "Situação",
    priority: "Prioridade",
    priority_reason: "Justificativa",
    summary: "Resumo",
    finding: "Achado visual",
    obstruction: "Obstrução",
    reviewed_by_human: "Revisado por pessoa"
  };
  const percent = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  let activeController = null;

  function node(tag, className, content) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined && content !== null) element.textContent = String(content);
    return element;
  }

  function clear(element) {
    element.replaceChildren();
  }

  function selectedMode() {
    return form.elements.configuration.value;
  }

  function updateMode() {
    const mode = selectedMode();
    contextFields.hidden = mode !== "agent";
    locationSelect.disabled = mode !== "agent";
    pointSelect.disabled = mode !== "agent";
    modeDescription.textContent = modes[mode]?.apiDescription ? `${modes[mode].apiDescription}. ${mode === "agent" ? "Os registros operacionais são sintéticos e as ferramentas são de leitura." : ""}` : (modeDescriptions[mode] || modeDescriptions.agent);
    stepConsultation.textContent = modes[mode]?.step || modes.agent.step;
  }

  function updatePoints(preferred = "") {
    const selectedLocation = locationSelect.value;
    const previous = preferred || pointSelect.value;
    clear(pointSelect);
    pointSelect.append(node("option", "", "Inferir pela pergunta"));
    pointSelect.firstElementChild.value = "";
    for (const point of points) {
      if (selectedLocation && point.location !== selectedLocation) continue;
      const option = node("option", "", `${point.name} · ${point.id}`);
      option.value = point.id;
      pointSelect.append(option);
    }
    pointSelect.value = Array.from(pointSelect.options).some(option => option.value === previous) ? previous : "";
  }

  async function fetchJson(url, timeoutMs) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function loadHealth() {
    const dot = document.querySelector("#health-dot");
    const label = document.querySelector("#health-label");
    const model = document.querySelector("#model-name");
    try {
      const health = await fetchJson("/health", 8000);
      model.textContent = health.model || "Modelo local";
      dot.classList.toggle("is-ready", Boolean(health.ollama_model_available));
      dot.classList.toggle("is-unavailable", !health.ollama_model_available);
      label.textContent = health.ollama_model_available ? "Modelo local disponível" : "Modelo local indisponível";
    } catch {
      dot.classList.add("is-unavailable");
      label.textContent = "Não foi possível verificar o modelo";
    }
  }

  async function loadConfigurations() {
    try {
      const data = await fetchJson("/assistant/configurations", 8000);
      for (const configuration of data.configurations || []) {
        if (modes[configuration.id] && typeof configuration.description === "string") {
          modes[configuration.id].apiDescription = configuration.description;
        }
      }
      updateMode();
      const model = document.querySelector("#model-name");
      if (data.model && model.textContent === "DrenaAssist") model.textContent = data.model;
    } catch {
      // Labels locais continuam disponíveis quando a API de configurações falha.
    }
  }

  function validScore(entry) {
    return entry && Number.isFinite(entry.correct_pct) && Number.isFinite(entry.unsupported_claim_detected_pct) && Number.isFinite(entry.n);
  }

  function scoreCard(id, entry, best) {
    const card = node("article", `benchmark-card${id === best ? " is-best" : ""}`);
    const top = node("div", "benchmark-mode");
    top.append(node("span", "", { baseline: "Sem contexto", rag: "Com documentos", agent: "Agente" }[id]));
    top.append(node("span", "mode-mark", { baseline: "○", rag: "◉", agent: "✦" }[id]));
    card.append(top);
    card.append(node("div", "benchmark-value", `${percent.format(entry.correct_pct)}%`));
    card.append(node("p", "benchmark-caption", "Respostas corretas com gabarito"));
    const track = node("div", "accuracy-track");
    track.setAttribute("role", "img");
    track.setAttribute("aria-label", `${percent.format(entry.correct_pct)}% de respostas corretas`);
    const fill = node("span");
    fill.style.width = `${Math.max(0, Math.min(100, entry.correct_pct))}%`;
    track.append(fill);
    card.append(track);
    const footer = node("div", "benchmark-footer");
    const cases = node("span", "", "Casos avaliados");
    cases.prepend(node("strong", "", entry.n));
    const latency = node("span", "", "Latência média");
    latency.prepend(node("strong", "", Number.isFinite(entry.mean_latency_ms) ? `${Math.round(entry.mean_latency_ms)} ms` : "—"));
    footer.append(cases, latency);
    card.append(footer);
    return card;
  }

  function unsupportedRow(id, entry) {
    const row = node("div", "unsupported-row");
    const label = { baseline: "Sem contexto", rag: "Com documentos", agent: "Agente" }[id];
    row.append(node("span", "bar-name", label));
    const track = node("div", "unsupported-track");
    track.setAttribute("role", "img");
    track.setAttribute("aria-label", `${label}: ${percent.format(entry.unsupported_claim_detected_pct)}% de afirmações sem suporte detectadas`);
    const fill = node("span");
    fill.style.width = `${Math.max(0, Math.min(100, entry.unsupported_claim_detected_pct))}%`;
    track.append(fill);
    row.append(track, node("strong", "bar-value", `${percent.format(entry.unsupported_claim_detected_pct)}%`));
    return row;
  }

  async function loadEvaluation() {
    const status = document.querySelector("#evaluation-status");
    const content = document.querySelector("#evaluation-content");
    const grid = document.querySelector("#benchmark-grid");
    const bars = document.querySelector("#unsupported-bars");
    const caseCount = document.querySelector("#case-count");
    const teaser = document.querySelector("#score-teaser-copy");
    try {
      const scores = await fetchJson("/evaluation/results", 8000);
      const ids = ["baseline", "rag", "agent"];
      if (!ids.every(id => validScore(scores[id]))) throw new Error("Placar incompleto");
      const best = ids.reduce((winner, id) => scores[id].correct_pct > scores[winner].correct_pct ? id : winner, ids[0]);
      clear(grid);
      clear(bars);
      for (const id of ids) {
        grid.append(scoreCard(id, scores[id], best));
        bars.append(unsupportedRow(id, scores[id]));
      }
      const counts = ids.map(id => scores[id].n);
      caseCount.textContent = counts.every(count => count === counts[0]) ? `${counts[0]} casos por configuração` : "Casos avaliados por configuração";
      teaser.textContent = `No conjunto salvo, o agente acertou ${percent.format(scores.agent.correct_pct)}% dos casos, frente a ${percent.format(scores.baseline.correct_pct)}% sem contexto.`;
      status.hidden = true;
      content.hidden = false;
    } catch {
      status.textContent = "Os resultados da avaliação ainda não estão disponíveis nesta instância. Execute a avaliação para preencher o placar.";
      caseCount.textContent = "Placar indisponível";
      teaser.textContent = "O placar não está disponível nesta instância. A consulta ao modelo continua acessível.";
    }
  }

  function auditCard(title, values, denominator, note) {
    const card = node("section", "audit-card");
    card.append(node("h4", "", title));
    for (const [label, numerator] of values) {
      const row = node("div", "audit-row");
      row.append(node("span", "", label), node("strong", "", `${numerator}/${denominator}`));
      card.append(row);
    }
    card.append(node("p", "", note));
    return card;
  }

  async function loadAudit() {
    const panel = document.querySelector("#audit-panel");
    const grid = document.querySelector("#audit-grid");
    const finding = document.querySelector("#audit-finding");
    try {
      const audit = await fetchJson("/evaluation/audit", 8000);
      const summary = audit.summary;
      const ids = ["baseline", "rag", "agent"];
      if (!ids.every(id => summary?.[id]?.by_split?.final && Number.isFinite(summary[id].excess_refusals_on_answerable_cases))) return;
      const labels = { baseline: "Sem contexto", rag: "Com documentos", agent: "Agente" };
      const finalCount = summary.baseline.by_split.final.cases;
      const answerable = summary.baseline.answerable_cases;
      grid.append(auditCard("Acertos no teste final", ids.map(id => [labels[id], summary[id].by_split.final.official_correct]), finalCount, "Conjunto final separado dos casos de desenvolvimento."));
      grid.append(auditCard("Recusas em casos com resposta", ids.map(id => [labels[id], summary[id].excess_refusals_on_answerable_cases]), answerable, "A referência contém resposta, mas o modo recusou. Em perguntas operacionais, os modos sem ferramentas não tinham acesso aos registros."));
      const contradiction = Array.isArray(audit.deterministic_contradictions) ? audit.deterministic_contradictions.find(item => item.case_id === "O10" && item.configuration === "agent") : null;
      finding.textContent = contradiction ? "Falha confirmada: em O10/agente, uma frase contradiz ocorrências consultadas, mas o placar automático aprovou a resposta. A auditoria de alucinações por afirmação ainda está incompleta." : "O placar automático não verifica semanticamente todas as frases. A auditoria por afirmação ainda está incompleta.";
      panel.hidden = false;
    } catch {
      // A auditoria complementar pode ainda não existir; o placar principal segue disponível.
    }
  }

  function safeUrl(value) {
    if (typeof value !== "string") return null;
    try {
      const parsed = new URL(value);
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
    } catch {
      return null;
    }
  }

  function metaText(data) {
    const items = [];
    const configuration = data.metadata?.configuration;
    if (modes[configuration]) items.push(`Configuração: ${modes[configuration].name}`);
    if (typeof data.metadata?.model === "string") items.push(`Modelo: ${data.metadata.model}`);
    if (Number.isFinite(data.metadata?.latency_ms)) items.push(`Tempo: ${(data.metadata.latency_ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`);
    if (data.metadata?.synthetic_operational_data) items.push("Registros sintéticos");
    return items;
  }

  function makeSourceSection(sources) {
    if (!Array.isArray(sources) || sources.length === 0) return null;
    const section = node("section", "detail-section");
    section.append(node("h4", "", "Fontes citadas"));
    const list = node("ul", "source-list");
    for (const source of sources) {
      const item = node("li", "source-item");
      item.append(node("span", "source-id", source.source_id || "Fonte"));
      const text = node("div");
      const href = safeUrl(source.url);
      if (href) {
        const link = node("a", "", source.title || source.source_id || "Abrir documento");
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        text.append(link);
      } else {
        text.append(node("strong", "", source.title || source.source_id || "Registro"));
      }
      text.append(node("small", "", source.source_type === "document" ? "Documento técnico" : "Registro operacional sintético"));
      item.append(text);
      list.append(item);
    }
    section.append(list);
    return section;
  }

  function makeActionSection(actions) {
    if (!Array.isArray(actions) || actions.length === 0) return null;
    const section = node("section", "detail-section");
    section.append(node("h4", "", "Próximas verificações sugeridas"));
    const list = node("ul", "action-list");
    for (const action of actions) list.append(node("li", "", action));
    section.append(list);
    return section;
  }

  function makeDraft(draft) {
    if (!draft || typeof draft !== "object") return null;
    const section = node("section", "draft-card");
    const top = node("div", "draft-top");
    top.append(node("h4", "", "Pré-chamado para revisão"), node("span", "draft-status", "Pendente de aprovação humana"));
    section.append(top);
    const meta = node("div", "draft-meta");
    if (draft.event_id) meta.append(node("span", "", `Ocorrência ${draft.event_id}`));
    if (draft.point_id) meta.append(node("span", "", `Ponto ${draft.point_id}`));
    if (draft.priority) meta.append(node("span", "", `Prioridade ${draft.priority}`));
    section.append(meta);
    if (draft.justification) section.append(node("p", "", draft.justification));
    if (Array.isArray(draft.evidence_ids) && draft.evidence_ids.length) {
      section.append(node("p", "", `Evidências vinculadas: ${draft.evidence_ids.join(", ")}.`));
    }
    if (Array.isArray(draft.checklist) && draft.checklist.length) {
      section.append(node("h5", "", "Checklist sugerido"));
      const list = node("ul");
      for (const action of draft.checklist) list.append(node("li", "", action));
      section.append(list);
    }
    section.append(node("p", "draft-disclaimer", "Rascunho somente de leitura. Nenhuma ocorrência foi alterada."));
    return section;
  }

  function recordSummary(record) {
    const parts = [];
    for (const [key, label] of Object.entries(recordLabels)) {
      if (!Object.prototype.hasOwnProperty.call(record, key)) continue;
      let value = record[key];
      if (typeof value === "boolean") value = value ? "sim" : "não";
      if (value === null || typeof value === "object") continue;
      parts.push(`${label}: ${value}`);
    }
    return parts.join(" · ");
  }

  function makeTechnicalDetails(data) {
    const trace = Array.isArray(data.metadata?.tool_trace) ? data.metadata.tool_trace : [];
    const retrieval = Array.isArray(data.metadata?.retrieval) ? data.metadata.retrieval : [];
    if (!trace.length && !retrieval.length) return null;
    const details = node("details", "technical-details");
    details.append(node("summary", "", "Ver percurso técnico da resposta"));
    if (trace.length) {
      details.append(node("h4", "", "Consultas executadas"));
      const list = node("ol", "trace-list");
      for (const item of trace) {
        const row = node("li", "trace-row");
        row.append(node("span", "trace-name", toolNames[item.tool] || item.tool || "Ferramenta"));
        row.append(node("span", "trace-count", `${Number.isFinite(item.result_count) ? item.result_count : 0} registro(s)`));
        const args = item.arguments && typeof item.arguments === "object" ? Object.entries(item.arguments).map(([key, value]) => `${key}: ${value}`).join(" · ") : "";
        if (args) row.append(node("span", "trace-arg", args));
        list.append(row);
      }
      details.append(list);
      const method = data.metadata?.tool_selection_method;
      if (typeof method === "string" && method.includes("fallback")) {
        details.append(node("p", "technical-note", "Seleção das consultas: regras determinísticas de recuperação quando o plano da LLM não trouxe as evidências necessárias."));
      } else if (typeof method === "string" && method.includes("required_evidence")) {
        details.append(node("p", "technical-note", "Consultas complementares obrigatórias foram incluídas para verificar a resposta."));
      }
    }
    if (retrieval.length) {
      details.append(node("h4", "", "Trechos documentais recuperados"));
      const list = node("ul", "record-list");
      for (const item of retrieval) {
        const row = node("li", "record-card");
        row.append(node("strong", "", item.chunk_id || "Trecho"));
        if (Number.isFinite(item.score)) row.append(node("span", "", `Similaridade: ${item.score.toLocaleString("pt-BR", { maximumFractionDigits: 3 })}`));
        list.append(row);
      }
      details.append(list);
    }
    const ids = new Set((data.sources || []).map(source => source.source_id));
    for (const id of data.draft_work_order?.evidence_ids || []) ids.add(id);
    const seen = new Set();
    const records = [];
    for (const call of trace) {
      for (const record of Array.isArray(call.result) ? call.result : []) {
        if (ids.has(record.id) && !seen.has(record.id)) {
          seen.add(record.id);
          records.push(record);
        }
      }
    }
    if (records.length) {
      details.append(node("h4", "", "Registros citados"));
      const list = node("ul", "record-list");
      for (const record of records) {
        const row = node("li", "record-card");
        row.append(node("strong", "", record.id));
        row.append(node("span", "", recordSummary(record)));
        list.append(row);
      }
      details.append(list);
    }
    return details;
  }

  function renderAnswer(data) {
    clear(answerContent);
    answerEmpty.hidden = true;
    answerContent.hidden = false;
    const head = node("div", "answer-head");
    const title = node("div");
    title.append(node("span", "eyebrow", "RESPOSTA DO MODELO LOCAL"), node("h3", "", "Resultado da consulta"));
    head.append(title);
    let badgeText = "Sem fontes externas";
    let badgeClass = "result-badge is-general";
    if (data.refused) { badgeText = "Evidência insuficiente"; badgeClass = "result-badge is-refusal"; }
    else if (data.supported) { badgeText = "Com fontes citadas"; badgeClass = "result-badge"; }
    head.append(node("span", badgeClass, badgeText));
    answerContent.append(head);
    answerContent.append(node("p", "answer-body", data.answer || "Resposta indisponível."));
    if (data.reason) answerContent.append(node("p", "answer-reason", `Motivo: ${data.reason}`));
    const metadata = metaText(data);
    if (metadata.length) {
      const meta = node("div", "answer-metadata");
      for (const item of metadata) meta.append(node("span", "", item));
      answerContent.append(meta);
    }
    for (const section of [makeSourceSection(data.sources), makeActionSection(data.suggested_actions), makeDraft(data.draft_work_order), makeTechnicalDetails(data)]) {
      if (section) answerContent.append(section);
    }
    answerPanel.focus({ preventScroll: true });
    answerPanel.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  function renderError(message) {
    clear(answerContent);
    answerEmpty.hidden = true;
    answerContent.hidden = false;
    answerContent.append(node("span", "eyebrow", "CONSULTA NÃO CONCLUÍDA"));
    answerContent.append(node("h3", "", "Não foi possível obter a resposta"));
    const error = node("p", "answer-error", message);
    error.setAttribute("role", "alert");
    answerContent.append(error);
    answerPanel.focus({ preventScroll: true });
  }

  async function submitQuestion(event) {
    event.preventDefault();
    if (activeController) return;
    const text = question.value.trim();
    if (text.length < 3 || text.length > 1000) {
      requestStatus.textContent = "Digite uma pergunta entre 3 e 1.000 caracteres.";
      question.focus();
      return;
    }
    const configuration = selectedMode();
    const payload = { question: text, configuration };
    if (configuration === "agent") {
      if (locationSelect.value) payload.location_id = locationSelect.value;
      if (pointSelect.value) payload.point_id = pointSelect.value;
    }
    activeController = new AbortController();
    const controller = activeController;
    const timeout = window.setTimeout(() => controller.abort(), 300000);
    askButton.disabled = true;
    cancelButton.hidden = false;
    answerPanel.setAttribute("aria-busy", "true");
    requestStatus.textContent = "Consultando o modelo local e verificando evidências…";
    try {
      const response = await fetch("/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 503) throw new Error("O modelo local está indisponível. Inicie o Ollama e tente novamente.");
        throw new Error(response.status === 422 ? "A pergunta ou os identificadores enviados são inválidos." : `A API retornou HTTP ${response.status}.`);
      }
      if (typeof data.answer !== "string" || !Array.isArray(data.sources)) throw new Error("A API retornou um formato de resposta inesperado.");
      renderAnswer(data);
      requestStatus.textContent = data.refused ? "Consulta concluída com recusa fundamentada." : "Consulta concluída.";
      loadHealth();
    } catch (error) {
      const message = error.name === "AbortError" ? "A consulta foi cancelada ou excedeu cinco minutos." : error.message || "Falha ao consultar o assistente.";
      renderError(message);
      requestStatus.textContent = "Consulta não concluída.";
      if (error.name !== "AbortError") loadHealth();
    } finally {
      window.clearTimeout(timeout);
      activeController = null;
      askButton.disabled = false;
      cancelButton.hidden = true;
      answerPanel.removeAttribute("aria-busy");
    }
  }

  form.addEventListener("submit", submitQuestion);
  form.elements.configuration.forEach(input => input.addEventListener("change", updateMode));
  locationSelect.addEventListener("change", () => updatePoints());
  cancelButton.addEventListener("click", () => activeController?.abort());
  for (const button of document.querySelectorAll("[data-example]")) {
    button.addEventListener("click", () => {
      const example = examples[button.dataset.example];
      if (!example) return;
      form.querySelector(`input[name="configuration"][value="${example.mode}"]`).checked = true;
      updateMode();
      question.value = example.question;
      locationSelect.value = example.location;
      updatePoints(example.point);
      requestStatus.textContent = "Exemplo preenchido. Clique em Consultar DrenaAssist para enviar.";
      question.focus();
    });
  }

  updatePoints();
  updateMode();
  loadHealth();
  loadConfigurations();
  loadEvaluation();
  loadAudit();
})();
