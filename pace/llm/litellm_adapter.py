"""PACE LiteLLM Adapter.

Wraps LiteLLM to provide access to 100+ LLM providers through a single interface.
LiteLLM uses OpenAI's message format; this adapter converts PACE's internal
Anthropic-format messages to/from OpenAI format transparently.

Required environment variable:
    Set the appropriate key for your chosen provider (see below).

Model format for pace.config.yaml → llm.model:
    openai/gpt-4o                     OpenAI GPT-4o
    openai/o3-mini                    OpenAI o3-mini
    anthropic/claude-sonnet-4-6       Anthropic via LiteLLM (uses ANTHROPIC_API_KEY)
    gemini/gemini-2.0-flash           Google Gemini
    bedrock/anthropic.claude-sonnet-4-6   AWS Bedrock (uses AWS credentials)
    azure/gpt-4o                      Azure OpenAI (uses AZURE_* env vars)
    ollama/llama3.1                   Local Ollama instance
    groq/llama-3.1-70b-versatile      Groq (fast inference)
    mistral/mistral-large-latest      Mistral AI

Provider environment variables:
    OpenAI:          OPENAI_API_KEY
    Google Gemini:   GEMINI_API_KEY
    AWS Bedrock:     AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION_NAME
    Azure OpenAI:    AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION
    Groq:            GROQ_API_KEY
    Mistral:         MISTRAL_API_KEY
    Ollama:          Set llm.base_url to your Ollama URL (default: http://localhost:11434)

Tool calling:
    LiteLLM normalises tool calling across providers. PACE tools defined in
    Anthropic's input_schema format are converted to OpenAI function format
    before the API call, and responses are converted back.

See https://docs.litellm.ai/docs/providers for the full provider list.
"""

from __future__ import annotations

import json
import uuid

try:
    import litellm
    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False

from llm.base import ChatResponse, LLMAdapter, ToolCall


class LiteLLMAdapter(LLMAdapter):
    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None) -> None:
        if not _LITELLM_AVAILABLE:
            raise ImportError("litellm not installed. Run: pip install litellm")
        self._model = model
        self._base_url = base_url
        self._api_key = api_key

    def _call_kwargs(self) -> dict:
        kwargs = {}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._api_key:
            kwargs["api_key"] = self._api_key
        return kwargs

    # ------------------------------------------------------------------
    # Simple completion
    # ------------------------------------------------------------------

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        response = litellm.completion(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            **self._call_kwargs(),
        )
        return response.choices[0].message.content or ""

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
        oai_messages = _pace_messages_to_openai(messages, system)
        oai_tools = _anthropic_tools_to_openai(tools) if tools else None

        kwargs = dict(
            model=self._model,
            messages=oai_messages,
            max_tokens=max_tokens,
            **self._call_kwargs(),
        )
        if oai_tools:
            kwargs["tools"] = oai_tools

        response = litellm.completion(**kwargs)
        return _openai_response_to_pace(response)


# ---------------------------------------------------------------------------
# Format conversion helpers
# ---------------------------------------------------------------------------

def _anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to OpenAI function format."""
    result = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return result


def _pace_messages_to_openai(messages: list[dict], system: str) -> list[dict]:
    """Convert PACE/Anthropic-format message history to OpenAI format.

    PACE message types handled:
      - Plain user message:  {"role": "user", "content": "text"}
      - Assistant with tool_use blocks in content list
      - Tool results: {"role": "user", "content": [{"type": "tool_result", ...}]}
    """
    oai: list[dict] = [{"role": "system", "content": system}]

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        # Plain string content
        if isinstance(content, str):
            oai.append({"role": role, "content": content})
            continue

        # List content — inspect first block to determine type
        if not isinstance(content, list):
            oai.append({"role": role, "content": str(content)})
            continue

        # Tool result message — becomes multiple role:"tool" messages
        if role == "user" and content and _is_tool_result_block(content[0]):
            for block in content:
                block_content = block.get("content", "")
                if isinstance(block_content, list):
                    block_content = " ".join(
                        b.get("text", "") if isinstance(b, dict) else str(b)
                        for b in block_content
                    )
                oai.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id", ""),
                    "content": str(block_content),
                })
            continue

        # Assistant message with possible text + tool_use blocks
        if role == "assistant":
            oai.extend(_assistant_blocks_to_openai(content))
            continue

        # Fallback: extract any text blocks
        text = _extract_text(content)
        oai.append({"role": role, "content": text})

    return oai


def _is_tool_result_block(block) -> bool:
    if isinstance(block, dict):
        return block.get("type") == "tool_result"
    return getattr(block, "type", None) == "tool_result"


def _assistant_blocks_to_openai(content: list) -> list[dict]:
    """Convert an assistant message's content blocks to OpenAI format.

    May produce one assistant message (with optional tool_calls).
    """
    text_parts: list[str] = []
    tool_calls: list[dict] = []

    for block in content:
        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)

        if btype == "text":
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
            if text:
                text_parts.append(text)

        elif btype == "tool_use":
            if isinstance(block, dict):
                bid, bname, binput = block.get("id", ""), block.get("name", ""), block.get("input", {})
            else:
                bid = getattr(block, "id", str(uuid.uuid4()))
                bname = getattr(block, "name", "")
                binput = dict(getattr(block, "input", {}))

            tool_calls.append({
                "id": bid,
                "type": "function",
                "function": {
                    "name": bname,
                    "arguments": json.dumps(binput),
                },
            })

    msg: dict = {"role": "assistant", "content": " ".join(text_parts) or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return [msg]


def _extract_text(content: list) -> str:
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif hasattr(block, "type") and block.type == "text":
            parts.append(getattr(block, "text", ""))
    return " ".join(parts)


def _openai_response_to_pace(response) -> ChatResponse:
    """Convert an OpenAI/LiteLLM completion response to a PACE ChatResponse."""
    choice = response.choices[0]
    message = choice.message
    finish_reason = choice.finish_reason or "stop"

    text: str | None = message.content or None
    tool_calls: list[ToolCall] = []

    if getattr(message, "tool_calls", None):
        for tc in message.tool_calls:
            try:
                input_dict = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                input_dict = {}
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                input=input_dict,
            ))

    # Normalise finish_reason to PACE stop_reason vocabulary
    if finish_reason == "tool_calls" or tool_calls:
        stop_reason = "tool_use"
    elif finish_reason == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    return ChatResponse(stop_reason=stop_reason, text=text, tool_calls=tool_calls)
