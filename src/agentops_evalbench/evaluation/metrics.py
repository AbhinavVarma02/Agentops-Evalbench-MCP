"""Evaluation metrics.

This is the heart of the platform. Every metric returns a float in ``[0, 1]``
and has TWO implementations:

* a **custom, dependency-free** version based on claim/term overlap, and
* an optional **LLM judge** (OpenAI) that scores the same dimensions.

The custom versions are the default and the fallback. They make the whole
platform runnable offline, in CI, and without RAGAS/DeepEval — which is
important because those libraries are heavy and sometimes lag new Python
releases. When RAGAS/DeepEval or an OpenAI judge are available they can be
layered on top, but the numbers below are always meaningful on their own.

Metric definitions
------------------
* **groundedness**       — average support of the answer's claims in the context.
* **hallucination_risk** — share of answer claims that are clearly unsupported.
* **answer_relevance**   — how directly the answer addresses the question.
* **retrieval_score**    — whether the retrieved context contains the key terms
                            needed to answer (question + expected answer).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Lightweight text utilities (kept local so this module has no rag dependency)
# --------------------------------------------------------------------------- #
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
    "where",
    "why",
    "must",
    "will",
    "can",
    "may",
    "should",
    "would",
    "could",
    "do",
    "does",
    "did",
    "has",
    "have",
    "had",
    "not",
    "no",
    "than",
    "then",
    "there",
    "here",
    "its",
    "their",
    "your",
    "you",
}

# Phrases that indicate the model declined to answer.
_REFUSAL_RE = re.compile(
    r"\b(i (don'?t|do not) know|cannot answer|can'?t answer|no information|"
    r"not (enough|sufficient) (information|context)|insufficient context|"
    r"not (in|found in) the (provided )?context|unable to answer)\b",
    re.IGNORECASE,
)


def _content_tokens(text: str) -> set[str]:
    """Return the set of meaningful (non-stopword) tokens in ``text``."""
    return {
        t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 1 and t not in _STOPWORDS
    }


def _sentences(text: str) -> list[str]:
    """Split text into sentences (also treats list bullets as sentences)."""
    if not text:
        return []
    # Break on sentence punctuation and newlines/bullets so list items count.
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -*•\t").strip() for p in parts if p and p.strip(" -*•\t").strip()]


def is_refusal(answer: str) -> bool:
    """True when the answer is an "I don't know"-style refusal."""
    return bool(_REFUSAL_RE.search(answer or ""))


def _overlap(a: set[str], b: set[str]) -> float:
    """Fraction of ``a`` present in ``b`` (recall of a against b). 0..1."""
    if not a:
        return 0.0
    return len(a & b) / len(a)


# --------------------------------------------------------------------------- #
# Custom metrics (default + fallback)
# --------------------------------------------------------------------------- #
# A claim counts as "supported" when at least this fraction of its content
# tokens appear in the retrieved context.
_CLAIM_SUPPORT_THRESHOLD = 0.6


def groundedness_score(answer: str, context: str) -> float:
    """Average support of the answer's claims in the context (0..1).

    Each sentence in the answer is a claim; its support is the share of its
    content tokens found in the context. Groundedness is the mean support over
    all claims. A refusal with no context is treated as fully grounded (it is
    honest rather than fabricated).
    """
    context_tokens = _content_tokens(context)
    claims = _sentences(answer)

    if not claims:
        return 0.0
    if is_refusal(answer) and not context_tokens:
        return 1.0

    supports: list[float] = []
    for claim in claims:
        claim_tokens = _content_tokens(claim)
        if not claim_tokens:
            continue
        supports.append(_overlap(claim_tokens, context_tokens))
    if not supports:
        return 0.0
    return round(sum(supports) / len(supports), 4)


def hallucination_risk_score(answer: str, context: str) -> float:
    """Share of answer claims that are clearly unsupported by the context (0..1).

    Distinct from (1 - groundedness): this counts how many claims fall *below*
    the support threshold, i.e. how many statements look fabricated, rather than
    the average support level. Higher = riskier.
    """
    context_tokens = _content_tokens(context)
    claims = _sentences(answer)
    if not claims:
        return 1.0
    if is_refusal(answer):
        return 0.0  # refusing to answer does not fabricate anything

    considered = 0
    unsupported = 0
    for claim in claims:
        claim_tokens = _content_tokens(claim)
        if not claim_tokens:
            continue
        considered += 1
        if _overlap(claim_tokens, context_tokens) < _CLAIM_SUPPORT_THRESHOLD:
            unsupported += 1
    if considered == 0:
        return 1.0
    return round(unsupported / considered, 4)


def answer_relevance_score(question: str, answer: str) -> float:
    """How directly the answer addresses the question (0..1).

    Uses recall of the question's key terms in the answer, with a strong penalty
    for refusals and near-empty answers (they do not actually answer).
    """
    if not answer or not answer.strip():
        return 0.0
    q_tokens = _content_tokens(question)
    a_tokens = _content_tokens(answer)
    if not q_tokens:
        # No specific terms to match; reward a substantive answer, penalize empty.
        base = 1.0 if len(a_tokens) >= 3 else 0.3
    else:
        base = _overlap(q_tokens, a_tokens)
    if is_refusal(answer):
        base = min(base, 0.2)
    return round(base, 4)


def retrieval_quality_score(
    question: str, context: str, expected_answer: str | None = None
) -> float:
    """Whether the retrieved context contains the key terms needed to answer.

    Key terms are drawn from the question and, when available, the expected
    answer — so retrieval is judged on whether it surfaced the information the
    correct answer requires.
    """
    context_tokens = _content_tokens(context)
    if not context_tokens:
        return 0.0
    key_terms = _content_tokens(question)
    if expected_answer:
        key_terms |= _content_tokens(expected_answer)
    if not key_terms:
        return 0.0
    return round(_overlap(key_terms, context_tokens), 4)


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
@dataclass
class MetricScores:
    """The four quality scores plus which method produced them."""

    groundedness: float
    hallucination_risk: float
    answer_relevance: float
    retrieval_score: float
    method: str = "custom"  # "custom" or "llm"

    def as_dict(self) -> dict[str, float | str]:
        return {
            "groundedness": self.groundedness,
            "hallucination_risk": self.hallucination_risk,
            "answer_relevance": self.answer_relevance,
            "retrieval_score": self.retrieval_score,
            "method": self.method,
        }


def custom_scores(
    question: str, answer: str, context: str, expected_answer: str | None = None
) -> MetricScores:
    """Compute all four metrics with the dependency-free custom evaluators."""
    return MetricScores(
        groundedness=groundedness_score(answer, context),
        hallucination_risk=hallucination_risk_score(answer, context),
        answer_relevance=answer_relevance_score(question, answer),
        retrieval_score=retrieval_quality_score(question, context, expected_answer),
        method="custom",
    )


# --------------------------------------------------------------------------- #
# Optional LLM judge (OpenAI). Falls back to custom scores on any error.
# --------------------------------------------------------------------------- #
_LLM_JUDGE_SYSTEM = (
    "You are a strict evaluation judge for a RAG system. Given a question, a "
    "generated answer, and the retrieved context, score four metrics from 0.0 to "
    "1.0 and return ONLY compact JSON with keys: groundedness, hallucination_risk, "
    "answer_relevance, retrieval_score. groundedness = how well the answer is "
    "supported by the context; hallucination_risk = fraction of the answer that is "
    "unsupported; answer_relevance = how directly it answers the question; "
    "retrieval_score = whether the context contains the needed information."
)


def llm_judge_scores(
    question: str,
    answer: str,
    context: str,
    expected_answer: str | None = None,
    model: str | None = None,
) -> MetricScores:
    """Score with an OpenAI judge. Returns custom scores if OpenAI is unavailable."""
    from ..config import get_settings

    settings = get_settings()
    if not settings.has_openai_key:
        return custom_scores(question, answer, context, expected_answer)
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
        payload = (
            f"Question: {question}\n\nRetrieved context:\n{context}\n\n"
            f"Generated answer:\n{answer}"
        )
        if expected_answer:
            payload += f"\n\nReference answer:\n{expected_answer}"
        resp = client.chat.completions.create(
            model=model or settings.default_model,
            messages=[
                {"role": "system", "content": _LLM_JUDGE_SYSTEM},
                {"role": "user", "content": payload},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")

        def _clip(x: object, default: float) -> float:
            try:
                return max(0.0, min(1.0, float(x)))
            except (TypeError, ValueError):
                return default

        fallback = custom_scores(question, answer, context, expected_answer)
        return MetricScores(
            groundedness=_clip(data.get("groundedness"), fallback.groundedness),
            hallucination_risk=_clip(data.get("hallucination_risk"), fallback.hallucination_risk),
            answer_relevance=_clip(data.get("answer_relevance"), fallback.answer_relevance),
            retrieval_score=_clip(data.get("retrieval_score"), fallback.retrieval_score),
            method="llm",
        )
    except Exception:
        # Any failure (network/quota/parse) -> deterministic custom scores.
        return custom_scores(question, answer, context, expected_answer)


def score_answer(
    question: str,
    answer: str,
    context: str,
    expected_answer: str | None = None,
    use_llm_judge: bool = False,
    model: str | None = None,
) -> MetricScores:
    """Public entry point: score one answer, LLM judge optional (custom default)."""
    if use_llm_judge:
        return llm_judge_scores(question, answer, context, expected_answer, model)
    return custom_scores(question, answer, context, expected_answer)
