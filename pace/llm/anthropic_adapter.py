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


def _compact_user_message(user: str) -> str:
    """Truncate a user message to ~60 % of its length with a truncation notice.

    Used as a fallback when the full prompt exceeds the model's context window.
    """
    cutoff = max(200, int(len(user) * 0.60))
    return (
        user[:cutoff]
        + "\n\n[Note: Input was truncated to fit the context window. "
        "Focus on the core requirements above and produce a complete response.]"
    )


class AnthropicAdapter(LLMAdapter):
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Simple completion
    # ------------------------------------------------------------------

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """Single-turn completion with one retry on context-length errors.

        Item 3 deferred step 6: when the Anthropic API rejects the request
        because the prompt exceeds the context window, compact the user
        message to ~60 % of its original length and retry once.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            spend_tracker.record(response.model, response.usage.input_tokens, response.usage.output_tokens)
            return response.content[0].text
        except anthropic.BadRequestError as exc:
            err_str = str(exc).lower()
            if "prompt is too long" in err_str or "context_length" in err_str or "too many tokens" in err_str:
                compact_user = _compact_user_message(user)
                print(
                    f"[PACE][LLM] Token limit hit — retrying with compacted input "
                    f"({len(user)} → {len(compact_user)} chars)"
                )
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": compact_user}],
                )
                spend_tracker.record(response.model, response.usage.input_tokens, response.usage.output_tokens)
                return response.content[0].text
            raise

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
        # Wrap the system prompt in Anthropic's prompt-caching format. The system
        # prompt is identical on every iteration of the agentic loop, so caching
        # its KV state reduces repeated input-token cost by ~90% for iterations 2+.
        system_param: str | list = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens,
            system=system_param,
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
