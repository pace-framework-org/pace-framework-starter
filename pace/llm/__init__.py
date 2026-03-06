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


def get_llm_adapter() -> LLMAdapter:
    """Instantiate and return the LLMAdapter for the configured provider.

    Provider and model are read from pace.config.yaml → llm section.
    API keys are always read from environment variables.
    """
    from config import load_config
    cfg = load_config()
    llm = cfg.llm

    if llm.provider == "litellm":
        from llm.litellm_adapter import LiteLLMAdapter
        return LiteLLMAdapter(
            model=llm.model,
            base_url=llm.base_url,
            api_key=os.environ.get("LLM_API_KEY"),  # generic override; provider keys auto-picked by litellm
        )

    # Default: anthropic
    from llm.anthropic_adapter import AnthropicAdapter
    return AnthropicAdapter(
        model=llm.model,
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )


__all__ = ["LLMAdapter", "get_llm_adapter"]
