"""PACE LLM Factory.

Call get_llm_adapter() to get the configured LLMAdapter instance.
The provider is selected from pace.config.yaml (llm.provider) and the
API key is read from environment variables.

Supported providers:
    anthropic  — Anthropic Claude (default); requires ANTHROPIC_API_KEY
    litellm    — Any provider via LiteLLM; requires the provider's own API key

LiteLLM model prefixes (set in llm.model):
    openai/gpt-4o
    gemini/gemini-2.0-flash
    bedrock/anthropic.claude-sonnet-4-6
    azure/gpt-4o
    ollama/llama3.1
    groq/llama-3.1-70b-versatile
    mistral/mistral-large-latest
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.base import LLMAdapter


def get_llm_adapter(model: str | None = None) -> LLMAdapter:
    """Instantiate and return the LLMAdapter for the configured provider.

    Provider and model are read from pace.config.yaml → llm section.
    API keys are always read from environment variables.

    Args:
        model: Optional model override. If None, uses llm.model from config.
    """
    from config import load_config
    cfg = load_config()
    llm = cfg.llm
    resolved_model = model or llm.model

    if llm.provider == "litellm":
        from llm.litellm_adapter import LiteLLMAdapter
        return LiteLLMAdapter(
            model=resolved_model,
            base_url=llm.base_url,
            api_key=os.environ.get("LLM_API_KEY"),  # generic override; provider keys auto-picked by litellm
        )

    # Default: anthropic
    from llm.anthropic_adapter import AnthropicAdapter
    return AnthropicAdapter(
        model=resolved_model,
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )


def get_analysis_adapter() -> LLMAdapter:
    """Return an adapter using the analysis_model (PRIME/GATE/SENTINEL/CONDUIT).

    Falls back to the main model if analysis_model is not explicitly configured.
    """
    from config import load_config
    cfg = load_config()
    return get_llm_adapter(model=cfg.llm.analysis_model)


__all__ = ["LLMAdapter", "get_llm_adapter", "get_analysis_adapter"]
