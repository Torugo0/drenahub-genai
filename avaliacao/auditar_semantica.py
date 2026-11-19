"""Independent audit of frozen answers; does not alter the original scoreboard.

This script counts refusals and citation conditions without calling an LLM or
equating a missing citation with a false factual statement. It detects one
narrow, checkable class of contradiction: a claim that there are no pending
maintenance events when the versioned operational data contain such events.
Other free-form claims still need human review.
"""

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "avaliacao" / "casos.json"
RAW = ROOT / "avaliacao" / "resultados" / "respostas_brutas.jsonl"
SCORES = ROOT / "avaliacao" / "resultados" / "pontuacao_individual.json"
OPERATIONAL = ROOT / "base" / "operational.json"
OUTPUT = ROOT / "avaliacao" / "resultados" / "auditoria_semantica.json"
REFUSAL = "Não consta nos dados disponíveis."
CONFIGURATIONS = ("baseline", "rag", "agent")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def audit() -> dict:
    cases = {item["id"]: item for item in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}
    raw = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]
    scores = {
        (item["case_id"], item["configuration"]): item
        for item in json.loads(SCORES.read_text(encoding="utf-8"))
    }
    operational = json.loads(OPERATIONAL.read_text(encoding="utf-8"))
    pending = sorted(item["id"] for item in operational["events"] if item["status"] == "aguardando_manutencao")

    keys = [(item["case_id"], item["configuration"]) for item in raw]
    if len(keys) != len(set(keys)) or set(keys) != set(scores):
        raise ValueError("Frozen raw answers and scores do not contain the same unique case/configuration pairs")
    if set(keys) != {(case_id, configuration) for case_id in cases for configuration in CONFIGURATIONS}:
        raise ValueError("Expected one answer per case and configuration")

    groups = defaultdict(list)
    contradictions = []
    for item in raw:
        case_id, configuration = item["case_id"], item["configuration"]
        case, response = cases[case_id], item["response"]
        score = scores[(case_id, configuration)]
        refused = bool(response["refused"])
        answer = str(response["answer"])
        source_ids = [source["source_id"] for source in response["sources"]]
        groups[configuration].append((case, response, score))

        # This rule uses the versioned operational ground truth, independent of
        # whether the model was allowed to see it. It is deliberately narrow.
        no_pending_claim = re.search(
            r"\bnao ha ocorrencias? aguardando manutencao\b|\bnenhuma ocorrencia aguarda manutencao\b",
            _plain(answer),
        )
        if pending and not refused and no_pending_claim:
            contradictions.append({
                "case_id": case_id,
                "configuration": configuration,
                "claim": no_pending_claim.group(0),
                "contradicting_record_ids": pending,
                "official_correct": bool(score["correct"]),
                "official_unsupported_claim_detected": bool(score["unsupported_claim_detected"]),
                "response_source_ids": source_ids,
            })

    summary = {}
    for configuration in CONFIGURATIONS:
        rows = groups[configuration]
        answerable = [(case, response, score) for case, response, score in rows if not case["refuse"]]
        no_answer = [(case, response, score) for case, response, score in rows if case["refuse"]]
        substantive = [(case, response, score) for case, response, score in rows if not response["refused"]]
        summary[configuration] = {
            "total_cases": len(rows),
            "answerable_cases": len(answerable),
            "expected_refusal_cases": len(no_answer),
            "correct_refusals": sum(bool(response["refused"]) and response["answer"] == REFUSAL for _, response, _ in no_answer),
            "excess_refusals_on_answerable_cases": sum(bool(response["refused"]) for _, response, _ in answerable),
            "substantive_answers": len(substantive),
            "substantive_answers_without_citation": sum(not response["sources"] for _, response, _ in substantive),
            "official_correct": sum(bool(score["correct"]) for _, _, score in rows),
            "official_correct_on_answerable_cases": sum(bool(score["correct"]) for _, _, score in answerable),
            "official_valid_citation": sum(bool(score["citation_valid"]) for _, _, score in rows),
            "official_valid_citation_on_substantive_answers": sum(bool(score["citation_valid"]) for _, _, score in substantive),
            "official_unsupported_claim_detected": sum(bool(score["unsupported_claim_detected"]) for _, _, score in rows),
            "unsupported_flag_from_uncited_substantive_answer": sum(
                bool(score["unsupported_claim_detected"]) and not response["sources"]
                and not score["forbidden_claims_found"] and not score["invalid_source_ids"]
                and not score["unconsulted_source_ids"]
                for _, response, score in substantive
            ),
            "unsupported_flag_with_id_outside_case_whitelist": sum(bool(score["invalid_source_ids"]) for _, _, score in rows),
            "forbidden_claim_matches": sum(bool(score["forbidden_claims_found"]) for _, _, score in rows),
            "by_split": {
                split: {
                    "cases": sum(case["split"] == split for case, _, _ in rows),
                    "official_correct": sum(bool(score["correct"]) for case, _, score in rows if case["split"] == split),
                    "answerable_cases": sum(case["split"] == split and not case["refuse"] for case, _, _ in rows),
                    "official_correct_on_answerable_cases": sum(
                        bool(score["correct"]) for case, _, score in rows if case["split"] == split and not case["refuse"]
                    ),
                }
                for split in ("dev", "final")
            },
        }

    return {
        "scope": "Frozen 40 cases x 3 configurations; quantitative rule audit plus narrow deterministic contradiction check",
        "input_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): _hash(path) for path in (CASES, RAW, SCORES, OPERATIONAL)},
        "summary": summary,
        "deterministic_contradictions": contradictions,
        "limitation": "Missing/invalid citations, omissions and excessive refusals are separate from semantic hallucinations; unflagged free-form claims are not proven true.",
    }


if __name__ == "__main__":
    result = audit()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
