"""Testes do contrato que impedem uniões automáticas entre projetos."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from lora.contracts import Evidence, PointLink, PointRegistry


def test_unknown_points_stay_unmapped_even_when_names_look_related():
    registry = PointRegistry(version="v2-initial")
    assert registry.resolve("drenadata", "GARAGEM_A_RALO_01") is None
    assert registry.resolve("drenavision", "RALO-01") is None


def test_only_explicit_verified_link_can_resolve_point():
    link = PointLink(
        source_system="drenadata",
        source_point_id="GARAGEM_A_RALO_01",
        canonical_point_id="DH-POINT-001",
        verified_by="cadastro_fisico",
        verified_at=datetime(2026, 11, 19, tzinfo=timezone.utc),
    )
    registry = PointRegistry(version="v2-mapping-1", links=(link,))
    assert registry.resolve("drenadata", "GARAGEM_A_RALO_01") == "DH-POINT-001"
    assert registry.resolve("drenavision", "GARAGEM_A_RALO_01") is None
    with pytest.raises(ValidationError):
        PointRegistry(version="duplicate", links=(link, link))


def test_evidence_requires_timezones_and_keeps_namespaced_citation():
    data = dict(
        source_system="drenadata",
        kind="water_level",
        source_record_id="LE-1",
        source_point_id="GARAGEM_A_RALO_01",
        observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
        data_origin="synthetic",
        review_status="not_applicable",
        facts={"water_level_cm": 12.3},
    )
    evidence = Evidence(**data)
    assert evidence.citation_id == "drenadata:LE-1"
    assert evidence.canonical_point_id is None
    with pytest.raises(ValidationError):
        Evidence(**{**data, "observed_at": datetime(2026, 11, 18)})
