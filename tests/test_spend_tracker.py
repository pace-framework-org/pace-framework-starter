"""Tests for pace/spend_tracker.py."""
import pytest
import spend_tracker


@pytest.fixture(autouse=True)
def reset_records():
    """Clear spend_tracker state before each test."""
    spend_tracker._records.clear()
    yield
    spend_tracker._records.clear()


# ---------------------------------------------------------------------------
# install()
# ---------------------------------------------------------------------------

def test_install_is_noop():
    spend_tracker.install()  # must not raise


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------

def test_record_appends_entry():
    spend_tracker.record("claude-sonnet-4-6", 1000, 200)
    assert len(spend_tracker._records) == 1
    assert spend_tracker._records[0] == {"model": "claude-sonnet-4-6", "in": 1000, "out": 200}


def test_record_multiple():
    spend_tracker.record("claude-sonnet-4-6", 1000, 200)
    spend_tracker.record("claude-haiku-4-5-20251001", 500, 100)
    assert len(spend_tracker._records) == 2


# ---------------------------------------------------------------------------
# total_usd()
# ---------------------------------------------------------------------------

def test_total_usd_empty():
    assert spend_tracker.total_usd() == 0.0


def test_total_usd_sonnet():
    # sonnet: $3.00/M in, $15.00/M out
    spend_tracker.record("claude-sonnet-4-6", 1_000_000, 1_000_000)
    cost = spend_tracker.total_usd()
    assert abs(cost - 18.0) < 0.001


def test_total_usd_haiku():
    # haiku: $0.80/M in, $4.00/M out
    spend_tracker.record("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    cost = spend_tracker.total_usd()
    assert abs(cost - 4.80) < 0.001


def test_total_usd_opus():
    # opus: $15.00/M in, $75.00/M out
    spend_tracker.record("claude-opus-4-6", 1_000_000, 1_000_000)
    cost = spend_tracker.total_usd()
    assert abs(cost - 90.0) < 0.001


def test_total_usd_unknown_model_uses_fallback():
    # unknown model uses sonnet fallback rate
    spend_tracker.record("unknown-model-xyz", 1_000_000, 1_000_000)
    cost = spend_tracker.total_usd()
    assert abs(cost - 18.0) < 0.001  # sonnet fallback


def test_total_usd_model_with_provider_prefix():
    # provider/model → strip prefix for lookup
    spend_tracker.record("anthropic/claude-sonnet-4-6", 1_000_000, 0)
    cost = spend_tracker.total_usd()
    assert abs(cost - 3.0) < 0.001


def test_total_usd_accumulates():
    spend_tracker.record("claude-sonnet-4-6", 500_000, 0)
    spend_tracker.record("claude-sonnet-4-6", 500_000, 0)
    cost = spend_tracker.total_usd()
    assert abs(cost - 3.0) < 0.001  # 1M in total at $3/M


# ---------------------------------------------------------------------------
# session_total()
# ---------------------------------------------------------------------------

def test_session_total_empty():
    assert spend_tracker.session_total() == (0, 0)


def test_session_total_sums_tokens():
    spend_tracker.record("claude-sonnet-4-6", 100, 50)
    spend_tracker.record("claude-haiku-4-5-20251001", 200, 75)
    total_in, total_out = spend_tracker.session_total()
    assert total_in == 300
    assert total_out == 125


# ---------------------------------------------------------------------------
# call_exceeds_limit()
# ---------------------------------------------------------------------------

class MockLimits:
    forge_input_tokens = 160_000
    forge_output_tokens = 16_384
    analysis_input_tokens = 80_000
    analysis_output_tokens = 8_192


def test_call_exceeds_limit_no_limits():
    assert spend_tracker.call_exceeds_limit("forge", 999_999, 999_999, limits=None) is False


def test_call_exceeds_limit_forge_within():
    assert spend_tracker.call_exceeds_limit("forge", 100_000, 10_000, limits=MockLimits()) is False


def test_call_exceeds_limit_forge_input_exceeded():
    assert spend_tracker.call_exceeds_limit("forge", 200_000, 100, limits=MockLimits()) is True


def test_call_exceeds_limit_forge_output_exceeded():
    assert spend_tracker.call_exceeds_limit("forge", 1_000, 20_000, limits=MockLimits()) is True


def test_call_exceeds_limit_analysis_within():
    assert spend_tracker.call_exceeds_limit("analysis", 50_000, 5_000, limits=MockLimits()) is False


def test_call_exceeds_limit_analysis_exceeded():
    assert spend_tracker.call_exceeds_limit("analysis", 100_000, 100, limits=MockLimits()) is True


def test_call_exceeds_limit_analysis_case_insensitive():
    assert spend_tracker.call_exceeds_limit("ANALYSIS", 100_000, 100, limits=MockLimits()) is True


def test_call_exceeds_limit_unknown_class_returns_false():
    assert spend_tracker.call_exceeds_limit("scribe", 999_999, 999_999, limits=MockLimits()) is False


# ---------------------------------------------------------------------------
# summary()
# ---------------------------------------------------------------------------

def test_summary_empty():
    result = spend_tracker.summary()
    assert "No API calls" in result


def test_summary_single_model():
    spend_tracker.record("claude-sonnet-4-6", 1_000_000, 1_000_000)
    result = spend_tracker.summary()
    assert "claude-sonnet-4-6" in result
    assert "$" in result
    assert "Run total" in result


def test_summary_multiple_models():
    spend_tracker.record("claude-sonnet-4-6", 500_000, 0)
    spend_tracker.record("claude-haiku-4-5-20251001", 500_000, 0)
    result = spend_tracker.summary()
    assert "claude-sonnet-4-6" in result
    assert "claude-haiku-4-5-20251001" in result
    assert "Run total" in result


def test_summary_aggregates_same_model():
    spend_tracker.record("claude-sonnet-4-6", 100, 50)
    spend_tracker.record("claude-sonnet-4-6", 200, 100)
    result = spend_tracker.summary()
    assert "300" in result  # 100+200 in tokens
    assert "150" in result  # 50+100 out tokens
