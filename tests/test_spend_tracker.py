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
    assert spend_tracker._records[0] == {
        "model": "claude-sonnet-4-6",
        "in": 1000,
        "out": 200,
        "cache_read": 0,
        "cache_create": 0,
    }


def test_record_multiple():
    spend_tracker.record("claude-sonnet-4-6", 1000, 200)
    spend_tracker.record("claude-haiku-4-5-20251001", 500, 100)
    assert len(spend_tracker._records) == 2


def test_record_with_cache_read_stored():
    spend_tracker.record("claude-sonnet-4-6", 100, 50, cache_read=500)
    r = spend_tracker._records[0]
    assert r["cache_read"] == 500
    assert r["cache_create"] == 0


def test_record_with_cache_create_stored():
    spend_tracker.record("claude-sonnet-4-6", 100, 50, cache_create=800)
    r = spend_tracker._records[0]
    assert r["cache_read"] == 0
    assert r["cache_create"] == 800


def test_record_with_both_cache_fields_stored():
    spend_tracker.record("claude-sonnet-4-6", 100, 50, cache_read=300, cache_create=700)
    r = spend_tracker._records[0]
    assert r["cache_read"] == 300
    assert r["cache_create"] == 700


def test_record_default_cache_args_zero():
    """Old callers that omit cache args get 0 defaults — backwards compatible."""
    spend_tracker.record("claude-sonnet-4-6", 1000, 200)
    r = spend_tracker._records[0]
    assert r["cache_read"] == 0
    assert r["cache_create"] == 0


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


def test_total_usd_cache_read_priced_at_10_percent():
    # sonnet input rate: $3.00/M → cache_read rate: $0.30/M
    # 1M cache_read tokens → $0.30
    spend_tracker.record("claude-sonnet-4-6", 0, 0, cache_read=1_000_000)
    cost = spend_tracker.total_usd()
    assert abs(cost - 0.30) < 0.0001


def test_total_usd_cache_create_priced_at_125_percent():
    # sonnet input rate: $3.00/M → cache_create rate: $3.75/M
    # 1M cache_create tokens → $3.75
    spend_tracker.record("claude-sonnet-4-6", 0, 0, cache_create=1_000_000)
    cost = spend_tracker.total_usd()
    assert abs(cost - 3.75) < 0.0001


def test_total_usd_combined_cache_and_normal_tokens():
    # sonnet: 500k in ($1.50) + 200k out ($3.00) + 300k cache_read ($0.09) + 100k cache_create ($0.375)
    spend_tracker.record(
        "claude-sonnet-4-6", 500_000, 200_000,
        cache_read=300_000, cache_create=100_000,
    )
    cost = spend_tracker.total_usd()
    expected = (500_000 / 1e6 * 3.0) + (200_000 / 1e6 * 15.0) + (300_000 / 1e6 * 3.0 * 0.10) + (100_000 / 1e6 * 3.0 * 1.25)
    assert abs(cost - expected) < 0.0001


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


def test_summary_includes_cache_columns_when_cache_tokens_exist():
    spend_tracker.record("claude-sonnet-4-6", 100, 50, cache_read=500, cache_create=200)
    result = spend_tracker.summary()
    assert "cache_read" in result
    assert "cache_create" in result
    assert "500" in result
    assert "200" in result


def test_summary_omits_cache_columns_when_all_zero():
    """Backwards-compat: no cache columns when no cache tokens recorded."""
    spend_tracker.record("claude-sonnet-4-6", 1_000, 500)
    result = spend_tracker.summary()
    assert "cache_read" not in result
    assert "cache_create" not in result


def test_summary_shows_cache_columns_when_any_record_has_cache():
    """Cache columns appear even if only one of multiple records has cache data."""
    spend_tracker.record("claude-sonnet-4-6", 1_000, 500)
    spend_tracker.record("claude-sonnet-4-6", 2_000, 100, cache_read=8_000)
    result = spend_tracker.summary()
    assert "cache_read" in result


# ---------------------------------------------------------------------------
# cache_stats()
# ---------------------------------------------------------------------------

def test_cache_stats_empty():
    stats = spend_tracker.cache_stats()
    assert stats == {"cache_read_tokens": 0, "cache_create_tokens": 0, "cache_savings_usd": 0.0}


def test_cache_stats_structure():
    spend_tracker.record("claude-sonnet-4-6", 100, 50, cache_read=1000, cache_create=500)
    stats = spend_tracker.cache_stats()
    assert "cache_read_tokens" in stats
    assert "cache_create_tokens" in stats
    assert "cache_savings_usd" in stats


def test_cache_stats_correct_token_counts():
    spend_tracker.record("claude-sonnet-4-6", 0, 0, cache_read=300, cache_create=700)
    spend_tracker.record("claude-sonnet-4-6", 0, 0, cache_read=200, cache_create=100)
    stats = spend_tracker.cache_stats()
    assert stats["cache_read_tokens"] == 500
    assert stats["cache_create_tokens"] == 800


def test_cache_stats_savings_usd_sonnet():
    # sonnet input rate: $3.00/M
    # 1M cache_read tokens → saving = 90% of $3.00/M = $2.70
    spend_tracker.record("claude-sonnet-4-6", 0, 0, cache_read=1_000_000)
    stats = spend_tracker.cache_stats()
    assert abs(stats["cache_savings_usd"] - 2.70) < 0.0001


def test_cache_stats_savings_usd_haiku():
    # haiku input rate: $0.80/M
    # 1M cache_read tokens → saving = 90% of $0.80/M = $0.72
    spend_tracker.record("claude-haiku-4-5-20251001", 0, 0, cache_read=1_000_000)
    stats = spend_tracker.cache_stats()
    assert abs(stats["cache_savings_usd"] - 0.72) < 0.0001


def test_cache_stats_savings_usd_no_cache_read():
    # cache_create tokens do not contribute to savings
    spend_tracker.record("claude-sonnet-4-6", 0, 0, cache_create=1_000_000)
    stats = spend_tracker.cache_stats()
    assert stats["cache_savings_usd"] == 0.0


def test_cache_stats_no_cache_activity():
    spend_tracker.record("claude-sonnet-4-6", 500, 100)
    stats = spend_tracker.cache_stats()
    assert stats["cache_read_tokens"] == 0
    assert stats["cache_create_tokens"] == 0
    assert stats["cache_savings_usd"] == 0.0
