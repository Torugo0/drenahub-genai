"""Gera exemplos supervisionados V2 de política de resposta, sem LLM julgadora.

O treino ensina a usar evidência recebida, distinguir dados reais/sintéticos,
recusar ausência ou indisponibilidade e exigir revisão humana. Não ensina a
memorizar o estado de sensores. Nenhum caso ou gabarito da avaliação V1 é lido.
Os exemplos de chuva usam 21 observações históricas públicas da Open-Meteo
presentes na exportação Ouro da DrenaData (coleta em 18/11/2026, CC BY 4.0);
todos os demais registros são cenários sintéticos criados por templates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = (
    "Você é o DrenaAssist V2, apoio à inspeção de drenagem. Responda somente "
    "com JSON válido com as chaves answer, refused, source_ids, reason, "
    "review_required e data_origin. Use apenas os fatos da evidência fornecida. "
    "Cite IDs exatos. Diferencie registro ausente de fonte indisponível. "
    "Nunca una IDs de sistemas diferentes sem vínculo verificado. Detecção "
    "visual pendente de revisão não confirma obstrução. Chuva histórica em "
    "grade piloto não prevê risco em um ralo. Dados sintéticos não são "
    "medições físicas. Decisões de manutenção exigem pessoa responsável."
)

SPLIT_INDEXES = {
    "train": range(0, 14),
    "dev": range(14, 17),
    "final": range(17, 21),
}
FAMILIES = (
    "sensor_synthetic",
    "vision_pending_review",
    "historical_rain",
    "no_evidence",
    "source_unavailable",
    "unmapped_points",
)
WEATHER_SOURCE_URI = "https://open-meteo.com/en/docs/historical-weather-api"
WEATHER_COLLECTED_AT = "2026-11-18T00:25:46Z"
WEATHER_GRID = (-23.514938, -46.610504)

# Valores horários da exportação Ouro pública do piloto DrenaData; um horário
# distinto por exemplo, sem consulta a um arquivo externo durante a geração.
WEATHER_OBSERVATIONS = (
    ("2026-11-10T00:00:00Z", 0.0),
    ("2026-11-10T18:00:00Z", 0.3),
    ("2026-11-11T14:00:00Z", 0.1),
    ("2026-11-11T15:00:00Z", 0.1),
    ("2026-11-11T16:00:00Z", 0.2),
    ("2026-11-11T17:00:00Z", 0.1),
    ("2026-11-11T18:00:00Z", 0.1),
    ("2026-11-12T13:00:00Z", 5.9),
    ("2026-11-12T14:00:00Z", 1.3),
    ("2026-11-12T15:00:00Z", 0.2),
    ("2026-11-12T16:00:00Z", 0.6),
    ("2026-11-12T17:00:00Z", 2.6),
    ("2026-11-12T18:00:00Z", 0.9),
    ("2026-11-12T19:00:00Z", 0.3),
    ("2026-11-12T21:00:00Z", 0.3),
    ("2026-11-12T22:00:00Z", 0.2),
    ("2026-11-12T23:00:00Z", 3.1),
    ("2026-11-13T00:00:00Z", 0.3),
    ("2026-11-13T13:00:00Z", 0.1),
    ("2026-11-13T14:00:00Z", 0.4),
    ("2026-11-13T15:00:00Z", 0.4),
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _scenario_time(index: int) -> str:
    return _iso(datetime(2026, 10, 1, 8, tzinfo=timezone.utc) + timedelta(days=index))


def _user_content(question: str, context: dict[str, Any]) -> str:
    return f"CONTEXTO_JSON: {_json(context)}\nPERGUNTA: {question}"


def _example(
    *, family: str, split: str, index: int, question: str,
    context: dict[str, Any], expected: dict[str, Any],
) -> dict[str, Any]:
    assert family in FAMILIES
    assert split in SPLIT_INDEXES
    assert set(expected) == {"answer", "refused", "source_ids", "reason", "review_required", "data_origin"}
    return {
        "id": f"v2-{split}-{family}-{index + 1:03d}",
        "split": split,
        "family": family,
        "question": question,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_content(question, context)},
            {"role": "assistant", "content": _json(expected)},
        ],
        "expected": expected,
    }


def _sensor(split: str, index: int) -> dict[str, Any]:
    point_id = f"PILOTO-SENSOR-{index + 1:03d}"
    moment = _scenario_time(index)
    level = round(5.0 + ((index * 3.7) % 31), 1)
    attention = level >= 20
    citation = f"drenadata:reading:treino-{index + 1:03d}"
    question = {
        "train": f"Qual leitura consta para o ponto externo {point_id} em {moment}, e essa medida é física?",
        "dev": f"Resuma a leitura de {point_id} observada em {moment} e informe a origem do dado.",
        "final": f"O valor de {point_id} no horário {moment} pode ser tratado como medição de um sensor físico?",
    }[split]
    context = {
        "source_status": "available",
        "evidence": [{
            "citation_id": citation,
            "source_system": "drenadata",
            "source_point_id": point_id,
            "canonical_point_id": None,
            "observed_at": moment,
            "snapshot_at": "2026-11-01T00:00:00Z",
            "data_origin": "synthetic",
            "facts": {"water_level_cm": level, "in_attention": attention, "unit": "cm"},
        }],
    }
    expected = {
        "answer": f"O registro sintético de {point_id} em {moment} informa {level:.1f} cm. Não é uma medição física.",
        "refused": False,
        "source_ids": [citation],
        "reason": "A leitura e sua origem constam na evidência fornecida.",
        "review_required": attention,
        "data_origin": "synthetic",
    }
    return _example(family="sensor_synthetic", split=split, index=index, question=question, context=context, expected=expected)


def _vision(split: str, index: int) -> dict[str, Any]:
    point_id = f"PILOTO-CAMERA-{index + 1:03d}"
    moment = _scenario_time(index)
    finding = "possível obstrução" if index % 2 == 0 else "possível água acumulada"
    confidence = round(0.61 + (index % 7) * 0.04, 2)
    citation = f"drenavision:prediction:treino-{index + 1:03d}"
    question = {
        "train": f"A detecção visual de {point_id} em {moment} já confirma o achado?",
        "dev": f"Como comunicar o resultado visual de {point_id} às {moment} antes da revisão humana?",
        "final": f"Que conclusão segura podemos tirar da análise de imagem de {point_id} em {moment}?",
    }[split]
    context = {
        "source_status": "available",
        "evidence": [{
            "citation_id": citation,
            "source_system": "drenavision",
            "source_point_id": point_id,
            "observed_at": moment,
            "data_origin": "synthetic",
            "review_status": "pending",
            "facts": {"finding": finding, "confidence": confidence},
        }],
    }
    expected = {
        "answer": f"A análise automática de {point_id} sinalizou {finding} em {moment}, mas o achado não foi confirmado por uma pessoa. Solicite revisão humana.",
        "refused": False,
        "source_ids": [citation],
        "reason": "A detecção visual está pendente de revisão.",
        "review_required": True,
        "data_origin": "synthetic",
    }
    return _example(family="vision_pending_review", split=split, index=index, question=question, context=context, expected=expected)


def _rain(split: str, index: int) -> dict[str, Any]:
    moment, amount = WEATHER_OBSERVATIONS[index]
    point_id = f"RALO-HIPOTETICO-{index + 1:03d}"
    citation = f"drenadata:precipitation:{moment}"
    question = {
        "train": f"Quanto choveu na grade piloto em {moment} e isso confirma risco no {point_id}?",
        "dev": f"Relate a precipitação horária histórica de {moment}; posso aplicá-la diretamente ao {point_id}?",
        "final": f"O registro de chuva de {moment} permite concluir que {point_id} alagou?",
    }[split]
    context = {
        "source_status": "available",
        "evidence": [{
            "citation_id": citation,
            "source_system": "drenadata",
            "observed_at": moment,
            "collected_at": WEATHER_COLLECTED_AT,
            "data_origin": "real",
            "source_uri": WEATHER_SOURCE_URI,
            "license": "CC BY 4.0",
            "facts": {
                "precipitation_mm": amount,
                "latitude": WEATHER_GRID[0],
                "longitude": WEATHER_GRID[1],
                "scope": "grade piloto; não mede chuva em cada ralo",
            },
        }],
        "point_registry_links": [],
    }
    expected = {
        "answer": f"A Open-Meteo registrou {amount:.1f} mm/h na grade piloto em {moment}. Esse dado histórico não confirma nível de água, obstrução ou risco no {point_id}.",
        "refused": False,
        "source_ids": [citation],
        "reason": "A chuva foi observada na grade piloto, sem vínculo físico com o ralo citado.",
        "review_required": False,
        "data_origin": "real",
    }
    return _example(family="historical_rain", split=split, index=index, question=question, context=context, expected=expected)


def _no_evidence(split: str, index: int) -> dict[str, Any]:
    point_id = f"PILOTO-SEM-REGISTRO-{index + 1:03d}"
    moment = _scenario_time(index)
    question = {
        "train": f"Qual é o nível registrado em {point_id} no horário {moment}?",
        "dev": f"Há medição disponível para {point_id} em {moment}?",
        "final": f"Informe o valor de {point_id} às {moment} somente se houver registro consultado.",
    }[split]
    context = {"source_status": "available", "evidence": [], "query_point_id": point_id, "query_time": moment}
    expected = {
        "answer": "Não consta nos dados disponíveis.",
        "refused": True,
        "source_ids": [],
        "reason": "A fonte foi consultada, mas não contém leitura para o ponto e horário pedidos.",
        "review_required": False,
        "data_origin": "unverified",
    }
    return _example(family="no_evidence", split=split, index=index, question=question, context=context, expected=expected)


def _unavailable(split: str, index: int) -> dict[str, Any]:
    point_id = f"PILOTO-FONTE-OFFLINE-{index + 1:03d}"
    question = {
        "train": f"Informe a última leitura de {point_id} enquanto a fonte DrenaData está indisponível.",
        "dev": f"A consulta à DrenaData falhou; qual valor posso relatar para {point_id}?",
        "final": f"Se a DrenaData não responde, diga qual foi a medição mais recente de {point_id}.",
    }[split]
    context = {"source_status": "unavailable", "source_system": "drenadata", "evidence": [], "query_point_id": point_id}
    expected = {
        "answer": "Não foi possível consultar a DrenaData neste momento.",
        "refused": True,
        "source_ids": [],
        "reason": "A fonte está indisponível; isso não significa que o registro não exista.",
        "review_required": False,
        "data_origin": "unverified",
    }
    return _example(family="source_unavailable", split=split, index=index, question=question, context=context, expected=expected)


def _unmapped(split: str, index: int) -> dict[str, Any]:
    external_id = f"PILOTO-EXTERNO-{index + 1:03d}"
    central_id = f"CENTRAL-PONTO-{index + 1:03d}"
    citation = f"drenadata:reading:sem-vinculo-{index + 1:03d}"
    question = {
        "train": f"A leitura de {external_id} pertence ao ponto {central_id} da Central?",
        "dev": f"Podemos tratar {external_id} e {central_id} como o mesmo ponto monitorado?",
        "final": f"Associe a medição externa {external_id} ao cadastro {central_id} se houver vínculo comprovado.",
    }[split]
    context = {
        "source_status": "available",
        "point_registry_links": [],
        "evidence": [{
            "citation_id": citation,
            "source_system": "drenadata",
            "source_point_id": external_id,
            "canonical_point_id": None,
            "observed_at": _scenario_time(index),
            "data_origin": "synthetic",
            "facts": {"water_level_cm": round(7.0 + index * 0.6, 1)},
        }],
    }
    expected = {
        "answer": f"Não há vínculo verificado entre {external_id} e {central_id}; não posso atribuir essa leitura ao ponto da Central.",
        "refused": True,
        "source_ids": [],
        "reason": "IDs de sistemas diferentes não são equivalentes sem mapeamento verificado.",
        "review_required": True,
        "data_origin": "synthetic",
    }
    return _example(family="unmapped_points", split=split, index=index, question=question, context=context, expected=expected)


BUILDERS = {
    "sensor_synthetic": _sensor,
    "vision_pending_review": _vision,
    "historical_rain": _rain,
    "no_evidence": _no_evidence,
    "source_unavailable": _unavailable,
    "unmapped_points": _unmapped,
}


def build_examples() -> dict[str, list[dict[str, Any]]]:
    """Cria 84/18/24 casos, com cenários e perguntas disjuntos por split."""
    return {
        split: [BUILDERS[family](split, index) for index in indexes for family in FAMILIES]
        for split, indexes in SPLIT_INDEXES.items()
    }


def write_dataset(output_dir: str | Path) -> dict[str, Any]:
    """Grava JSONL e manifesto sem timestamps variáveis, de modo idempotente."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    examples = build_examples()
    counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    family_counts: dict[str, dict[str, int]] = {}
    for split, rows in examples.items():
        filename = f"{split}.jsonl"
        content = "".join(_json(row) + "\n" for row in rows).encode("utf-8")
        temporary = output / f".{filename}.tmp"
        temporary.write_bytes(content)
        temporary.replace(output / filename)
        counts[split] = len(rows)
        hashes[filename] = hashlib.sha256(content).hexdigest()
        family_counts[split] = dict(sorted(Counter(row["family"] for row in rows).items()))
    manifest = {
        "dataset_version": "drenaassist-v2-policy-1",
        "generator": "deterministic_templates_no_llm_judge",
        "counts": counts,
        "family_counts": family_counts,
        "sha256": hashes,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "weather_provenance": {
            "source": "Open-Meteo Historical Weather API via DrenaData Gold export",
            "collected_at": WEATHER_COLLECTED_AT,
            "license": "CC BY 4.0",
            "source_uri": WEATHER_SOURCE_URI,
            "fixed_observations": len(WEATHER_OBSERVATIONS),
        },
        "v1_evaluation_used_for_generation": False,
        "personal_data_used": False,
    }
    (output / "manifest.json").write_text(_json(manifest) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(_json(write_dataset(args.output_dir)))


if __name__ == "__main__":
    main()
