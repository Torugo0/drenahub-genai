"""Metrics with independently authored gold answers.

The checks here deliberately do not ask the evaluated LLM to judge itself.
Required facts are short regular expressions reviewed against source documents
or synthetic operational records. They are evidence of covered facts, not a
complete semantic or safety assessment; borderline cases need human review.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any


REFUSAL = "Não consta nos dados disponíveis."


def _plain(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))


def retrieval_recall(retrieved_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """|G intersect top-k| / |G|. Call only for nonempty G."""
    if not gold_ids:
        raise ValueError("recall requires at least one gold chunk")
    return len(set(gold_ids) & set(retrieved_ids[:k])) / len(set(gold_ids))


def _source_ids(response: Mapping[str, Any]) -> list[str]:
    result = []
    for source in response.get("sources") or []:
        if isinstance(source, Mapping):
            result.append(str(source.get("source_id", "")))
        elif isinstance(source, str):
            result.append(source)
    draft = response.get("draft_work_order")
    if isinstance(draft, Mapping):
        result.extend(str(item) for item in draft.get("source_ids", []))
    return list(dict.fromkeys(result))


def _tool_names(response: Mapping[str, Any]) -> list[str]:
    metadata = response.get("metadata") or {}
    entries = metadata.get("tools_called") or metadata.get("tool_trace") or []
    result = []
    for entry in entries:
        result.append(entry if isinstance(entry, str) else str(entry.get("tool", entry.get("name", ""))))
    return result


def score_answer(case: Mapping[str, Any], response: Mapping[str, Any], configuration: str) -> dict[str, Any]:
    """Apply a fixed gold case to one returned answer.

    `correct` covers observable answer facts/refusal. Citation and tool scores
    are separate so an accurate sentence with a fabricated source is visible.
    `unsupported_claim_detected` catches auditable known failures; it is a
    lower bound rather than a proof that all other claims are supported.
    """
    answer = str(response.get("answer") or "")
    scored_text = _plain(answer + " " + json.dumps(response.get("draft_work_order"), ensure_ascii=False))
    refused = bool(response.get("refused"))
    expected_refusal = bool(case["refuse"])
    required = case.get("required_facts") or []
    forbidden = case.get("forbidden_claims") or []
    missed = [pattern for pattern in required if not re.search(pattern, scored_text, re.IGNORECASE | re.UNICODE)]
    forbidden_found = [pattern for pattern in forbidden if re.search(pattern, scored_text, re.IGNORECASE | re.UNICODE)]
    refusal_correct = expected_refusal and refused and REFUSAL.casefold() in answer.casefold()
    correct = refusal_correct if expected_refusal else (not refused and not missed)
    if case.get("expect_draft"):
        correct = correct and bool(response.get("draft_work_order"))

    cited = _source_ids(response)
    gold_sources = set(case.get("supporting_sources") or [])
    bad_sources = [source for source in cited if source not in gold_sources]
    metadata = response.get("metadata") or {}
    consultation_known = "retrieval" in metadata or "tool_trace" in metadata
    consulted = {str(item.get("chunk_id")) for item in metadata.get("retrieval", [])}
    for entry in metadata.get("tool_trace", []):
        consulted.update(str(item) for item in entry.get("result_ids", []))
    unconsulted = [source for source in cited if consultation_known and source not in consulted]
    missed_source_groups = [group for group in case.get("required_source_groups", [])
                            if not set(group) & set(cited)]
    citation_valid = not cited if refused else bool(cited) and not bad_sources and not unconsulted and not missed_source_groups
    if configuration == "baseline" and not cited:
        citation_valid = bool(refused)

    tools = _tool_names(response)
    required_tools = set(case.get("required_tools") or [])
    allowed_tools = set(case.get("allowed_tools") or required_tools)
    if allowed_tools:
        allowed_tools.update({"get_points", "get_maintenance_queue"})
    missed_tool_groups = [group for group in case.get("required_tool_groups", [])
                          if not set(group) & set(tools)]
    tool_use_correct: bool | None = None
    if configuration == "agent":
        tool_use_correct = required_tools <= set(tools) and set(tools) <= allowed_tools and not missed_tool_groups

    raw = (response.get("metadata") or {}).get("raw_model_output")
    raw_json_valid: bool | None = None
    if raw is not None:
        try:
            json.loads(raw if isinstance(raw, str) else json.dumps(raw))
            raw_json_valid = True
        except (TypeError, ValueError):
            raw_json_valid = False
    try:
        json.dumps(response, ensure_ascii=False)
        json_valid = True
    except (TypeError, ValueError):
        json_valid = False

    unsupported = bool(forbidden_found or bad_sources or unconsulted)
    if not refused and not citation_valid:
        unsupported = True
    if expected_refusal and not refused:
        unsupported = True

    return {
        "case_id": case["id"],
        "configuration": configuration,
        "correct": correct,
        "refusal_correct": refusal_correct,
        "expected_refusal": expected_refusal,
        "json_valid": json_valid,
        "raw_json_valid": raw_json_valid,
        "citation_valid": citation_valid,
        "unsupported_claim_detected": unsupported,
        "tool_use_correct": tool_use_correct,
        "required_facts_missed": missed,
        "forbidden_claims_found": forbidden_found,
        "invalid_source_ids": bad_sources,
        "unconsulted_source_ids": unconsulted,
        "missing_source_groups": missed_source_groups,
        "cited_source_ids": cited,
        "tools_called": tools,
        "missing_tool_groups": missed_tool_groups,
        "needs_human_review": bool(case.get("needs_human_review", False)),
        "latency_ms": (response.get("metadata") or {}).get("latency_ms"),
    }


def aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("No rows to aggregate")
    def rate(field: str, selected: Sequence[Mapping[str, Any]] | None = None) -> float | None:
        values = [bool(row[field]) for row in (selected if selected is not None else rows) if row.get(field) is not None]
        return round(100 * mean(values), 2) if values else None

    refusals = [row for row in rows if row["expected_refusal"]]
    tool_rows = [row for row in rows if row.get("tool_use_correct") is not None]
    latency = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
    return {
        "n": len(rows),
        "correct_pct": rate("correct"),
        "unsupported_claim_detected_pct": rate("unsupported_claim_detected"),
        "correct_refusal_pct": rate("refusal_correct", refusals),
        "json_valid_pct": rate("json_valid"),
        "raw_json_valid_pct": rate("raw_json_valid"),
        "valid_citation_pct": rate("citation_valid"),
        "correct_tool_use_pct": rate("tool_use_correct", tool_rows),
        "mean_latency_ms": round(mean(latency), 2) if latency else None,
    }
