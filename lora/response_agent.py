"""Agente V2 de resposta com ferramentas de leitura e saída explicitamente revisável.

Falha da fonte e consulta vazia são resolvidas antes da LLM. Quando há evidência,
o modelo gera apenas um rascunho; validação estrutural não comprova cada frase.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import Evidence
from .inference_client import InferenceClient
from .training_data import SYSTEM_PROMPT
from .evaluate_lora import parse_response
from .train_lora import MODEL_ID, MODEL_REVISION


SourceChoice = Literal["drenadata_latest", "drenavision_events", "rain_history"]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=500)
    source: SourceChoice
    source_point_id: str | None = Field(default=None, max_length=80)
    model_mode: Literal["base", "adapted"] = "adapted"

    @model_validator(mode="after")
    def point_for_point_source(self) -> "AnswerRequest":
        if self.source != "rain_history" and not (self.source_point_id or "").strip():
            raise ValueError("source_point_id é obrigatório para esta fonte")
        if self.source == "rain_history" and self.source_point_id:
            raise ValueError("Chuva histórica da grade não usa ID de ralo")
        return self


class AnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["no_record", "draft_requires_review", "model_refusal_requires_review", "guarded_refusal"]
    answer: str
    refused: bool
    source_ids: list[str]
    evidence: list[Evidence]
    model_invoked: bool
    model_mode: Literal["base", "adapted"]
    raw_model_output: str | None = None
    validation_issues: list[str] = Field(default_factory=list)
    human_review_required: bool = True


def _context_evidence(evidence: Evidence) -> dict[str, object]:
    return {
        "citation_id": evidence.citation_id,
        "source_system": evidence.source_system,
        "source_point_id": evidence.source_point_id,
        "canonical_point_id": evidence.canonical_point_id,
        "observed_at": evidence.observed_at.isoformat(),
        "collected_at": evidence.collected_at.isoformat() if evidence.collected_at else None,
        "snapshot_at": evidence.snapshot_at.isoformat() if evidence.snapshot_at else None,
        "data_origin": evidence.data_origin,
        "review_status": evidence.review_status,
        "facts": evidence.facts,
        "source_uri": evidence.source_uri,
    }


def _plain(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(ch))


_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _dates_in_text(text: str) -> set[str]:
    """Reconhece datas ISO e brasileiras; valor impossível nunca vira evidência."""
    plain = _plain(text)
    dates = set(re.findall(r"(?<!\d)((?:19|20)\d{2}-\d{2}-\d{2})(?!\d)", plain))
    triples = [(int(year), int(month), int(day)) for day, month, year in
               re.findall(r"\b(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})\b", plain)]
    triples.extend((int(year), _MONTHS[month], int(day)) for day, month, year in
                   re.findall(r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+((?:19|20)\d{2})\b", plain))
    for year, month, day in triples:
        try:
            dates.add(datetime(year, month, day).date().isoformat())
        except ValueError:
            dates.add("invalid-requested-date")
    return dates


def _claim_issues(answer_text: str, evidence: list[Evidence]) -> list[str]:
    """Bloqueios conservadores; não substituem revisão factual por pessoa."""
    plain = _plain(answer_text)
    issues: list[str] = []
    if any(item.data_origin == "synthetic" for item in evidence):
        physical_claim = re.compile(r"\b(?:e|foi|trata-se de)\s+(?:uma\s+)?medicao fisica\b")
        for match in physical_claim.finditer(plain):
            prefix = plain[max(0, match.start() - 10):match.start()]
            if not re.search(r"\bnao\s+$", prefix):
                issues.append("synthetic_claimed_physical")
                break
    if any(item.source_system == "drenavision" and item.review_status == "pending" for item in evidence):
        if re.search(r"\b(?:obstrucao|alagamento|agua acumulada)\s+(?:esta\s+)?(?:confirmad|comprovad)", plain):
            issues.append("pending_vision_claimed_confirmed")
    if any(item.kind == "precipitation" for item in evidence):
        if re.search(r"\b(?:alagamento confirmado|risco comprovado|o ralo alagou)\b", plain):
            issues.append("rain_claimed_flood_confirmation")
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", answer_text))
    allowed_years = {
        str(moment.year)
        for item in evidence
        for moment in (item.observed_at, item.collected_at, item.snapshot_at)
        if moment is not None
    }
    if years - allowed_years:
        issues.append("unsupported_year")
    allowed_dates = {
        moment.date().isoformat()
        for item in evidence
        for moment in (item.observed_at, item.collected_at, item.snapshot_at)
        if moment is not None
    }
    if _dates_in_text(answer_text) - allowed_dates:
        issues.append("unsupported_date")
    observed_dates = {item.observed_at.date().isoformat() for item in evidence}
    for sentence in re.split(r"(?<!\d)\.(?!\d)|[!?;]", answer_text):
        plain_sentence = _plain(sentence)
        if (re.search(r"\b(?:leitura|medicao|observad|registrad|chuva|analise)\w*\b", plain_sentence)
                and not re.search(r"\b(?:coletad|snapshot|exportad)\w*\b", plain_sentence)
                and _dates_in_text(sentence) - observed_dates):
            issues.append("observation_date_mismatch")
            break
    allowed_by_unit = {
        "cm": {float(item.facts[key]) for item in evidence for key in ("water_level_cm", "alert_level_cm")
               if isinstance(item.facts.get(key), (int, float)) and not isinstance(item.facts[key], bool)},
        "mm": {float(item.facts["precipitation_mm"]) for item in evidence
               if isinstance(item.facts.get("precipitation_mm"), (int, float)) and not isinstance(item.facts["precipitation_mm"], bool)},
    }
    for raw, unit in re.findall(r"\b(\d+(?:[,.]\d+)?)\s*(cm|mm(?:/h)?)\b", plain):
        value = float(raw.replace(",", "."))
        group = "cm" if unit == "cm" else "mm"
        if not any(abs(value - known) < 0.011 for known in allowed_by_unit[group]):
            issues.append("unsupported_measurement")
            break
    return issues


def gather_evidence(request: AnswerRequest, data_source, vision_factory) -> list[Evidence]:
    """Seleciona ferramenta pela fonte pedida; nunca une IDs externos por nome."""
    if request.source == "drenadata_latest":
        item = data_source().latest_reading(request.source_point_id)
        return [item] if item is not None else []
    if request.source == "rain_history":
        rows = data_source().historical_precipitation()
        requested_dates = _dates_in_text(request.question)
        if requested_dates:
            return [item for item in rows if item.observed_at.date().isoformat() in requested_dates]
        return rows[-1:]
    with vision_factory() as vision:
        return vision.list_events(point_id=request.source_point_id, limit=5)


def answer(
    request: AnswerRequest,
    *,
    data_source,
    vision_factory,
    inference_factory=InferenceClient,
) -> AnswerResult:
    """Retorna rascunho auditável; nunca publica saída inválida como resposta."""
    evidence = gather_evidence(request, data_source, vision_factory)
    if not evidence:
        return AnswerResult(
            status="no_record",
            answer="Não consta nos dados disponíveis da fonte consultada.",
            refused=True,
            source_ids=[],
            evidence=[],
            model_invoked=False,
            model_mode=request.model_mode,
            validation_issues=[],
        )
    requested_dates = _dates_in_text(request.question)
    observed_dates = {item.observed_at.date().isoformat() for item in evidence}
    if requested_dates and not requested_dates.issubset(observed_dates):
        return AnswerResult(
            status="guarded_refusal",
            answer="A fonte consultada não trouxe evidência para a data solicitada.",
            refused=True, source_ids=[], evidence=evidence, model_invoked=False,
            model_mode=request.model_mode, validation_issues=["requested_time_not_in_evidence"],
        )
    if len(evidence) > 10:
        return AnswerResult(
            status="guarded_refusal",
            answer="A consulta retornou muitas observações para um resumo seguro. Delimite uma hora na API de histórico.",
            refused=True, source_ids=[], evidence=evidence[-10:], model_invoked=False,
            model_mode=request.model_mode, validation_issues=["interval_too_broad"],
        )
    if (re.search(r"\b(?:agora|hoje|atual|tempo real)\b", _plain(request.question))
            and datetime.now(timezone.utc) - max(item.observed_at for item in evidence) > timedelta(hours=2)):
        return AnswerResult(
            status="guarded_refusal",
            answer="O registro disponível não é uma medição atual; confira o horário da evidência.",
            refused=True, source_ids=[], evidence=evidence, model_invoked=False,
            model_mode=request.model_mode, validation_issues=["stale_observation"],
        )
    mapping_question = re.search(r"mesmo ponto|mesmo (?:ralo|ativo)|associe|associar|vincul|pertence (?:a|ao)|corresponde (?:a|ao)", _plain(request.question))
    canonical_ids = {item.canonical_point_id for item in evidence if item.canonical_point_id}
    question_plain = _plain(request.question)
    named_verified_point = any(re.search(r"(?<![a-z0-9_-])" + re.escape(_plain(point_id)) + r"(?![a-z0-9_-])", question_plain)
                               for point_id in canonical_ids)
    if mapping_question and (not canonical_ids or not named_verified_point):
        return AnswerResult(
            status="guarded_refusal",
            answer="Não há vínculo verificado para associar este ID externo a outro ponto.",
            refused=True,
            source_ids=[],
            evidence=evidence,
            model_invoked=False,
            model_mode=request.model_mode,
            validation_issues=["point_link_unverified"],
        )
    context = {"source_status": "available", "evidence": [_context_evidence(item) for item in evidence]}
    user_message = "CONTEXTO_JSON: " + json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\nPERGUNTA: " + request.question
    generated = inference_factory().generate(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message}],
        mode=request.model_mode,
        max_new_tokens=256,
        timeout_s=60,
    )
    parsed = parse_response(generated.raw_output)
    issues: list[str] = []
    if generated.mode != request.model_mode or generated.model_id != MODEL_ID or generated.model_revision != MODEL_REVISION:
        issues.append("runtime_model_mismatch")
    if request.model_mode == "adapted" and not generated.adapter_active:
        issues.append("adapter_not_active")
    if parsed is None:
        issues.append("schema_invalid")
    else:
        permitted_ids = {item.citation_id for item in evidence}
        if not set(parsed["source_ids"]).issubset(permitted_ids):
            issues.append("citation_not_in_evidence")
        origins = {item.data_origin for item in evidence}
        if len(origins) == 1 and parsed["data_origin"] not in origins:
            issues.append("data_origin_mismatch")
        if any(item.review_status == "pending" for item in evidence) and not parsed["review_required"]:
            issues.append("pending_vision_without_review")
        if any(item.kind == "water_level" and item.facts.get("in_attention") is True for item in evidence) and not parsed["review_required"]:
            issues.append("attention_without_review")
        if not parsed["source_ids"] and not parsed["refused"]:
            issues.append("answer_without_citation")
        if parsed["refused"] and not re.search(r"\b(?:nao posso|nao e possivel|nao consta|nao ha|nao foi possivel|nao permite|nao confirma|sem evidencia|exige revisao)\b", _plain(parsed["answer"])):
            issues.append("refusal_text_inconsistent")
        issues.extend(_claim_issues(parsed["answer"], evidence))
    if issues:
        return AnswerResult(
            status="guarded_refusal",
            answer="A resposta gerada não passou na validação. Consulte as evidências e solicite revisão humana.",
            refused=True,
            source_ids=[],
            evidence=evidence,
            model_invoked=True,
            model_mode=request.model_mode,
            raw_model_output=generated.raw_output,
            validation_issues=issues,
        )
    return AnswerResult(
        status="model_refusal_requires_review" if parsed["refused"] else "draft_requires_review",
        answer=parsed["answer"],
        refused=parsed["refused"],
        source_ids=parsed["source_ids"],
        evidence=evidence,
        model_invoked=True,
        model_mode=request.model_mode,
        raw_model_output=generated.raw_output,
        validation_issues=[],
    )
