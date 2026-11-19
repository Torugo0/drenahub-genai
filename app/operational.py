"""Consultas somente leitura sobre registros demonstrativos sinteticos."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = ROOT / "base" / "operational.json"
ALLOWED_TOOLS = frozenset(
    {
        "get_sensor_readings",
        "get_recent_events",
        "get_visual_inspections",
        "get_maintenance_history",
        "get_event",
        "get_points",
        "get_maintenance_queue",
    }
)


class ToolNotAllowed(ValueError):
    """A ferramenta solicitada nao pertence a lista de consulta segura."""


class OperationalStore:
    def __init__(self, path: Path | str = DEFAULT_DATA_PATH):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        if self.data.get("synthetic") is not True:
            raise ValueError("A base demonstrativa deve estar identificada como sintetica")
        self._points = {row["id"]: row for row in self.data["points"]}
        self._locations = {row["id"]: row for row in self.data["locations"]}
        for event in self.data["events"]:
            if event["priority"] != self.calculated_priority(event["point_id"]):
                raise ValueError(f"Prioridade de {event['id']} diverge das regras explicitas")

    def point_id(self, value: str | None) -> str | None:
        if not value:
            return None
        upper = value.upper().replace(" ", "_")
        for point in self.data["points"]:
            if upper == point["id"] or upper in point.get("external_ids", []):
                return point["id"]
        return value

    def location_id(self, value: str | None) -> str | None:
        if not value:
            return None
        upper = value.upper().replace(" ", "-")
        aliases = {"GARAGEM-A": "GAR-A", "GARAGEM_A": "GAR-A", "GARAGEM-B": "GAR-B", "GARAGEM_B": "GAR-B", "GALPAO-NORTE": "GAL-1", "GALPAO_NORTE": "GAL-1"}
        return aliases.get(upper, aliases.get(value.upper(), value))

    def infer_ids(self, question: str, location_id: str | None, point_id: str | None) -> tuple[str | None, str | None, str | None]:
        q = question.upper()
        if not point_id:
            for point in self.data["points"]:
                if point["id"] in q or point["name"].upper() in q:
                    point_id = point["id"]
                    break
        if not point_id:
            match = re.search(r"\bRALO[\s_-]*(\d+)\b", q)
            if match:
                point_id = f"RALO-{int(match.group(1)):02d}"
        point_id = self.point_id(point_id)
        if not location_id:
            for loc in self.data["locations"]:
                if loc["id"] in q or loc["name"].upper() in q:
                    location_id = loc["id"]
                    break
        location_id = self.location_id(location_id)
        if not location_id and point_id in self._points:
            location_id = self._points[point_id]["location_id"]
        if location_id and point_id in self._points and self._points[point_id]["location_id"] != location_id:
            raise ValueError("Ponto e localizacao informados nao correspondem")
        event_id = next((row["id"] for row in self.data["events"] if row["id"] in q or row["id"].replace("OC-", "OCORRENCIA ") in q or row["id"].replace("OC-", "OCORRÊNCIA ") in q), None)
        if not event_id:
            match = re.search(r"\b(?:OC|OCORRENCIA|OCORRÊNCIA)[\s_-]*(\d+)\b", q)
            if match:
                event_id = f"OC-{int(match.group(1)):03d}"
        if event_id:
            event = next((row for row in self.data["events"] if row["id"] == event_id), None)
            if event:
                point_id = point_id or event["point_id"]
                location_id = location_id or event["location_id"]
        return location_id, point_id, event_id

    def calculated_priority(self, point_id: str) -> str:
        point = self._points[point_id]
        readings = self.get_sensor_readings(point_id)
        inspections = self.get_visual_inspections(point_id)
        above_alert = bool(readings and readings[0]["water_level_cm"] > point["alert_level_cm"])
        obstructed = bool(inspections and inspections[0]["obstruction"])
        if above_alert and obstructed:
            return "alta"
        if above_alert or obstructed:
            return "media"
        return "baixa"

    def _limit(self, rows: list[dict[str, Any]], field: str, limit: int = 10) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda item: item[field], reverse=True)[:limit]

    def get_sensor_readings(self, point_id: str | None = None, location_id: str | None = None) -> list[dict[str, Any]]:
        point_id = self.point_id(point_id)
        location_id = self.location_id(location_id)
        rows = [r for r in self.data["sensor_readings"] if (point_id is None or r["point_id"] == point_id) and (location_id is None or self._points[r["point_id"]]["location_id"] == location_id)]
        return self._limit(rows, "timestamp")

    def get_recent_events(self, location_id: str | None = None) -> list[dict[str, Any]]:
        location_id = self.location_id(location_id)
        rows = [r for r in self.data["events"] if location_id is None or r["location_id"] == location_id]
        return self._limit(rows, "opened_at")

    def get_visual_inspections(self, point_id: str | None = None, location_id: str | None = None) -> list[dict[str, Any]]:
        point_id = self.point_id(point_id)
        location_id = self.location_id(location_id)
        rows = [r for r in self.data["visual_inspections"] if (point_id is None or r["point_id"] == point_id) and (location_id is None or self._points[r["point_id"]]["location_id"] == location_id)]
        return self._limit(rows, "timestamp")

    def get_maintenance_history(self, point_id: str | None = None, location_id: str | None = None) -> list[dict[str, Any]]:
        point_id = self.point_id(point_id)
        location_id = self.location_id(location_id)
        rows = [r for r in self.data["maintenance_history"] if (point_id is None or r["point_id"] == point_id) and (location_id is None or self._points[r["point_id"]]["location_id"] == location_id)]
        return self._limit(rows, "timestamp")

    def get_event(self, event_id: str) -> list[dict[str, Any]]:
        return [r for r in self.data["events"] if r["id"] == event_id.upper()]

    def get_points(self, location_id: str | None = None) -> list[dict[str, Any]]:
        location_id = self.location_id(location_id)
        return [r for r in self.data["points"] if location_id is None or r["location_id"] == location_id]

    def get_maintenance_queue(self, location_id: str | None = None) -> list[dict[str, Any]]:
        location_id = self.location_id(location_id)
        return [r for r in self.data["events"] if r["status"] == "aguardando_manutencao" and (location_id is None or r["location_id"] == location_id)]

    def call(self, name: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        if name not in ALLOWED_TOOLS:
            raise ToolNotAllowed(name)
        allowed_args = {
            "get_sensor_readings": {"point_id", "location_id"},
            "get_recent_events": {"location_id"},
            "get_visual_inspections": {"point_id", "location_id"},
            "get_maintenance_history": {"point_id", "location_id"},
            "get_event": {"event_id"},
            "get_points": {"location_id"},
            "get_maintenance_queue": {"location_id"},
        }[name]
        if any(key in allowed_args and (not isinstance(value, str) or not value or len(value) > 80) for key, value in arguments.items()):
            return []
        clean = {key: value for key, value in arguments.items() if key in allowed_args and isinstance(value, str) and len(value) <= 80}
        if name == "get_event" and "event_id" not in clean:
            return []
        fn: Callable[..., list[dict[str, Any]]] = getattr(self, name)
        return fn(**clean)


def log_tool_call(name: str, arguments: dict[str, Any], result: list[dict[str, Any]], elapsed_ms: float) -> dict[str, Any]:
    """Registra argumentos e resultados da base sintetica, sem dados pessoais."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": name,
        "arguments": {key: value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) else "[redacted]" for key, value in arguments.items()},
        "result_ids": [row["id"] for row in result],
        "result_count": len(result),
        "result": result,
        "elapsed_ms": round(elapsed_ms, 2),
    }
    log_path = Path(os.getenv("DRENA_TOOL_LOG_PATH", str(ROOT / "avaliacao" / "tool_calls.jsonl")))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
