"use strict";

const $ = (id) => document.getElementById(id);
const originLabels = { real: "Real", synthetic: "Sintético", unverified: "Não verificada" };
const reviewLabels = { not_applicable: "Não se aplica", pending: "Revisão pendente", reviewed: "Revisado" };
const factLabels = {
  water_level_cm: "Nível de água",
  in_attention: "Em atenção",
  sensor_status: "Estado do sensor",
  unit: "Unidade",
  precipitation_mm: "Precipitação",
  latitude: "Latitude",
  longitude: "Longitude",
  source: "Fonte dos dados",
  license: "Licença",
  scope: "Escopo",
  event_id: "ID do evento",
  model_version: "Versão do modelo",
  input_type: "Tipo de entrada",
  detected_classes: "Classes detectadas",
  detection_count: "Detecções",
  status: "Estado do evento",
  inspection_recommended: "Inspeção recomendada",
  evidence_uri: "URI da evidência",
  timestamp_scope: "Significado do horário",
};
const factValueLabels = {
  analysis_time_not_capture_time: "Hora da análise, não da captura",
  sem_deteccao: "Sem detecção",
  revisao_recomendada: "Revisão recomendada",
  revisado: "Revisado",
};

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = String(content);
  return node;
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Horário inválido no registro";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "America/Sao_Paulo",
  }).format(date) + " · São Paulo";
}

function formatFact(key, value) {
  if (value === null || value === undefined || value === "") return "Não informado";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "Nenhuma";
  if (typeof value === "number") {
    const formatted = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(value);
    return key === "water_level_cm" ? formatted + " cm" : key === "precipitation_mm" ? formatted + " mm/h" : formatted;
  }
  return factValueLabels[value] || String(value);
}

function safeHttpUrl(value) {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch (_) {
    return null;
  }
}

async function getJson(url) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal: controller.signal });
    if (!response.ok) {
      throw new ApiError(response.status, response.status === 503 ? "Fonte indisponível nesta instância" : `HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new ApiError(503, "A fonte não respondeu dentro do prazo");
    if (error instanceof TypeError) throw new ApiError(503, "Não foi possível contatar a API local");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function postJson(url, body) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 75000);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) throw new ApiError(response.status, `HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new ApiError(503, "A consulta excedeu o prazo");
    if (error instanceof TypeError) throw new ApiError(503, "Não foi possível contatar a API local");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function showMessage(container, tone, icon, title, detail) {
  const wrap = element("div", `result-message ${tone}`);
  wrap.append(element("span", "", icon), element("strong", "", title), element("p", "", detail));
  container.replaceChildren(wrap);
}

function showFailure(container, error, emptyMessage) {
  if (error instanceof ApiError && error.status === 404) {
    showMessage(container, "is-empty", "○", "Sem registro para este ID", emptyMessage);
  } else if (error instanceof ApiError && error.status === 503) {
    showMessage(container, "is-unavailable", "!", "Fonte indisponível", "A fonte não respondeu ou não está configurada nesta instância. Tente novamente quando estiver disponível.");
  } else {
    showMessage(container, "is-error", "!", "Consulta não concluída", "Confira o ID e tente novamente. Se o problema persistir, verifique a API local.");
  }
}

function addMeta(container, label, value, asLink = false) {
  if (value === null || value === undefined || value === "") return;
  const row = element("p");
  row.append(element("strong", "", label + ":"));
  if (asLink) {
    const url = safeHttpUrl(value);
    if (url) {
      const link = element("a", "", value);
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      row.append(link);
    } else {
      row.append(document.createTextNode(" " + value));
    }
  } else {
    row.append(document.createTextNode(" " + value));
  }
  container.append(row);
}

function evidenceCard(evidence) {
  if (!evidence || typeof evidence !== "object" || typeof evidence.source_system !== "string" || typeof evidence.source_record_id !== "string") {
    throw new Error("Registro de evidência inválido");
  }
  const facts = evidence.facts && typeof evidence.facts === "object" ? evidence.facts : {};
  const card = element("article", "evidence-card");
  const top = element("div", "evidence-top");
  top.append(element("strong", "", evidence.source_point_id || (evidence.kind === "precipitation" ? "Grade histórica" : "Registro sem ponto")));
  top.append(element("span", `origin-chip origin-${evidence.data_origin || "unverified"}`, originLabels[evidence.data_origin] || "Origem não informada"));
  card.append(top);

  let headlineValue = null;
  let headlineLabel = null;
  let headlineKey = null;
  if (evidence.kind === "water_level" && typeof facts.water_level_cm === "number") {
    headlineValue = formatFact("water_level_cm", facts.water_level_cm);
    headlineLabel = "Nível de água";
    headlineKey = "water_level_cm";
  } else if (evidence.kind === "precipitation" && typeof facts.precipitation_mm === "number") {
    headlineValue = formatFact("precipitation_mm", facts.precipitation_mm);
    headlineLabel = "Chuva histórica";
    headlineKey = "precipitation_mm";
  } else if (evidence.kind === "vision_detection" && typeof facts.detection_count === "number") {
    headlineValue = formatFact("detection_count", facts.detection_count);
    headlineLabel = facts.detection_count === 1 ? "Detecção registrada" : "Detecções registradas";
    headlineKey = "detection_count";
  }
  if (headlineValue !== null) {
    const metric = element("div", "evidence-metric");
    metric.append(element("strong", "", headlineValue), element("span", "", headlineLabel));
    card.append(metric);
  }

  const details = element("dl", "evidence-facts");
  for (const [key, value] of Object.entries(facts)) {
    if (key === headlineKey || (key === "unit" && headlineValue !== null)) continue;
    const item = element("div", key === "scope" || key === "evidence_uri" || key === "timestamp_scope" ? "span-two" : "");
    item.append(element("dt", "", factLabels[key] || key), element("dd", "", formatFact(key, value)));
    details.append(item);
  }
  if (evidence.kind === "vision_detection") {
    const item = element("div");
    item.append(element("dt", "", "Revisão"), element("dd", "", reviewLabels[evidence.review_status] || "Não informada"));
    details.append(item);
  }
  card.append(details);

  const meta = element("div", "evidence-meta");
  addMeta(meta, evidence.kind === "vision_detection" ? "Análise registrada" : "Observado em", evidence.observed_at ? formatTime(evidence.observed_at) : null);
  addMeta(meta, "Coletado pela fonte", evidence.collected_at ? formatTime(evidence.collected_at) : null);
  addMeta(meta, "Snapshot da exportação", evidence.snapshot_at ? formatTime(evidence.snapshot_at) : null);
  addMeta(meta, "Consultado em", evidence.retrieved_at ? formatTime(evidence.retrieved_at) : null);
  addMeta(meta, "Ponto canônico verificado", evidence.canonical_point_id);
  addMeta(meta, "Referência", `${evidence.source_system}:${evidence.source_record_id}`);
  if (evidence.source_uri) addMeta(meta, "Registro na fonte", evidence.source_uri, true);
  else addMeta(meta, "Fonte", evidence.source_system === "drenadata" ? "DrenaData · exportação Ouro local" : "DrenaVision · API de eventos");
  card.append(meta);
  if (evidence.kind === "vision_detection") {
    card.append(element("p", "evidence-note", "Horário da análise; a hora e a origem da captura não foram atestadas por esta integração."));
  }
  return card;
}

function showEvidence(container, records) {
  const stack = element("div", "evidence-stack");
  for (const record of records) stack.append(evidenceCard(record));
  container.replaceChildren(stack);
}

function setSourceState(id, configured) {
  const node = $(id);
  node.className = `source-state ${configured ? "state-configured" : "state-unconfigured"}`;
  node.textContent = configured ? "Configurada" : "Não configurada";
}

function setAdaptedMode(trainingInfo) {
  const ready = Boolean(trainingInfo && trainingInfo.adapter_runtime_available);
  const configured = ready || Boolean(trainingInfo && trainingInfo.adapter_runtime_configured);
  const adapted = $("agent-mode-adapted");
  adapted.disabled = !configured;
  if (!configured && adapted.checked) $("agent-form").querySelector('input[name="model_mode"][value="base"]').checked = true;
  $("adapted-mode-note").textContent = ready
    ? "Inferência adaptada pronta nesta instância; o resultado ainda exige revisão humana."
    : configured
      ? "Adapter configurado; o modelo carrega na primeira consulta. O resultado ainda exige revisão humana."
      : "Inferência adaptada indisponível nesta instância; use o modelo base.";
  return { ready, configured };
}

let dataCatalogHint = "Carregando IDs da DrenaData.";

function setDataCatalogMessage(label, hint, tone, title, description) {
  const select = $("data-point-id");
  select.replaceChildren(element("option", "", label));
  select.firstChild.value = "";
  select.disabled = true;
  $("data-form").querySelector("button").disabled = true;
  $("data-catalog-hint").textContent = hint;
  dataCatalogHint = hint;
  if ($("agent-source").value === "drenadata_latest") $("agent-point-hint").textContent = hint;
  showMessage($("data-result"), tone, tone === "is-empty" ? "○" : "!", title, description);
}

async function loadPointCatalog() {
  try {
    const catalog = await getJson("/v2/drenadata/points");
    if (!catalog || !Array.isArray(catalog.point_ids) || catalog.point_ids.some((id) => typeof id !== "string" || !id.trim())) {
      throw new Error("Catálogo de pontos inválido");
    }
    const ids = [...new Set(catalog.point_ids)];
    const suggestions = $("agent-data-points");
    suggestions.replaceChildren(...ids.map((id) => {
      const option = element("option");
      option.value = id;
      return option;
    }));
    if (!ids.length) {
      agentPointIds.drenadata_latest = "";
      setDataCatalogMessage("Nenhum ponto no snapshot", "O snapshot respondeu, mas não contém IDs de pontos.", "is-empty", "Sem pontos neste snapshot", "A fonte respondeu com um catálogo vazio; não há ponto para consultar.");
      return;
    }
    const select = $("data-point-id");
    select.replaceChildren(...ids.map((id) => {
      const option = element("option", "", id);
      option.value = id;
      return option;
    }));
    select.disabled = false;
    $("data-form").querySelector("button").disabled = false;
    agentPointIds.drenadata_latest = ids[0];
    if ($("agent-source").value === "drenadata_latest") $("agent-point-id").value = ids[0];
    dataCatalogHint = `IDs do snapshot da DrenaData${catalog.snapshot_at ? ` · ${formatTime(catalog.snapshot_at)}` : ""}. Pontos e leituras sintéticos.`;
    $("data-catalog-hint").textContent = dataCatalogHint;
    if ($("agent-source").value === "drenadata_latest") $("agent-point-hint").textContent = dataCatalogHint;
    await queryData();
  } catch (error) {
    const unavailable = error instanceof ApiError && error.status === 503;
    setDataCatalogMessage(
      unavailable ? "Fonte indisponível" : "Catálogo não disponível",
      unavailable ? "A fonte não respondeu ao catálogo de pontos." : "Não foi possível ler o catálogo de pontos.",
      unavailable ? "is-unavailable" : "is-error",
      unavailable ? "Fonte indisponível" : "Catálogo inválido",
      unavailable ? "Não foi possível consultar os pontos da DrenaData nesta instância." : "O catálogo de pontos não pôde ser interpretado. Confira a API local.",
    );
  }
}

async function loadSources() {
  try {
    const sources = await getJson("/v2/sources");
    setSourceState("source-data-status", Boolean(sources.drenadata && sources.drenadata.configured));
    setSourceState("source-vision-status", Boolean(sources.drenavision && sources.drenavision.configured));
    const training = $("training-status");
    const trainingExplanation = $("training-explanation");
    const complete = Boolean(sources.llm_training && sources.llm_training.completed);
    const runtime = setAdaptedMode(sources.llm_training);
    training.textContent = complete ? "Concluído" : "Pendente";
    training.className = `source-state ${complete ? "state-configured" : "state-pending"}`;
    trainingExplanation.textContent = complete
      ? runtime.ready
        ? "concluído; inferência local disponível sob demanda."
        : runtime.configured
          ? "concluído; inferência local configurada e carregada na primeira consulta."
          : "concluído; adapter ainda não conectado à inferência desta API."
      : "pendente nesta instância.";
    if (sources.drenadata && sources.drenadata.configured) {
      await Promise.allSettled([loadPointCatalog(), queryRain()]);
    } else {
      setDataCatalogMessage("Fonte não configurada", "Configure a exportação Ouro para carregar os IDs de pontos.", "is-unavailable", "Fonte não configurada", "Configure a exportação Ouro da DrenaData para consultar leituras.");
      showMessage($("rain-result"), "is-unavailable", "!", "Fonte não configurada", "A chuva histórica fica disponível quando a exportação Ouro da DrenaData estiver configurada.");
    }
    if (!sources.drenavision || !sources.drenavision.configured) {
      showMessage($("vision-result"), "is-unavailable", "!", "Fonte não configurada", "Configure a URL da API DrenaVision para consultar eventos.");
    }
  } catch (_) {
    for (const id of ["source-data-status", "source-vision-status"]) {
      const node = $(id);
      node.className = "source-state state-error";
      node.textContent = "Estado desconhecido";
    }
    const training = $("training-status");
    training.className = "source-state state-error";
    training.textContent = "Estado desconhecido";
    $("training-explanation").textContent = "estado indisponível; verifique a API local.";
    setAdaptedMode(null);
    setDataCatalogMessage("API local indisponível", "Não foi possível carregar o catálogo de pontos.", "is-unavailable", "API local indisponível", "Não foi possível verificar as fontes nesta instância.");
    showMessage($("vision-result"), "is-unavailable", "!", "API local indisponível", "Não foi possível verificar as fontes nesta instância.");
  }
}

async function queryData() {
  const pointId = $("data-point-id").value.trim();
  const container = $("data-result");
  const button = $("data-form").querySelector("button");
  if (!pointId) return;
  button.disabled = true;
  container.setAttribute("aria-busy", "true");
  showMessage(container, "", "↗", "Consultando DrenaData", "Buscando a última leitura deste ID externo.");
  try {
    const record = await getJson(`/v2/drenadata/points/${encodeURIComponent(pointId)}/latest`);
    showEvidence(container, [record]);
  } catch (error) {
    showFailure(container, error, "A fonte respondeu, mas não há leitura para este ID externo.");
  } finally {
    button.disabled = false;
    container.removeAttribute("aria-busy");
  }
}

async function queryVision() {
  const pointId = $("vision-point-id").value.trim();
  const container = $("vision-result");
  const button = $("vision-form").querySelector("button");
  if (!pointId) return;
  button.disabled = true;
  container.setAttribute("aria-busy", "true");
  showMessage(container, "", "◎", "Consultando DrenaVision", "Buscando eventos deste ID externo.");
  try {
    const records = await getJson(`/v2/drenavision/events?point_id=${encodeURIComponent(pointId)}&limit=12`);
    if (!Array.isArray(records)) throw new Error("Lista de eventos inválida");
    if (records.length === 0) {
      showMessage(container, "is-empty", "○", "Nenhum evento encontrado", "A fonte respondeu e não encontrou eventos para este ID externo.");
    } else {
      showEvidence(container, records);
    }
  } catch (error) {
    showFailure(container, error, "A fonte respondeu, mas não há evento para este ID externo.");
  } finally {
    button.disabled = false;
    container.removeAttribute("aria-busy");
  }
}

async function queryRain() {
  const container = $("rain-result");
  const button = $("rain-button");
  button.disabled = true;
  container.setAttribute("aria-busy", "true");
  showMessage(container, "", "↗", "Consultando chuva histórica", "Buscando a última observação da grade piloto.");
  try {
    const records = await getJson("/v2/drenadata/precipitation/history?limit=1");
    if (!Array.isArray(records)) throw new Error("Histórico de chuva inválido");
    if (records.length === 0) {
      showMessage(container, "is-empty", "○", "Sem observações", "A exportação respondeu, mas não contém registros de chuva.");
    } else {
      showEvidence(container, [records[records.length - 1]]);
    }
  } catch (error) {
    showFailure(container, error, "A exportação respondeu, mas não contém registros de chuva.");
  } finally {
    button.disabled = false;
    container.removeAttribute("aria-busy");
  }
}

const agentPointIds = { drenadata_latest: "", drenavision_events: "" };
let activeAgentSource = $("agent-source").value;

function updateAgentSource() {
  const source = $("agent-source").value;
  const input = $("agent-point-id");
  const field = $("agent-point-field");
  const hint = $("agent-point-hint");
  if (activeAgentSource !== "rain_history") agentPointIds[activeAgentSource] = input.value.trim();
  if (source === "rain_history") {
    field.hidden = true;
    input.required = false;
    input.disabled = true;
    $("agent-question").placeholder = "O que a última observação de chuva informa sobre a grade piloto?";
  } else {
    field.hidden = false;
    input.required = true;
    input.disabled = false;
    input.value = agentPointIds[source] || "";
    if (source === "drenadata_latest") {
      input.setAttribute("list", "agent-data-points");
      input.placeholder = "Selecione um ID do catálogo";
      hint.textContent = dataCatalogHint;
      $("agent-question").placeholder = "O que a última leitura informa sobre este ponto?";
    } else {
      input.removeAttribute("list");
      input.placeholder = "Digite um point_id da DrenaVision";
      hint.textContent = "Use um ID registrado na DrenaVision. Não há vínculo automático com IDs da DrenaData.";
      $("agent-question").placeholder = "O que os eventos analisados registram para este ID?";
    }
  }
  activeAgentSource = source;
}

function showAgentState(tone, icon, title, description) {
  const container = $("agent-result");
  const state = element("div", `agent-state ${tone}`);
  state.append(element("span", "agent-state-icon", icon));
  const copy = element("div");
  copy.append(element("strong", "", title), element("p", "", description));
  state.append(copy);
  container.replaceChildren(state);
}

function showAgentFailure(error) {
  if (error instanceof ApiError && error.status === 503) {
    showAgentState("agent-unavailable", "!", "Fonte ou modelo indisponível", "A consulta não pôde ser concluída nesta instância. Isso não significa que não existam registros. Tente novamente quando a fonte e o modelo estiverem disponíveis.");
  } else if (error instanceof ApiError && error.status === 422) {
    showAgentState("agent-error", "!", "Revise os campos", "A API recusou os dados da consulta. Confira a fonte, o ID externo e a pergunta.");
  } else {
    showAgentState("agent-error", "!", "Não foi possível gerar o resultado", "Confira a API local e tente novamente. Nenhuma resposta foi confirmada.");
  }
}

function renderAgentResult(result) {
  if (!result || !["draft_requires_review", "model_refusal_requires_review", "guarded_refusal", "no_record"].includes(result.status)) {
    throw new Error("Estado do agente inválido");
  }
  const container = $("agent-result");
  const panel = element("article", `agent-answer-panel agent-${result.status}`);
  const header = element("div", "agent-answer-head");
  const heading = element("div");
  const status = {
    draft_requires_review: ["RASCUNHO · NÃO CONFIRMADO", "Rascunho para revisão humana"],
    model_refusal_requires_review: ["RECUSA DO MODELO · NÃO CONFIRMADA", "Recusa para revisão humana"],
    guarded_refusal: ["RESPOSTA BLOQUEADA", "Resposta bloqueada pela validação"],
    no_record: ["SEM REGISTRO", "Não consta na fonte consultada"],
  }[result.status];
  heading.append(element("span", "agent-answer-kicker", status[0]), element("h3", "", status[1]));
  header.append(heading, element("span", "agent-mode-tag", result.model_invoked ? `Modelo ${result.model_mode === "adapted" ? "adaptado" : "base"}` : "Sem geração"));
  panel.append(header);

  if (result.status === "draft_requires_review") {
    panel.append(element("p", "agent-review-warning", "Revisão humana obrigatória: este texto é um rascunho gerado, não uma resposta confirmada nem uma instrução operacional validada."));
  } else if (result.status === "model_refusal_requires_review") {
    panel.append(element("p", "agent-review-warning", "Revisão humana obrigatória: esta recusa foi gerada pelo modelo. Confira a pergunta e as evidências antes de interpretá-la como conclusão."));
  } else if (result.status === "guarded_refusal") {
    panel.append(element("p", "agent-review-warning", "A validação bloqueou a resposta. Consulte os registros abaixo antes de uma nova pergunta."));
  }
  panel.append(element("p", "agent-answer-text", typeof result.answer === "string" ? result.answer : "Resposta não informada pela API."));

  const cited = element("div", "agent-citations");
  cited.append(element("h4", "", "IDs citados"));
  const sourceIds = Array.isArray(result.source_ids) ? result.source_ids : [];
  if (sourceIds.length) {
    const list = element("ul", "citation-list");
    for (const id of sourceIds) list.append(element("li", "", id));
    cited.append(list);
  } else {
    cited.append(element("p", "agent-none", "Nenhum ID citado na resposta."));
  }
  panel.append(cited);

  const evidence = Array.isArray(result.evidence) ? result.evidence : [];
  const evidenceSection = element("div", "agent-evidence");
  evidenceSection.append(element("h4", "", `Evidências consultadas · ${evidence.length}`));
  if (evidence.length) {
    const stack = element("div", "evidence-stack");
    for (const record of evidence) stack.append(evidenceCard(record));
    evidenceSection.append(stack);
  } else {
    evidenceSection.append(element("p", "agent-none", "A fonte respondeu, mas não retornou registros para esta consulta."));
  }
  panel.append(evidenceSection);
  container.replaceChildren(panel);
}

async function queryAgent() {
  const form = $("agent-form");
  const button = $("agent-submit");
  const container = $("agent-result");
  const source = $("agent-source").value;
  const request = {
    source,
    question: $("agent-question").value.trim(),
    model_mode: form.querySelector('input[name="model_mode"]:checked').value,
  };
  if (source !== "rain_history") request.source_point_id = $("agent-point-id").value.trim();
  button.disabled = true;
  container.setAttribute("aria-busy", "true");
  showAgentState("agent-loading", "↗", "Consultando a fonte e o modelo", "A geração local pode demorar, especialmente na primeira carga do adapter.");
  try {
    const result = await postJson("/v2/assistant/ask", request);
    renderAgentResult(result);
  } catch (error) {
    showAgentFailure(error);
  } finally {
    button.disabled = false;
    container.removeAttribute("aria-busy");
    container.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

$("data-form").addEventListener("submit", (event) => { event.preventDefault(); void queryData(); });
$("vision-form").addEventListener("submit", (event) => { event.preventDefault(); void queryVision(); });
$("rain-button").addEventListener("click", () => { void queryRain(); });
$("agent-source").addEventListener("change", updateAgentSource);
$("agent-form").addEventListener("submit", (event) => { event.preventDefault(); void queryAgent(); });
void loadSources();
