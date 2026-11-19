"""API HTTP da Central DrenaHub para consultas somente leitura."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .assistant import ask
from .models import AskRequest, AskResponse, Configuration
from .ollama_client import OllamaClient
from .api_v2 import router as v2_router


ROOT = Path(__file__).resolve().parents[1]
SCOREBOARD_PATH = ROOT / "avaliacao" / "resultados" / "placar.json"
AUDIT_PATH = ROOT / "avaliacao" / "resultados" / "auditoria_semantica.json"
STATIC_PATH = ROOT / "app" / "static"
app = FastAPI(title="DrenaAssist", version="0.1.0", description="Assistente local para operacoes e manutencao de drenagem")
origins = [item.strip() for item in os.getenv("DRENA_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
app.include_router(v2_router)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_PATH / "index.html")


@app.get("/v2/console", include_in_schema=False)
def v2_console() -> FileResponse:
    return FileResponse(STATIC_PATH / "v2.html")


@app.get("/health")
def health() -> dict[str, object]:
    client = OllamaClient()
    return {"status": "ok", "ollama_model_available": client.available(), "model": client.model, "operational_data": "synthetic"}


@app.get("/assistant/configurations")
def configurations() -> dict[str, object]:
    return {
        "model": OllamaClient().model,
        "configurations": [
            {"id": Configuration.baseline.value, "description": "LLM local sem documentos ou ferramentas"},
            {"id": Configuration.rag.value, "description": "LLM local com documentos recuperados por embeddings"},
            {"id": Configuration.agent.value, "description": "Mesma LLM com documentos e ferramentas de consulta operacional"},
        ],
    }


@app.post("/assistant/ask", response_model=AskResponse)
async def ask_endpoint(request: AskRequest):
    result = await run_in_threadpool(ask, request.question, request.configuration, request.location_id, request.point_id)
    if result.metadata.get("error"):
        return JSONResponse(status_code=503, content=result.model_dump(mode="json"))
    return result


@app.get("/evaluation/results")
def evaluation_results() -> dict[str, object]:
    if not SCOREBOARD_PATH.exists():
        raise HTTPException(status_code=404, detail="Avaliação ainda não executada")
    return json.loads(SCOREBOARD_PATH.read_text(encoding="utf-8"))


@app.get("/evaluation/audit")
def evaluation_audit() -> dict[str, object]:
    if not AUDIT_PATH.exists():
        raise HTTPException(status_code=404, detail="Auditoria ainda não executada")
    return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
