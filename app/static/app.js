(() => {
  "use strict";

  const $ = selector => document.querySelector(selector);
  const form = $("#ask-form");
  const question = $("#question");
  const locationSelect = $("#location-id");
  const pointSelect = $("#point-id");
  const clearContext = $("#clear-context");
  const quickActions = $("#quick-actions");
  const askButton = $("#ask-button");
  const cancelButton = $("#cancel-button");
  const requestStatus = $("#request-status");
  const feed = $("#answer-panel");
  const feedEmpty = $("#answer-empty");
  const feedList = $("#answer-content");

  const GAUGE_MAX_CM = 20;
  const modeNames = { agent: "Agente", agent_trained: "Agente treinado", rag: "Só documentos", baseline: "Sem contexto" };
  const accents = {
    "Galpao Norte": "Galpão Norte",
    "Condominio Ipe": "Condomínio Ipê",
    "Centro Logistico Norte": "Centro Logístico Norte"
  };
  const statusNames = {
    aguardando_manutencao: "aguardando manutenção",
    em_verificacao: "em verificação",
    concluida: "concluída"
  };
  const priorityNames = { alta: "alta", media: "média", baixa: "baixa" };
  const starterQuestions = [
    { text: "Quais ocorrências estão aguardando manutenção nas unidades monitoradas?", mode: "agent" },
    { text: "Por que a Garagem A está com prioridade alta?", mode: "agent", location: "GAR-A" },
    { text: "O que registrar quando uma caixa de captação é limpa?", mode: "agent" },
    { text: "Que sinais visuais podem indicar problema no escoamento pluvial?", mode: "agent" }
  ];
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
    point_id: "ponto",
    timestamp: "data",
    opened_at: "abertura",
    water_level_cm: "nível (cm)",
    status: "situação",
    priority: "prioridade",
    finding: "achado",
    action: "serviço"
  };
  const percent = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  let overview = null;
  let activeController = null;

  function node(tag, className, content) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined && content !== null) element.textContent = String(content);
    return element;
  }

  const pretty = value => accents[value] || value;
  const allPoints = () => (overview?.locations || []).flatMap(location => location.points.map(point => ({ ...point, location })));

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

  /* Estado do modelo local */
  async function loadHealth() {
    const dot = $("#health-dot");
    const label = $("#health-label");
    try {
      const health = await fetchJson("/health", 8000);
      $("#model-name").textContent = health.model || "";
      dot.classList.toggle("is-ready", Boolean(health.ollama_model_available));
      dot.classList.toggle("is-unavailable", !health.ollama_model_available);
      label.textContent = health.ollama_model_available ? "Modelo local ativo" : "Modelo local desligado. Inicie o Ollama";
      const trainedInput = form.querySelector('input[value="agent_trained"]');
      trainedInput.disabled = !health.trained_model_available;
      $("#trained-note").hidden = Boolean(health.trained_model_available);
      if (trainedInput.disabled && trainedInput.checked) form.elements.configuration.value = "agent";
    } catch {
      dot.classList.add("is-unavailable");
      label.textContent = "API sem resposta";
    }
  }

  /* Lista de pontos com régua de nível */
  function gauge(point) {
    const box = node("span", "gauge");
    box.setAttribute("aria-hidden", "true");
    const level = point.reading?.water_level_cm;
    const water = node("span", "gauge-water");
    water.style.height = `${Number.isFinite(level) ? Math.min(level / GAUGE_MAX_CM, 1) * 100 : 0}%`;
    const alertMark = node("span", "gauge-alert");
    alertMark.style.bottom = `${(point.alert_level_cm / GAUGE_MAX_CM) * 100}%`;
    box.append(water, alertMark);
    return box;
  }

  function pointButton(point) {
    const reading = point.reading;
    const level = reading?.water_level_cm;
    const isAlert = Number.isFinite(level) && level > point.alert_level_cm;
    const button = node("button", `point${isAlert ? " is-alert" : ""}`);
    button.type = "button";
    button.dataset.point = point.id;
    button.dataset.location = point.location.id;
    button.setAttribute("aria-pressed", "false");

    const text = node("span");
    text.append(node("span", "point-name", point.id));
    const detail = [point.name];
    if (point.type === "bomba" && reading?.pump_state) detail.push(`bomba ${reading.pump_state}`);
    text.append(node("span", "point-detail", detail.join(", ")));
    for (const event of point.open_events) {
      const cls = event.priority === "alta" ? "tag tag-high" : "tag tag-medium";
      text.append(node("span", cls, `${event.id} prioridade ${priorityNames[event.priority] || event.priority}, ${statusNames[event.status] || event.status}`));
    }
    if (point.inspection?.obstruction) text.append(node("span", "tag tag-obstruction", "obstrução vista"));

    const value = node("span", "point-level", Number.isFinite(level) ? `${decimal.format(level)} cm` : "sem leitura");
    if (Number.isFinite(level)) value.append(node("small", "", isAlert ? "acima do alerta" : "normal"));

    button.setAttribute("aria-label", `${point.id}, ${point.name}. ${Number.isFinite(level) ? `Nível ${decimal.format(level)} centímetros, ${isAlert ? "acima do alerta" : "normal"}` : "Sem leitura"}. ${point.open_events.length} ocorrência(s) aberta(s).`);
    button.append(gauge(point), text, value);
    button.addEventListener("click", () => selectPoint(point.id));
    return button;
  }

  async function loadOverview() {
    const list = $("#points-list");
    try {
      overview = await fetchJson("/operational/overview", 8000);
      list.replaceChildren();
      for (const location of overview.locations) {
        const block = node("section", "location");
        const title = node("h3", "", pretty(location.name));
        title.append(node("small", "", pretty(location.unit)));
        block.append(title);
        for (const point of location.points) block.append(pointButton({ ...point, location }));
        list.append(block);
        const option = node("option", "", pretty(location.name));
        option.value = location.id;
        locationSelect.append(option);
      }
      const points = allPoints();
      const alerts = points.filter(p => p.reading && p.reading.water_level_cm > p.alert_level_cm).length;
      const open = points.reduce((sum, p) => sum + p.open_events.length, 0);
      $("#points-summary").textContent = `${points.length} pontos, ${alerts} acima do alerta, ${open} ocorrências abertas`;
      fillPoints();
    } catch {
      $("#points-summary").textContent = "Não foi possível carregar os pontos. Verifique se a API está rodando.";
    }
  }

  function fillPoints(preferred = "") {
    const location = locationSelect.value;
    const previous = preferred || pointSelect.value;
    pointSelect.replaceChildren(node("option", "", "Qualquer ponto"));
    pointSelect.firstElementChild.value = "";
    for (const point of allPoints()) {
      if (location && point.location.id !== location) continue;
      const option = node("option", "", `${point.id} (${point.name})`);
      option.value = point.id;
      pointSelect.append(option);
    }
    pointSelect.value = [...pointSelect.options].some(option => option.value === previous) ? previous : "";
  }

  function quickFor(point) {
    const items = [
      ["Última leitura", `Qual foi a última leitura do sensor no ${point.id}?`],
      ["Tem obstrução?", `Há obstrução registrada no ${point.id}?`],
      ["Última manutenção", `Qual foi a última intervenção registrada no ${point.id}?`]
    ];
    for (const event of point.open_events) {
      items.push([`Rascunho de OS para ${event.id}`, `Prepare um rascunho de ordem de serviço para a ocorrência ${event.id}, sem alterar seu status.`]);
    }
    return items;
  }

  function renderQuick() {
    quickActions.replaceChildren();
    const point = allPoints().find(p => p.id === pointSelect.value);
    if (!point) return;
    for (const [label, text] of quickFor(point)) {
      const chip = node("button", "chip", label);
      chip.type = "button";
      chip.title = text;
      chip.addEventListener("click", () => { question.value = text; form.requestSubmit(); });
      quickActions.append(chip);
    }
  }

  function syncSelection() {
    for (const button of document.querySelectorAll(".point")) {
      button.setAttribute("aria-pressed", String(button.dataset.point === pointSelect.value));
    }
    clearContext.hidden = !locationSelect.value && !pointSelect.value;
    renderQuick();
  }

  function selectPoint(pointId) {
    const point = allPoints().find(p => p.id === pointId);
    if (!point) return;
    if (pointSelect.value === pointId) { resetContext(); return; }
    locationSelect.value = point.location.id;
    fillPoints(point.id);
    if (form.elements.configuration.value !== "agent_trained") form.elements.configuration.value = "agent";
    syncSelection();
    question.focus();
  }

  function resetContext() {
    locationSelect.value = "";
    fillPoints();
    syncSelection();
  }

  function renderStarters() {
    const box = $("#starter-questions");
    for (const item of starterQuestions) {
      const chip = node("button", "chip", item.text);
      chip.type = "button";
      chip.addEventListener("click", () => {
        locationSelect.value = item.location || "";
        fillPoints();
        syncSelection();
        form.elements.configuration.value = item.mode;
        question.value = item.text;
        form.requestSubmit();
      });
      box.append(chip);
    }
  }

  /* Resposta */
  function safeUrl(value) {
    if (typeof value !== "string") return null;
    try {
      const parsed = new URL(value);
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
    } catch {
      return null;
    }
  }

  function sourceSection(sources) {
    if (!Array.isArray(sources) || sources.length === 0) return [];
    const list = node("ul", "source-list");
    for (const source of sources) {
      const item = node("li", "source-item");
      item.append(node("span", "source-id", source.source_id || "Fonte"));
      const text = node("span");
      const href = safeUrl(source.url);
      if (href) {
        const link = node("a", "", source.title || source.source_id);
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        text.append(link, node("small", "", "documento técnico"));
      } else {
        text.append(node("span", "", source.source_type === "document" ? (source.title || "Documento") : "Registro da central"), node("small", "", "dados de demonstração"));
      }
      item.append(text);
      list.append(item);
    }
    return [node("h4", "", "De onde veio"), list];
  }

  function actionSection(actions) {
    if (!Array.isArray(actions) || actions.length === 0) return [];
    const list = node("ul", "action-list");
    for (const action of actions) list.append(node("li", "", action));
    return [node("h4", "", "O que verificar"), list];
  }

  function draftSection(draft) {
    if (!draft || typeof draft !== "object") return [];
    const box = node("section", "draft");
    const title = node("h4", "", "Rascunho de ordem de serviço");
    title.append(node("span", "draft-status", "Aguardando aprovação de um responsável"));
    box.append(title);
    const facts = [];
    if (draft.event_id) facts.push(`Ocorrência ${draft.event_id}`);
    if (draft.point_id) facts.push(`ponto ${draft.point_id}`);
    if (draft.priority) facts.push(`prioridade ${draft.priority}`);
    if (facts.length) box.append(node("p", "", facts.join(", ")));
    if (draft.justification) box.append(node("p", "", draft.justification));
    if (Array.isArray(draft.evidence_ids) && draft.evidence_ids.length) box.append(node("p", "", `Evidências: ${draft.evidence_ids.join(", ")}`));
    if (Array.isArray(draft.checklist) && draft.checklist.length) {
      const list = node("ul");
      for (const step of draft.checklist) list.append(node("li", "", step));
      box.append(list);
    }
    box.append(node("p", "trace-note", "Nada foi alterado na ocorrência. O serviço só é aberto depois da aprovação."));
    return [box];
  }

  function recordSummary(record) {
    const parts = [];
    for (const [key, label] of Object.entries(recordLabels)) {
      const value = record[key];
      if (value === undefined || value === null || typeof value === "object") continue;
      parts.push(`${label}: ${typeof value === "boolean" ? (value ? "sim" : "não") : statusNames[value] || value}`);
    }
    return parts.join(", ");
  }

  function traceSection(data) {
    const trace = Array.isArray(data.metadata?.tool_trace) ? data.metadata.tool_trace : [];
    const retrieval = Array.isArray(data.metadata?.retrieval) ? data.metadata.retrieval : [];
    if (!trace.length && !retrieval.length) return [];
    const details = node("details", "trace");
    details.append(node("summary", "", "Ver o que a IA consultou"));
    if (retrieval.length) {
      details.append(node("p", "", "Trechos de documentos encontrados pela busca:"));
      const list = node("ul");
      for (const item of retrieval) {
        const row = node("li", "", item.chunk_id || "trecho");
        if (Number.isFinite(item.score)) row.append(node("span", "trace-arg", ` similaridade ${item.score.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}`));
        list.append(row);
      }
      details.append(list);
    }
    if (trace.length) {
      details.append(node("p", "", "Consultas aos registros, somente leitura:"));
      const list = node("ol");
      const cited = new Set((data.sources || []).map(s => s.source_id));
      for (const call of trace) {
        const row = node("li", "", toolNames[call.tool] || call.tool);
        const args = call.arguments && typeof call.arguments === "object" ? Object.values(call.arguments).join(", ") : "";
        row.append(node("span", "trace-arg", ` ${args ? `(${args}) ` : ""}${Number.isFinite(call.result_count) ? call.result_count : 0} registro(s)`));
        const records = (Array.isArray(call.result) ? call.result : []).filter(r => cited.has(r.id));
        if (records.length) {
          const inner = node("ul");
          for (const record of records) inner.append(node("li", "", `${record.id}: ${recordSummary(record)}`));
          row.append(inner);
        }
        list.append(row);
      }
      details.append(list);
      const method = data.metadata?.tool_selection_method;
      if (typeof method === "string" && method.includes("fallback")) {
        details.append(node("p", "trace-note", "Parte das consultas foi incluída por regra fixa, porque o plano da IA não trouxe toda a evidência necessária."));
      }
    }
    return [details];
  }

  function addEntry(asked, mode, data, errorMessage) {
    feedEmpty.hidden = true;
    const entry = node("li", "entry");
    const head = node("div", "entry-question");
    head.append(node("p", "", asked), node("span", "entry-mode", modeNames[mode]));
    entry.append(head);
    if (errorMessage) {
      entry.classList.add("is-error");
      const error = node("p", "entry-answer", errorMessage);
      error.setAttribute("role", "alert");
      entry.append(error);
    } else {
      if (data.refused) entry.classList.add("is-refusal");
      entry.append(node("p", "entry-answer", data.answer || "Resposta vazia."));
      if (data.reason && data.refused) entry.append(node("p", "entry-reason", data.reason));
      const meta = [];
      if (typeof data.metadata?.model === "string") meta.push(data.metadata.model);
      if (Number.isFinite(data.metadata?.latency_ms)) meta.push(`${decimal.format(data.metadata.latency_ms / 1000)} s`);
      if (meta.length) entry.append(node("p", "entry-meta", `Respondido por ${meta.join(" em ")}`));
      entry.append(...sourceSection(data.sources), ...actionSection(data.suggested_actions), ...draftSection(data.draft_work_order), ...traceSection(data));
    }
    feedList.prepend(entry);
    feed.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  async function submitQuestion(event) {
    event.preventDefault();
    if (activeController) return;
    const text = question.value.trim();
    if (text.length < 3 || text.length > 1000) {
      requestStatus.textContent = "Escreva uma pergunta entre 3 e 1.000 caracteres.";
      question.focus();
      return;
    }
    const mode = form.elements.configuration.value;
    const payload = { question: text, configuration: mode };
    if (mode === "agent" || mode === "agent_trained") {
      if (locationSelect.value) payload.location_id = locationSelect.value;
      if (pointSelect.value) payload.point_id = pointSelect.value;
    }
    activeController = new AbortController();
    const controller = activeController;
    const timeout = window.setTimeout(() => controller.abort(), 300000);
    askButton.disabled = true;
    cancelButton.hidden = false;
    feed.setAttribute("aria-busy", "true");
    requestStatus.textContent = mode === "agent_trained"
      ? "Consultando o modelo treinado. Ele roda em 4 bits e leva de 20 a 40 s por resposta."
      : "Consultando o modelo local. A primeira pergunta pode levar até 20 s.";
    try {
      const response = await fetch("/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 503) throw new Error("O modelo local está desligado. Inicie o Ollama e pergunte de novo.");
        throw new Error(response.status === 422 ? "A pergunta ou o ponto selecionado não foi aceito pela API." : `A API respondeu com erro ${response.status}.`);
      }
      if (typeof data.answer !== "string" || !Array.isArray(data.sources)) throw new Error("A API devolveu uma resposta em formato inesperado.");
      addEntry(text, mode, data);
      requestStatus.textContent = data.refused ? "Sem evidência suficiente: a IA recusou responder." : "Resposta pronta.";
      question.value = "";
    } catch (error) {
      addEntry(text, mode, null, error.name === "AbortError" ? "Consulta cancelada." : error.message || "Falha ao consultar a IA.");
      requestStatus.textContent = "";
      loadHealth();
    } finally {
      window.clearTimeout(timeout);
      activeController = null;
      askButton.disabled = false;
      cancelButton.hidden = true;
      feed.removeAttribute("aria-busy");
    }
  }

  /* Avaliação */
  const evalNames = { baseline: "Sem contexto", rag: "Só documentos", agent: "Agente" };

  function scoreCard(id, entry, best) {
    const card = node("article", `benchmark-card${id === best ? " is-best" : ""}`);
    card.append(node("div", "benchmark-mode", evalNames[id]));
    card.append(node("div", "benchmark-value", `${percent.format(entry.correct_pct)}%`));
    card.append(node("p", "benchmark-caption", "respostas corretas pelo gabarito"));
    const track = node("div", "accuracy-track");
    track.setAttribute("role", "img");
    track.setAttribute("aria-label", `${percent.format(entry.correct_pct)}% corretas`);
    const fill = node("span");
    fill.style.width = `${Math.max(0, Math.min(100, entry.correct_pct))}%`;
    track.append(fill);
    card.append(track);
    const footer = node("div", "benchmark-footer");
    const cases = node("span", "", "perguntas");
    cases.prepend(node("strong", "", entry.n));
    const latency = node("span", "", "tempo médio");
    latency.prepend(node("strong", "", Number.isFinite(entry.mean_latency_ms) ? `${decimal.format(entry.mean_latency_ms / 1000)} s` : "-"));
    footer.append(cases, latency);
    card.append(footer);
    return card;
  }

  async function loadEvaluation() {
    const status = $("#evaluation-status");
    try {
      const scores = await fetchJson("/evaluation/results", 8000);
      const ids = ["baseline", "rag", "agent"];
      if (!ids.every(id => scores[id] && Number.isFinite(scores[id].correct_pct))) throw new Error("Placar incompleto");
      const best = ids.reduce((win, id) => scores[id].correct_pct > scores[win].correct_pct ? id : win, ids[0]);
      const grid = $("#benchmark-grid");
      const bars = $("#unsupported-bars");
      for (const id of ids) {
        grid.append(scoreCard(id, scores[id], best));
        const row = node("div", "unsupported-row");
        const track = node("div", "unsupported-track");
        const fill = node("span");
        fill.style.width = `${Math.max(0, Math.min(100, scores[id].unsupported_claim_detected_pct))}%`;
        track.append(fill);
        row.append(node("span", "", evalNames[id]), track, node("strong", "bar-value", `${percent.format(scores[id].unsupported_claim_detected_pct)}%`));
        bars.append(row);
      }
      $("#case-count").textContent = `${scores.agent.n} perguntas por modo, ${scores.agent.n * 3} respostas reais`;
      status.hidden = true;
      $("#evaluation-content").hidden = false;
    } catch {
      status.textContent = "O placar ainda não foi gerado nesta instalação. Rode python -m avaliacao.run --phase all --fresh.";
      $("#case-count").textContent = "";
    }
  }

  async function loadAudit() {
    try {
      const audit = await fetchJson("/evaluation/audit", 8000);
      const summary = audit.summary;
      const ids = ["baseline", "rag", "agent"];
      if (!ids.every(id => summary?.[id]?.by_split?.final)) return;
      const grid = $("#audit-grid");
      const card = (title, values, denominator, note) => {
        const box = node("section", "audit-card");
        box.append(node("h3", "", title));
        for (const [label, value] of values) {
          const row = node("div", "audit-row");
          row.append(node("span", "", label), node("strong", "", `${value}/${denominator}`));
          box.append(row);
        }
        box.append(node("p", "", note));
        return box;
      };
      grid.append(card("Acertos no teste final", ids.map(id => [evalNames[id], summary[id].by_split.final.official_correct]), summary.baseline.by_split.final.cases, "Perguntas separadas das usadas para ajustar o limiar de busca."));
      grid.append(card("Recusas em perguntas que tinham resposta", ids.map(id => [evalNames[id], summary[id].excess_refusals_on_answerable_cases]), summary.baseline.answerable_cases, "Sem acesso aos registros, os modos sem agente recusam as perguntas operacionais."));
      $("#audit-finding").textContent = "O placar automático não lê cada frase. Na pergunta O10 o agente se contradisse e mesmo assim foi aprovado; esse caso está entre os cinco erros documentados.";
      $("#audit-panel").hidden = false;
    } catch {
      // Sem auditoria, o placar principal continua visível.
    }
  }

  async function loadTrained() {
    try {
      const board = await fetchJson("/evaluation/trained", 8000);
      if (!board.agent || !board.agent_trained) return;
      const grid = $("#trained-grid");
      const names = { agent: "Agente (modelo base)", agent_trained: "Agente treinado (LoRA)" };
      for (const id of ["agent", "agent_trained"]) {
        const box = node("section", "audit-card");
        box.append(node("h3", "", names[id]));
        const rows = [
          ["Corretas", `${percent.format(board[id].correct_pct)}%`],
          ["Teste final", `${board[id].final_correct}/${board[id].final_n}`],
          ["Citações válidas", `${percent.format(board[id].valid_citation_pct)}%`],
          ["Tempo médio", `${decimal.format(board[id].mean_latency_ms / 1000)} s`]
        ];
        for (const [label, value] of rows) {
          const row = node("div", "audit-row");
          row.append(node("span", "", label), node("strong", "", value));
          box.append(row);
        }
        grid.append(box);
      }
      $("#trained-panel").hidden = false;
    } catch {
      // Sem avaliação do modelo treinado, o restante do placar continua visível.
    }
  }

  /* Navegação entre central e avaliação */
  function showView() {
    const view = location.hash === "#avaliacao" ? "avaliacao" : "consulta";
    $("#view-consulta").hidden = view !== "consulta";
    $("#view-avaliacao").hidden = view !== "avaliacao";
    for (const link of document.querySelectorAll("[data-view]")) {
      if (link.dataset.view === view) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  }

  form.addEventListener("submit", submitQuestion);
  locationSelect.addEventListener("change", () => { fillPoints(); syncSelection(); });
  pointSelect.addEventListener("change", syncSelection);
  clearContext.addEventListener("click", resetContext);
  cancelButton.addEventListener("click", () => activeController?.abort());
  question.addEventListener("keydown", event => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) form.requestSubmit();
  });
  window.addEventListener("hashchange", showView);

  showView();
  renderStarters();
  loadHealth();
  loadOverview();
  loadEvaluation();
  loadAudit();
  loadTrained();
})();
