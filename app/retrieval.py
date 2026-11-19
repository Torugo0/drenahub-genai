"""Busca vetorial local com Sentence Transformers e similaridade cosseno."""

import re
import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = ROOT / "base" / "chunks.jsonl"
DEFAULT_INDEX_PATH = ROOT / "base" / "index.npz"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    source: str
    url: str
    text: str
    license: str
    accessed_at: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    rank: int


def load_chunks(path: Path | str = DEFAULT_CHUNKS_PATH) -> list[Chunk]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks = [Chunk(**row) for row in rows]
    ids = [chunk.chunk_id for chunk in chunks]
    if not chunks or len(ids) != len(set(ids)):
        raise ValueError("Base vazia ou IDs de trechos duplicados")
    return chunks


class Retriever:
    def __init__(
        self,
        chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
        index_path: Path | str = DEFAULT_INDEX_PATH,
        model_name: str | None = None,
    ):
        self.chunks_path = Path(chunks_path)
        self.index_path = Path(index_path)
        self.model_name = model_name or os.getenv("DRENA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        self.chunks = load_chunks(self.chunks_path)
        self._model: Any = None
        self._matrix: np.ndarray | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.model_name.encode("utf-8"))
        digest.update(self.chunks_path.read_bytes())
        return digest.hexdigest()

    def build_index(self, force: bool = False) -> np.ndarray:
        fingerprint = self._fingerprint()
        if not force and self._matrix is not None:
            return self._matrix
        if not force and self.index_path.exists():
            with np.load(self.index_path, allow_pickle=False) as stored:
                if str(stored["fingerprint"]) == fingerprint and stored["embeddings"].shape[0] == len(self.chunks):
                    self._matrix = stored["embeddings"].astype(np.float32)
                    return self._matrix
        embeddings = self.model.encode([chunk.text for chunk in self.chunks], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        matrix = np.asarray(embeddings, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.maximum(norms, 1e-12)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.index_path, embeddings=matrix, fingerprint=fingerprint)
        self._matrix = matrix
        return matrix

    def search(self, query: str, top_k: int = 3, threshold: float | None = None, expand: bool = True) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        matrix = self.build_index()
        text = expand_query(query) if expand else query
        vector = np.asarray(self.model.encode(text, normalize_embeddings=True, convert_to_numpy=True), dtype=np.float32).reshape(-1)
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        scores = matrix @ vector
        ranking = np.argsort(-scores, kind="stable")[: max(0, min(top_k, len(self.chunks)))]
        return [
            RetrievedChunk(chunk=self.chunks[int(index)], score=float(scores[index]), rank=rank)
            for rank, index in enumerate(ranking, start=1)
            if threshold is None or float(scores[index]) >= threshold
        ]


# Termos do dia a dia do zelador -> termos usados nos manuais técnicos.
# A base fala em "caixa de captação" e "grelha"; quem pergunta fala "ralo" e "bueiro".
_POPULAR_TERMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), technical)
    for pattern, technical in (
        (r"\b(ralos?|bueiros?|boca[s]?[ -]de[ -]lobo|sarjetas?)\b", "caixa de captação e grelha de drenagem pluvial"),
        (r"\b(entupid[oa]s?|entupiment[oa]s?|entupir|desentupir|desentupiment[oa])\b", "obstrução, limpeza e remoção de detritos e sedimentos"),
        (r"\b(lixo|sujeira|folhas)\b", "detritos e resíduos"),
        (r"\b(alagamentos?|alagad[oa]s?|enchentes?)\b", "inundação"),
        (r"\b(valetas?)\b", "canais e valas"),
    )
)


def expand_query(query: str) -> str:
    """Acrescenta à pergunta os termos técnicos equivalentes às palavras populares."""
    extras = [technical for pattern, technical in _POPULAR_TERMS if pattern.search(query)]
    return f"{query} ({'; '.join(extras)})" if extras else query


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()
