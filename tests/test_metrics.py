"""Tests for the custom evaluation metrics."""

from agentops_evalbench.evaluation import metrics

CONTEXT = (
    "Groundedness must be at least 0.80. Hallucination risk must be at most 0.20. "
    "The default production model is gpt-4o-mini."
)


def test_grounded_answer_scores_high():
    scores = metrics.custom_scores(
        "What is the minimum groundedness?",
        "Groundedness must be at least 0.80.",
        CONTEXT,
    )
    assert scores.groundedness >= 0.8
    assert scores.hallucination_risk <= 0.2


def test_hallucinated_answer_scores_low_groundedness():
    scores = metrics.custom_scores(
        "What is the minimum groundedness?",
        "The minimum is 0.10 and the company CEO is named Zaphod Beeblebrox.",
        CONTEXT,
    )
    # An answer full of unsupported claims should be less grounded and riskier
    # than a grounded one.
    assert scores.groundedness < 0.8
    assert scores.hallucination_risk > 0.0


def test_refusal_is_not_flagged_as_hallucination():
    assert metrics.is_refusal("I don't know based on the provided context.")
    risk = metrics.hallucination_risk_score("I don't know based on the provided context.", CONTEXT)
    assert risk == 0.0


def test_refusal_has_low_relevance():
    # Refusing to answer does not address the question.
    rel = metrics.answer_relevance_score("What is the model?", "I don't know.")
    assert rel <= 0.2


def test_retrieval_quality_reflects_key_term_coverage():
    good = metrics.retrieval_quality_score("What is the default production model?", CONTEXT)
    bad = metrics.retrieval_quality_score(
        "What is the office parking policy?", "Unrelated text about lunch menus."
    )
    assert good > bad
    assert metrics.retrieval_quality_score("anything", "") == 0.0


def test_scores_are_bounded():
    scores = metrics.custom_scores("q", "a totally unrelated answer", CONTEXT)
    for value in (
        scores.groundedness,
        scores.hallucination_risk,
        scores.answer_relevance,
        scores.retrieval_score,
    ):
        assert 0.0 <= value <= 1.0


def test_score_answer_defaults_to_custom_method():
    scores = metrics.score_answer("q", "a", "c")
    assert scores.method == "custom"
