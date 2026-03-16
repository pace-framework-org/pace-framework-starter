"""Tests for pace/config.py — config loading and helper functions."""
import os
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

import pytest

import config as config_mod
from config import (
    CronConfig,
    LLMLimitsConfig,
    LLMConfig,
    PaceConfig,
    SourceDir,
    TechConfig,
    _interpolate_env,
    load_config,
)


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Clear lru_cache on load_config between tests."""
    load_config.cache_clear()
    yield
    load_config.cache_clear()


# ---------------------------------------------------------------------------
# _interpolate_env
# ---------------------------------------------------------------------------

def test_interpolate_env_no_vars():
    assert _interpolate_env("hello world") == "hello world"


def test_interpolate_env_replaces_known_var(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "secret123")
    assert _interpolate_env("token=${MY_TOKEN}") == "token=secret123"


def test_interpolate_env_unknown_var_unchanged():
    # Remove env var if present
    os.environ.pop("UNKNOWN_VAR_XYZ", None)
    result = _interpolate_env("${UNKNOWN_VAR_XYZ}")
    assert result == "${UNKNOWN_VAR_XYZ}"


def test_interpolate_env_non_string_passthrough():
    assert _interpolate_env(42) == 42


def test_interpolate_env_multiple_vars(monkeypatch):
    monkeypatch.setenv("HOST", "localhost")
    monkeypatch.setenv("PORT", "5432")
    result = _interpolate_env("${HOST}:${PORT}")
    assert result == "localhost:5432"


# ---------------------------------------------------------------------------
# LLMLimitsConfig defaults
# ---------------------------------------------------------------------------

def test_llm_limits_defaults():
    limits = LLMLimitsConfig()
    assert limits.forge_input_tokens == 160_000
    assert limits.forge_output_tokens == 16_384
    assert limits.analysis_input_tokens == 80_000
    assert limits.analysis_output_tokens == 8_192


def test_llm_limits_custom():
    limits = LLMLimitsConfig(
        forge_input_tokens=200_000,
        forge_output_tokens=32_768,
        analysis_input_tokens=50_000,
        analysis_output_tokens=4_096,
    )
    assert limits.forge_input_tokens == 200_000


# ---------------------------------------------------------------------------
# LLMConfig post_init
# ---------------------------------------------------------------------------

def test_llm_config_creates_default_limits():
    llm = LLMConfig(provider="anthropic", model="claude-sonnet-4-6",
                    analysis_model="claude-haiku-4-5-20251001", base_url=None)
    assert llm.limits is not None
    assert isinstance(llm.limits, LLMLimitsConfig)


# ---------------------------------------------------------------------------
# CronConfig defaults
# ---------------------------------------------------------------------------

def test_cron_config_defaults():
    cron = CronConfig()
    assert cron.pace_pipeline == "0 9 * * 1-5"
    assert cron.planner_pipeline == "0 8 * * 1"
    assert cron.update_check == "0 0 * * *"
    assert cron.timezone == "UTC"


# ---------------------------------------------------------------------------
# load_config() with real pace.config.yaml
# ---------------------------------------------------------------------------

def test_load_config_returns_pace_config():
    cfg = load_config()
    assert isinstance(cfg, PaceConfig)


def test_load_config_has_product_name():
    cfg = load_config()
    assert isinstance(cfg.product_name, str)
    assert len(cfg.product_name) > 0


def test_load_config_has_cron():
    cfg = load_config()
    assert cfg.cron is not None
    assert isinstance(cfg.cron, CronConfig)


def test_load_config_has_llm():
    cfg = load_config()
    assert cfg.llm is not None
    assert cfg.llm.model


def test_load_config_has_training():
    cfg = load_config()
    assert cfg.training is not None
    assert isinstance(cfg.training.export_on_ship, bool)


def test_load_config_ci_type_valid():
    cfg = load_config()
    valid_types = {"github", "gitlab", "bitbucket", "jenkins", "local"}
    assert cfg.ci_type in valid_types


def test_load_config_tracker_type_valid():
    cfg = load_config()
    valid_types = {"github", "gitlab", "bitbucket", "jira", "local"}
    assert cfg.tracker_type in valid_types


def test_load_config_is_cached():
    cfg1 = load_config()
    cfg2 = load_config()
    assert cfg1 is cfg2  # same object from lru_cache


def test_load_config_source_dirs():
    cfg = load_config()
    assert isinstance(cfg.source_dirs, list)


def test_load_config_sprint_duration():
    cfg = load_config()
    assert cfg.sprint_duration_days > 0


def test_load_config_llm_limits():
    cfg = load_config()
    assert cfg.llm.limits.forge_input_tokens > 0
