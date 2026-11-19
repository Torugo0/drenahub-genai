"""Adaptador somente leitura para uma exportação Ouro da DrenaData.

O contrato da exportação é validado antes de qualquer consulta. Um arquivo
ausente/corrompido gera ``SourceUnavailable``; uma consulta legítima sem linhas
retorna ``None`` ou lista vazia. IDs da DrenaData só ganham ponto canônico via
``PointRegistry`` com vínculo verificado explicitamente.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import Evidence, PointRegistry, SourceUnavailable


REQUIRED_FILES = (
    "fato_monitoramento.csv",
    "dim_local.csv",
    "dim_tempo.csv",
    "precipitacao_horaria.csv",
)
WEATHER_SOURCE_URI = "https://open-meteo.com/en/docs/historical-weather-api"


@dataclass(frozen=True)
class _Reading:
    record_id: str
    point_id: str
    observed_at: datetime
    collected_at: datetime
    water_level_cm: float
    in_attention: bool
    sensor_status: str


@dataclass(frozen=True)
class _Precipitation:
    observed_at: datetime
    collected_at: datetime
    precipitation_mm: float
    latitude: float
    longitude: float


def _require_text(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceUnavailable(f"DrenaData: {field} ausente ou vazio")
    return value.strip()


def _utc_time(value: str | None, field: str, *, allow_naive: bool = False) -> datetime:
    raw = _require_text(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceUnavailable(f"DrenaData: {field} não é data/hora válida") from exc
    if parsed.tzinfo is None:
        if not allow_naive:
            raise SourceUnavailable(f"DrenaData: {field} não informa UTC")
        # Databricks exporta tempo_id como ``YYYY-MM-DD HH:MM:SS``. O metadado
        # da Ouro declara timezone=UTC; somente esse campo legado admite a
        # forma sem offset e é interpretado explicitamente como UTC.
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed.utcoffset() != timedelta(0):
        raise SourceUnavailable(f"DrenaData: {field} precisa estar em UTC")
    return parsed.astimezone(timezone.utc)


def _number(value: str | None, field: str, *, minimum: float, maximum: float | None = None) -> float:
    raw = _require_text(value, field)
    try:
        number = float(raw)
    except ValueError as exc:
        raise SourceUnavailable(f"DrenaData: {field} não é numérico") from exc
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        raise SourceUnavailable(f"DrenaData: {field} fora do intervalo válido")
    return number


def _boolean(value: str | None, field: str) -> bool:
    raw = _require_text(value, field).lower()
    if raw in {"true", "1"}:
        return True
    if raw in {"false", "0"}:
        return False
    raise SourceUnavailable(f"DrenaData: {field} não é booleano")


def _csv_rows(path: Path, required_columns: set[str], expected_count: int) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames
            if not columns or len(columns) != len(set(columns)) or not required_columns.issubset(columns):
                raise SourceUnavailable(f"DrenaData: colunas ausentes/duplicadas em {path.name}")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise SourceUnavailable(f"DrenaData: não foi possível ler {path.name}") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise SourceUnavailable(f"DrenaData: linha malformada em {path.name}")
    if len(rows) != expected_count:
        raise SourceUnavailable(
            f"DrenaData: {path.name} tem {len(rows)} linhas, metadado informa {expected_count}"
        )
    return rows


def _unique(values: list[str], field: str) -> None:
    if len(values) != len(set(values)):
        raise SourceUnavailable(f"DrenaData: {field} duplicado")


def _query_time(value: datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} precisa incluir fuso horário")
    return value.astimezone(timezone.utc)


def _query_point_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source_point_id precisa ser preenchido")
    return value.strip()


def _query_window(start: datetime | None, end: datetime | None) -> tuple[datetime | None, datetime | None]:
    start_utc = _query_time(start, "start")
    end_utc = _query_time(end, "end")
    if start_utc and end_utc and end_utc < start_utc:
        raise ValueError("end deve ser posterior ou igual a start")
    return start_utc, end_utc


@dataclass(frozen=True)
class DrenaDataSource:
    """Snapshot Ouro validado, pronto para consultas por IDs externos."""

    snapshot_at: datetime
    registry: PointRegistry
    readings: tuple[_Reading, ...]
    precipitation: tuple[_Precipitation, ...]

    def _reading_evidence(self, row: _Reading) -> Evidence:
        return Evidence(
            source_system="drenadata",
            kind="water_level",
            source_record_id=f"reading:{row.record_id}",
            source_point_id=row.point_id,
            canonical_point_id=self.registry.resolve("drenadata", row.point_id),
            observed_at=row.observed_at,
            collected_at=row.collected_at,
            snapshot_at=self.snapshot_at,
            data_origin="synthetic",
            review_status="not_applicable",
            facts={
                "water_level_cm": row.water_level_cm,
                "in_attention": row.in_attention,
                "sensor_status": row.sensor_status,
                "unit": "cm",
            },
        )

    def _rain_evidence(self, row: _Precipitation) -> Evidence:
        return Evidence(
            source_system="drenadata",
            kind="precipitation",
            source_record_id=f"precipitation:{row.observed_at.isoformat().replace('+00:00', 'Z')}",
            observed_at=row.observed_at,
            collected_at=row.collected_at,
            snapshot_at=self.snapshot_at,
            data_origin="real",
            review_status="not_applicable",
            facts={
                "precipitation_mm": row.precipitation_mm,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "unit": "mm/h",
                "source": "Open-Meteo Archive",
                "license": "CC BY 4.0",
                "scope": "grade histórica piloto de São Paulo; não mede chuva em cada ralo",
            },
            source_uri=WEATHER_SOURCE_URI,
        )

    def latest_reading(self, source_point_id: str) -> Evidence | None:
        """Última leitura válida de um ID **externo** da DrenaData."""
        point_id = _query_point_id(source_point_id)
        rows = (row for row in self.readings if row.point_id == point_id)
        latest = max(rows, key=lambda row: (row.observed_at, row.record_id), default=None)
        return self._reading_evidence(latest) if latest else None

    def reading_series(
        self,
        source_point_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Evidence]:
        """Leituras válidas no intervalo inclusivo, ordenadas por horário."""
        point_id = _query_point_id(source_point_id)
        start_utc, end_utc = _query_window(start, end)
        rows = (
            row for row in self.readings
            if row.point_id == point_id
            and (start_utc is None or row.observed_at >= start_utc)
            and (end_utc is None or row.observed_at <= end_utc)
        )
        return [self._reading_evidence(row) for row in rows]

    def historical_precipitation(
        self, *, start: datetime | None = None, end: datetime | None = None
    ) -> list[Evidence]:
        """Chuva horária observada na grade piloto, nunca previsão meteorológica."""
        start_utc, end_utc = _query_window(start, end)
        rows = (
            row for row in self.precipitation
            if (start_utc is None or row.observed_at >= start_utc)
            and (end_utc is None or row.observed_at <= end_utc)
        )
        return [self._rain_evidence(row) for row in rows]


def load_gold_export(export_dir: str | Path, registry: PointRegistry | None = None) -> DrenaDataSource:
    """Carrega a Ouro local com validação integral e sem fallback silencioso."""
    directory = Path(export_dir)
    if not directory.is_dir():
        raise SourceUnavailable(f"DrenaData: diretório Ouro indisponível: {directory}")
    metadata_path = directory / "export_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceUnavailable("DrenaData: export_metadata.json ausente ou inválido") from exc
    if not isinstance(metadata, dict) or metadata.get("timezone") != "UTC":
        raise SourceUnavailable("DrenaData: metadado timezone precisa ser UTC")
    snapshot_at = _utc_time(metadata.get("exported_at_utc"), "exported_at_utc")
    counts = metadata.get("files")
    if not isinstance(counts, dict):
        raise SourceUnavailable("DrenaData: contagens da exportação ausentes")
    for filename in REQUIRED_FILES:
        count = counts.get(filename)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise SourceUnavailable(f"DrenaData: contagem inválida para {filename}")

    places_rows = _csv_rows(directory / "dim_local.csv", {"local_id", "ponto_id", "is_synthetic"}, counts["dim_local.csv"])
    times_rows = _csv_rows(directory / "dim_tempo.csv", {"tempo_id", "data_hora"}, counts["dim_tempo.csv"])
    fact_rows = _csv_rows(
        directory / "fato_monitoramento.csv",
        {"leitura_id", "local_id", "tempo_id", "nivel_agua_cm", "em_atencao", "sensor_status", "is_synthetic", "collected_at"},
        counts["fato_monitoramento.csv"],
    )
    rain_rows = _csv_rows(
        directory / "precipitacao_horaria.csv",
        {"data_hora", "latitude", "longitude", "precipitacao_mm", "source", "collected_at"},
        counts["precipitacao_horaria.csv"],
    )

    places: dict[str, str] = {}
    for row in places_rows:
        local_id = _require_text(row["local_id"], "local_id")
        point_id = _require_text(row["ponto_id"], "ponto_id")
        if local_id in places:
            raise SourceUnavailable("DrenaData: local_id duplicado")
        if not _boolean(row["is_synthetic"], "dim_local.is_synthetic"):
            raise SourceUnavailable("DrenaData: este adaptador aceita somente locais sintéticos")
        places[local_id] = point_id
    _unique(list(places.values()), "dim_local.ponto_id")

    times: dict[str, datetime] = {}
    for row in times_rows:
        time_id = _require_text(row["tempo_id"], "tempo_id")
        observed_at = _utc_time(row["data_hora"], "dim_tempo.data_hora")
        if time_id in times:
            raise SourceUnavailable("DrenaData: tempo_id duplicado")
        if _utc_time(time_id, "tempo_id", allow_naive=True) != observed_at:
            raise SourceUnavailable("DrenaData: tempo_id diverge de data_hora")
        times[time_id] = observed_at
    _unique([moment.isoformat() for moment in times.values()], "dim_tempo.data_hora")

    readings: list[_Reading] = []
    reading_ids: list[str] = []
    for row in fact_rows:
        record_id = _require_text(row["leitura_id"], "leitura_id")
        local_id = _require_text(row["local_id"], "fato.local_id")
        time_id = _require_text(row["tempo_id"], "fato.tempo_id")
        if local_id not in places or time_id not in times:
            raise SourceUnavailable("DrenaData: fato_monitoramento referencia dimensão inexistente")
        if not _boolean(row["is_synthetic"], "fato.is_synthetic"):
            raise SourceUnavailable("DrenaData: este adaptador aceita somente leituras sintéticas")
        collected_at = _utc_time(row["collected_at"], "fato.collected_at")
        if times[time_id] > collected_at:
            raise SourceUnavailable("DrenaData: leitura observada depois da coleta")
        if collected_at > snapshot_at:
            raise SourceUnavailable("DrenaData: coleta posterior à exportação")
        readings.append(_Reading(
            record_id=record_id,
            point_id=places[local_id],
            observed_at=times[time_id],
            collected_at=collected_at,
            water_level_cm=_number(row["nivel_agua_cm"], "nivel_agua_cm", minimum=0, maximum=300),
            in_attention=_boolean(row["em_atencao"], "em_atencao"),
            sensor_status=_require_text(row["sensor_status"], "sensor_status"),
        ))
        reading_ids.append(record_id)
    _unique(reading_ids, "leitura_id")

    rain: list[_Precipitation] = []
    rain_hours: list[str] = []
    for row in rain_rows:
        observed_at = _utc_time(row["data_hora"], "precipitacao_horaria.data_hora")
        if _require_text(row["source"], "precipitacao_horaria.source") != "open-meteo-archive":
            raise SourceUnavailable("DrenaData: origem de chuva inesperada")
        collected_at = _utc_time(row["collected_at"], "precipitacao_horaria.collected_at")
        if observed_at > collected_at:
            raise SourceUnavailable("DrenaData: chuva observada depois da coleta")
        if collected_at > snapshot_at:
            raise SourceUnavailable("DrenaData: coleta de chuva posterior à exportação")
        rain.append(_Precipitation(
            observed_at=observed_at,
            collected_at=collected_at,
            precipitation_mm=_number(row["precipitacao_mm"], "precipitacao_mm", minimum=0),
            latitude=_number(row["latitude"], "latitude", minimum=-90, maximum=90),
            longitude=_number(row["longitude"], "longitude", minimum=-180, maximum=180),
        ))
        rain_hours.append(observed_at.isoformat())
    _unique(rain_hours, "precipitacao_horaria.data_hora")

    return DrenaDataSource(
        snapshot_at=snapshot_at,
        registry=registry or PointRegistry(version="unlinked"),
        readings=tuple(sorted(readings, key=lambda row: (row.observed_at, row.record_id))),
        precipitation=tuple(sorted(rain, key=lambda row: row.observed_at)),
    )
