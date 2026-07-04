"""RAG pipeline: retrieve context, then generate an answer.

Two execution modes, chosen automatically:

* **OpenAI mode** — embeddings + chat completion (when an API key is present).
* **Offline mode** — TF-IDF retrieval + an *extractive* answer built from the
  most relevant retrieved sentences. This keeps the entire evaluation workflow
  runnable with no API key (demos, CI, tests) while still returning grounded
  answers that the evaluator can score meaningfully.

Every ``answer()`` call returns the question, generated answer, retrieved
context, model name, latency, and a token-usage estimate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from .document_loader import SAMPLE_DOCS_DIR, Chunk, load_and_chunk
from .vector_store import BaseVectorStore, _tokenize, build_vector_store

# A tiny prompt library so prompt-version comparisons are meaningful in the demo.
PROMPT_LIBRARY: dict[str, str] = {
    "v1": (
        "You are a helpful assistant. Answer the question using ONLY the provided "
        "context. If the answer is not in the context, say you don't know. Be "
        "concise and factual."
    ),
    "v2": (
        "You are a precise documentation assistant. Use ONLY the context to answer. "
        "Quote the exact policy wording where possible. If the context is "
        "insufficient, reply: 'I don't know based on the provided context.' Keep "
        "answers to one or two sentences."
    ),
}
DEFAULT_PROMPT_VERSION = "v1"

# Fallback message when retrieval finds nothing usable.
_NO_CONTEXT_ANSWER = "I don't know based on the provided context."


def _estimate_tokens(text: str, model: str) -> int:
    """Best-effort token count. Uses the canonical counter when available."""
    try:
        from ..evaluation.cost_tracker import count_tokens

        return count_tokens(text, model)
    except Exception:
        # ~1.3 tokens per whitespace word is a reasonable rough estimate.
        return max(1, round(len(text.split()) * 1.3))


@dataclass
class RagResult:
    """Everything one RAG answer produces, ready for evaluation + storage."""

    question: str
    generated_answer: str
    retrieved_context: list[str]
    model_name: str
    latency_seconds: float
    token_usage: dict[str, int] = field(default_factory=dict)
    used_openai: bool = False
    prompt_version: str = DEFAULT_PROMPT_VERSION

    @property
    def context_text(self) -> str:
        """Retrieved chunks joined into a single context string."""
        return "\n\n".join(self.retrieved_context)


def _extractive_answer(question: str, chunks: list[str], max_sentences: int = 2) -> str:
    """Build a grounded answer offline by selecting the most relevant sentences.

    Splits the retrieved context into sentences and ranks them by token overlap
    with the question. This is deliberately simple and deterministic so offline
    runs are reproducible.
    """
    if not chunks:
        return _NO_CONTEXT_ANSWER

    q_tokens = set(_tokenize(question))
    if not q_tokens:
        return chunks[0].strip()

    import re

    sentences: list[str] = []
    for chunk in chunks:
        sentences.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", chunk) if s.strip())

    scored = []
    for sent in sentences:
        s_tokens = set(_tokenize(sent))
        if not s_tokens:
            continue
        overlap = len(q_tokens & s_tokens) / len(q_tokens)
        scored.append((overlap, sent))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    best = [sent for score, sent in scored[:max_sentences] if score > 0]
    if not best:
        return _NO_CONTEXT_ANSWER
    return " ".join(best)


class RAGPipeline:
    """Index documents, then answer questions grounded in retrieved context."""

    def __init__(
        self,
        vector_store: BaseVectorStore,
        model_name: str | None = None,
        use_openai: bool | None = None,
        top_k: int = 4,
    ) -> None:
        settings = get_settings()
        self.vector_store = vector_store
        self.model_name = model_name or settings.default_model
        self.top_k = top_k
        self.use_openai = settings.has_openai_key if use_openai is None else use_openai
        self._settings = settings

    # ---- construction helpers -------------------------------------------- #
    @classmethod
    def from_directory(
        cls,
        directory: str | Path = SAMPLE_DOCS_DIR,
        model_name: str | None = None,
        use_openai: bool | None = None,
        chunk_size: int = 800,
        overlap: int = 100,
        top_k: int = 4,
    ) -> RAGPipeline:
        """Load + chunk a directory of documents and index them."""
        chunks = load_and_chunk(directory, chunk_size=chunk_size, overlap=overlap)
        settings = get_settings()
        resolved_use_openai = settings.has_openai_key if use_openai is None else use_openai
        store = build_vector_store(use_openai=resolved_use_openai)
        store.add_texts([c.text for c in chunks])
        return cls(store, model_name=model_name, use_openai=resolved_use_openai, top_k=top_k)

    @classmethod
    def from_sample_docs(cls, **kwargs) -> RAGPipeline:
        """Convenience: build a pipeline from the bundled sample documents."""
        return cls.from_directory(SAMPLE_DOCS_DIR, **kwargs)

    def index_chunks(self, chunks: list[Chunk]) -> None:
        self.vector_store.add_texts([c.text for c in chunks])

    # ---- retrieval + generation ------------------------------------------ #
    def retrieve(self, question: str, k: int | None = None) -> list[tuple[str, float]]:
        return self.vector_store.query(question, k=k or self.top_k)

    def answer(self, question: str, prompt_version: str = DEFAULT_PROMPT_VERSION) -> RagResult:
        """Retrieve context and generate an answer, timing the whole operation."""
        start = time.perf_counter()

        retrieved = self.retrieve(question)
        context_chunks = [text for text, _score in retrieved]
        context_text = "\n\n".join(context_chunks)
        system_prompt = PROMPT_LIBRARY.get(prompt_version, PROMPT_LIBRARY[DEFAULT_PROMPT_VERSION])

        if self.use_openai:
            answer_text, token_usage, used_openai = self._generate_openai(
                question, context_text, system_prompt
            )
        else:
            answer_text = _extractive_answer(question, context_chunks)
            prompt_tokens = _estimate_tokens(
                system_prompt + context_text + question, self.model_name
            )
            completion_tokens = _estimate_tokens(answer_text, self.model_name)
            token_usage = {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            }
            used_openai = False

        latency = time.perf_counter() - start
        return RagResult(
            question=question,
            generated_answer=answer_text,
            retrieved_context=context_chunks,
            model_name=(
                self.model_name if used_openai else f"{self.model_name} (offline-extractive)"
            ),
            latency_seconds=latency,
            token_usage=token_usage,
            used_openai=used_openai,
            prompt_version=prompt_version,
        )

    def _generate_openai(
        self, question: str, context_text: str, system_prompt: str
    ) -> tuple[str, dict[str, int], bool]:
        """Call OpenAI chat completions. Falls back to extractive on any error."""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._settings.openai_api_key.get_secret_value())
            user_content = f"Context:\n{context_text}\n\nQuestion: {question}"
            resp = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
            )
            answer_text = (resp.choices[0].message.content or "").strip()
            usage = resp.usage
            token_usage = {
                "prompt": getattr(usage, "prompt_tokens", 0),
                "completion": getattr(usage, "completion_tokens", 0),
                "total": getattr(usage, "total_tokens", 0),
            }
            return answer_text, token_usage, True
        except Exception:
            # Network/key/quota failure -> stay usable with the offline path.
            answer_text = _extractive_answer(question, context_text.split("\n\n"))
            p = _estimate_tokens(context_text + question, self.model_name)
            c = _estimate_tokens(answer_text, self.model_name)
            return answer_text, {"prompt": p, "completion": c, "total": p + c}, False
