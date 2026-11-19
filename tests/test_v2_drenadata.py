"""Contrato da exportação Ouro da DrenaData usando somente fixture temporária."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from lora.contracts import PointLink, PointRegistry, SourceUnavailable
from lora.drenadata import load_gold_export


@pytest.fixture
def gold_dir(tmp_path):
    (tmp_path / "dim_local.csv").write_text(
        "local_id,ponto_id,nome_local,is_synthetic\n"
        "GARAGEM_A_RALO_01,GARAGEM_A_RALO_01,Garagem A,true\n",
        encoding="utf-8",
    )
    (tmp_path / "dim_tempo.csv").write_text(
        "tempo_id,data_hora,data,hora,hora_inicio\n"
        "2026-11-10 00:00:00,2026-11-10T00:00:00Z,2026-11-10,0,2026-11-10T00:00:00Z\n"
        "2026-11-10 01:00:00,2026-11-10T01:00:00Z,2026-11-10,1,2026-11-10T01:00:00Z\n",
        encoding="utf-8",
    )
    (tmp_path / "fato_monitoramento.csv").write_text(
        "leitura_id,local_id,tempo_id,nivel_agua_cm,em_atencao,sensor_status,is_synthetic,responsavel_hash,collected_at\n"
        "r1,GARAGEM_A_RALO_01,2026-11-10 00:00:00,8.5,false,ok,true,segredo-que-nao-deve-sair,2026-11-18T00:25:45Z\n"
        "r2,GARAGEM_A_RALO_01,2026-11-10 01:00:00,22.0,true,ok,true,outro-hash,2026-11-18T00:25:45Z\n",
        encoding="utf-8",
    )
    (tmp_path / "precipitacao_horaria.csv").write_text(
        "data_hora,latitude,longitude,precipitacao_mm,source,collected_at\n"
        "2026-11-10T00:00:00Z,-23.514938,-46.610504,0.0,open-meteo-archive,2026-11-18T00:25:46Z\n"
        "2026-11-10T01:00:00Z,-23.514938,-46.610504,1.2,open-meteo-archive,2026-11-18T00:25:46Z\n",
        encoding="utf-8",
    )
    metadata = {
        "exported_at_utc": "2026-11-18T00:45:30Z",
        "timezone": "UTC",
        "source": "Databricks Delta Gold",
        "files": {
            "dim_local.csv": 1,
            "dim_tempo.csv": 2,
            "fato_monitoramento.csv": 2,
            "precipitacao_horaria.csv": 2,
        },
    }
    (tmp_path / "export_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return tmp_path


def test_gold_export_returns_traceable_evidence_without_hash_or_automatic_link(gold_dir):
    source = load_gold_export(gold_dir)
    latest = source.latest_reading("GARAGEM_A_RALO_01")
    assert latest is not None
    assert latest.citation_id == "drenadata:reading:r2"
    assert latest.canonical_point_id is None
    assert latest.source_point_id == "GARAGEM_A_RALO_01"
    assert latest.data_origin == "synthetic"
    assert latest.kind == "water_level"
    assert latest.facts["water_level_cm"] == 22.0
    assert latest.facts["in_attention"] is True
    assert latest.snapshot_at == datetime(2026, 11, 18, 0, 45, 30, tzinfo=timezone.utc)
    assert "responsavel_hash" not in latest.model_dump_json()
    assert "segredo-que-nao-deve-sair" not in latest.model_dump_json()

    readings = source.reading_series(
        "GARAGEM_A_RALO_01",
        start=datetime(2026, 11, 10, 1, tzinfo=timezone.utc),
    )
    assert [item.source_record_id for item in readings] == ["reading:r2"]
    assert source.latest_reading("RALO-01") is None  # nome parecido não é vínculo

    rain = source.historical_precipitation()
    assert [item.facts["precipitation_mm"] for item in rain] == [0.0, 1.2]
    assert all(item.data_origin == "real" and item.source_point_id is None for item in rain)
    assert rain[1].citation_id == "drenadata:precipitation:2026-11-10T01:00:00Z"
    assert "não mede chuva em cada ralo" in rain[1].facts["scope"]


def test_only_verified_registry_links_to_canonical_point(gold_dir):
    registry = PointRegistry(
        version="verified-1",
        links=(PointLink(
            source_system="drenadata",
            source_point_id="GARAGEM_A_RALO_01",
            canonical_point_id="POINT-001",
            verified_by="responsavel-teste",
            verified_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
        ),),
    )
    source = load_gold_export(gold_dir, registry)
    assert source.latest_reading("GARAGEM_A_RALO_01").canonical_point_id == "POINT-001"
    with pytest.raises(ValueError, match="fuso horário"):
        source.historical_precipitation(start=datetime(2026, 11, 10))


@pytest.mark.parametrize("failure", ["missing", "count", "duplicate", "wrong_utc", "foreign_key", "not_synthetic"])
def test_corrupted_export_raises_instead_of_returning_empty(gold_dir, failure):
    fact_path = gold_dir / "fato_monitoramento.csv"
    metadata_path = gold_dir / "export_metadata.json"
    if failure == "missing":
        (gold_dir / "precipitacao_horaria.csv").unlink()
    elif failure == "count":
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["files"]["fato_monitoramento.csv"] = 3
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    elif failure == "duplicate":
        fact_path.write_text(fact_path.read_text(encoding="utf-8").replace("r2,", "r1,"), encoding="utf-8")
    elif failure == "wrong_utc":
        rain_path = gold_dir / "precipitacao_horaria.csv"
        rain_path.write_text(rain_path.read_text(encoding="utf-8").replace("2026-11-10T01:00:00Z", "2026-11-10T01:00:00-03:00"), encoding="utf-8")
    elif failure == "foreign_key":
        fact_path.write_text(fact_path.read_text(encoding="utf-8").replace("GARAGEM_A_RALO_01,2026-11-10 01:00:00", "OUTRO_PONTO,2026-11-10 01:00:00"), encoding="utf-8")
    elif failure == "not_synthetic":
        fact_path.write_text(fact_path.read_text(encoding="utf-8").replace("22.0,true,ok,true,", "22.0,true,ok,false,"), encoding="utf-8")
    with pytest.raises(SourceUnavailable):
        load_gold_export(gold_dir)


def test_valid_empty_sources_remain_distinct_from_import_failure(gold_dir):
    for filename in ("fato_monitoramento.csv", "precipitacao_horaria.csv"):
        path = gold_dir / filename
        path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    metadata_path = gold_dir / "export_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["files"]["fato_monitoramento.csv"] = 0
    metadata["files"]["precipitacao_horaria.csv"] = 0
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    source = load_gold_export(gold_dir)
    assert source.latest_reading("GARAGEM_A_RALO_01") is None
    assert source.reading_series("GARAGEM_A_RALO_01") == []
    assert source.historical_precipitation() == []
