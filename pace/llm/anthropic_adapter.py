"""PACE Anthropic LLM Adapter.

Wraps the Anthropic Python SDK. This is the default adapter.

Required environment variable:
    ANTHROPIC_API_KEY — your Anthropic API key

Model IDs (set in pace.config.yaml → llm.model):
    claude-sonnet-4-6      — default; strong reasoning, fast
    claude-opus-4-6        — most capable; slower and more expensive
    claude-haiku-4-5-20251001  — fastest and cheapest; lighter tasks
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
import spend_tracker

from llm.base import ChatResponse, LLMAdapter, ToolCall


class AnthropicAdapter(LLMAdapter):
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Simple completion
    # ------------------------------------------------------------------

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        spend_tracker.record(response.model, response.usage.input_tokens, response.usage.output_tokens)
        return response.content[0].text

    # ------------------------------------------------------------------
    # Agentic chat (one step in the tool loop)
    # ------------------------------------------------------------------

    def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
    ) -> ChatResponse:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)
        spend_tracker.record(response.model, response.usage.input_tokens, response.usage.output_tokens)

        text: str | None = None
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    input=dict(block.input),
                ))

        return ChatResponse(
            stop_reason=response.stop_reason or ("tool_use" if tool_calls else "end_turn"),
            text=text,
            tool_calls=tool_calls,
        )
