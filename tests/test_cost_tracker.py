"""Tests for token counting and cost estimation."""

from agentops_evalbench.evaluation import cost_tracker


def test_count_tokens_nonzero_for_text():
    assert cost_tracker.count_tokens("hello world foo bar", "gpt-4o-mini") > 0
    assert cost_tracker.count_tokens("", "gpt-4o-mini") == 0


def test_estimate_cost_scales_with_model():
    usage = {"prompt": 1000, "completion": 500, "total": 1500}
    cheap = cost_tracker.estimate_cost(usage, "gpt-4o-mini")
    pricey = cost_tracker.estimate_cost(usage, "gpt-4o")
    assert pricey > cheap > 0


def test_estimate_cost_handles_empty_usage():
    assert cost_tracker.estimate_cost(None, "gpt-4o-mini") == 0.0
    assert cost_tracker.estimate_cost({}, "gpt-4o-mini") == 0.0


def test_model_name_normalization_strips_offline_suffix():
    usage = {"prompt": 1000, "completion": 500, "total": 1500}
    normal = cost_tracker.estimate_cost(usage, "gpt-4o-mini")
    suffixed = cost_tracker.estimate_cost(usage, "gpt-4o-mini (offline-extractive)")
    assert normal == suffixed


def test_unknown_model_uses_fallback_pricing():
    usage = {"prompt": 1000, "completion": 1000, "total": 2000}
    assert cost_tracker.estimate_cost(usage, "some-unknown-model") > 0


def test_build_token_usage_totals():
    usage = cost_tracker.build_token_usage("a b c", "one two", "gpt-4o-mini")
    assert usage["total"] == usage["prompt"] + usage["completion"]
