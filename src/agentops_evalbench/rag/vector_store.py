"""Vector store abstraction with two backends.

* ``ChromaVectorStore`` — ChromaDB + OpenAI embeddings (semantic retrieval).
* ``SimpleVectorStore`` — pure-Python TF-IDF cosine similarity (zero deps).

``build_vector_store()`` picks Chroma when an OpenAI key and ChromaDB are both
available, and otherwise falls back to the Simple store. Because the evaluator
computes retrieval quality from term overlap (not from the store's internal
score), both backends produce comparable, meaningful evaluations — the Simple
store keeps the whole platform runnable offline and in CI.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter

from ..config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "is",
    "are",
    "for",
    "on",
    "at",
    "by",
    "be",
    "as",
    "it",
    "that",
    "this",
    "with",
    "from",
    "was",
    "were",
    "what",
    "which",
    "who",
    "how",
    "when",
    "must",
    "will",
    "can",
    "may",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


class BaseVectorStore:
    """Common interface shared by both backends."""

    backend: str = "base"

    def add_texts(self, texts: list[str]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def query(self, text: str, k: int = 4) -> list[tuple[str, float]]:  # pragma: no cover
        raise NotImplementedError


class SimpleVectorStore(BaseVectorStore):
    """TF-IDF cosine similarity retriever with no external dependencies."""

    backend = "simple"

    def __init__(self) -> None:
        self._texts: list[str] = []
        self._tfs: list[Counter] = []
        self._df: Counter = Counter()  # document frequency per term
        self._n = 0

    def add_texts(self, texts: list[str]) -> None:
        for t in texts:
            tf = Counter(_tokenize(t))
            self._texts.append(t)
            self._tfs.append(tf)
            for term in tf:
                self._df[term] += 1
            self._n += 1

    def _idf(self, term: str) -> float:
        # Smoothed inverse document frequency.
        return math.log((1 + self._n) / (1 + self._df.get(term, 0))) + 1.0

    def _weighted(self, tf: Counter) -> dict[str, float]:
        return {term: freq * self._idf(term) for term, freq in tf.items()}

    def query(self, text: str, k: int = 4) -> list[tuple[str, float]]:
        if not self._texts:
            return []
        qv = self._weighted(Counter(_tokenize(text)))
        qnorm = math.sqrt(sum(v * v for v in qv.values())) or 1.0

        scored: list[tuple[str, float]] = []
        for idx, tf in enumerate(self._tfs):
            dv = self._weighted(tf)
            dnorm = math.sqrt(sum(v * v for v in dv.values())) or 1.0
            dot = sum(qv.get(term, 0.0) * val for term, val in dv.items())
            scored.append((self._texts[idx], dot / (qnorm * dnorm)))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB-backed store using OpenAI embeddings.

    A fresh collection is created on each build so re-indexing the sample docs
    never leaves stale or duplicated chunks behind.
    """

    backend = "chromadb"

    def __init__(
        self, collection_name: str, persist_dir, embedding_model: str, api_key: str
    ) -> None:
        import chromadb  # lazy import (optional dependency)
        from openai import OpenAI

        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass  # collection may not exist yet
        self._collection = self._client.create_collection(collection_name)
        self._openai = OpenAI(api_key=api_key)
        self._embedding_model = embedding_model
        self._count = 0

    def _embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._openai.embeddings.create(model=self._embedding_model, input=texts)
        return [item.embedding for item in resp.data]

    def add_texts(self, texts: list[str]) -> None:
        if not texts:
            return
        embeddings = self._embed(list(texts))
        ids = [f"chunk-{self._count + i}" for i in range(len(texts))]
        self._collection.add(ids=ids, documents=list(texts), embeddings=embeddings)
        self._count += len(texts)

    def query(self, text: str, k: int = 4) -> list[tuple[str, float]]:
        q_emb = self._embed([text])[0]
        res = self._collection.query(query_embeddings=[q_emb], n_results=k)
        docs = (res.get("documents") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out: list[tuple[str, float]] = []
        for doc, dist in zip(docs, dists, strict=False):
            # Convert a distance into a rough 0..1 similarity for display.
            sim = 1.0 / (1.0 + float(dist)) if dist is not None else 0.0
            out.append((doc, sim))
        return out


def build_vector_store(
    collection_name: str = "agentops_eval",
    use_openai: bool | None = None,
) -> BaseVectorStore:
    """Return the best available vector store.

    Falls back to ``SimpleVectorStore`` if OpenAI/ChromaDB are unavailable or
    error out, so retrieval always works.
    """
    settings = get_settings()
    if use_openai is None:
        use_openai = settings.has_openai_key

    if use_openai:
        try:
            store = ChromaVectorStore(
                collection_name=collection_name,
                persist_dir=settings.chroma_dir,
                embedding_model=settings.default_embedding_model,
                api_key=settings.openai_api_key.get_secret_value(),
            )
            logger.info("Using ChromaDB vector store (OpenAI embeddings).")
            return store
        except Exception as exc:  # noqa: BLE001 - fall back on any failure
            logger.warning("ChromaDB unavailable (%s); falling back to SimpleVectorStore.", exc)

    logger.info("Using SimpleVectorStore (TF-IDF, offline).")
    return SimpleVectorStore()
