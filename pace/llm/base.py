"""PACE LLM Adapter — abstract base class.

All LLM provider integrations (Anthropic, LiteLLM) implement this interface.
Agents only call methods defined here; they never import provider SDKs directly.

Two call patterns are supported:

  complete(system, user)
      Single-turn completion for non-agentic agents (PRIME, GATE, SENTINEL, CONDUIT).
      Returns the raw text response.

  chat(system, messages, tools)
      Single model call for use inside an agentic tool loop (FORGE, SCRIBE).
      Returns a ChatResponse that agents use to drive the next loop iteration.

Message format convention
--------------------------
PACE uses Anthropic's message structure internally:

  User message (plain):
    {"role": "user", "content": "text"}

  Assistant message with optional tool calls:
    {"role": "assistant", "content": [
        {"type": "text", "text": "..."},                   # optional
        {"type": "tool_use", "id": "id", "name": "tool",
         "input": {...}},                                  # one per tool call
    ]}

  Tool results (appended after assistant calls tools):
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "id", "content": "result"},
    ]}

Adapters are responsible for converting this format to/from their provider's
native wire format before making the API call.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A single tool call returned by the model."""
    id: str
    name: str
    input: dict


@dataclass
class ChatResponse:
    """Normalized response from a single model call.

    stop_reason values:
        "end_turn"   — model finished naturally; no further tool calls expected
        "tool_use"   — model wants to call one or more tools
        "max_tokens" — hit the token limit mid-response
    """
    stop_reason: str
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def to_assistant_message(self) -> dict:
        """Return an assistant message dict in Anthropic format.

        Agents append the result of this method to their message history
        after each model call, before appending tool results.
        """
        content: list[dict] = []
        if self.text:
            content.append({"type": "text", "text": self.text})
        for call in self.tool_calls:
            content.append({
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": call.input,
            })
        return {"role": "assistant", "content": content}


class LLMAdapter(ABC):
    """Abstract interface for all PACE LLM provider integrations.

    Two methods are required:
      complete  — single-turn text completion (non-agentic agents)
      chat      — one model call with optional tools (agentic loop agents)
    """

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> str:
        """Single-turn completion.

        Args:
            system:     System prompt.
            user:       User message content.
            max_tokens: Maximum tokens to generate.

        Returns:
            The model's text response as a plain string.
        """

    @abstractmethod
    def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
    ) -> ChatResponse:
        """One model API call for use inside an agentic tool loop.

        Args:
            system:     System prompt.
            messages:   Conversation history in Anthropic message format.
            tools:      Tool definitions in Anthropic input_schema format.
            max_tokens: Maximum tokens to generate.

        Returns:
            ChatResponse with stop_reason, optional text, and tool_calls list.
            Agents call response.to_assistant_message() to get the dict to
            append to their message history.
        """
