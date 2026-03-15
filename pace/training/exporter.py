"""PACE Training Data Exporter.

Serialises StoryTrace instances to JSONL files in two formats:

SFT (Supervised Fine-Tuning)
    Anthropic fine-tuning format.  Each line is a JSON object:
        {
            "system": "<FORGE system prompt>",
            "messages": [
                {"role": "user",      "content": "<story card text>"},
                {"role": "assistant", "content": [...]},
                ...
            ]
        }
    The first user turn is replaced with the story.md text so the model
    learns to produce the correct tool-call sequence from a story card.

Reward (RLHF reward-model training)
    Each line is a JSON object:
        {
            "prompt":     "<system>\n\n<story card>",
            "completion": "<serialised FORGE trace>",
            "reward":     0.87
        }
    where `reward` is the pre-computed StoryTrace.reward_score ∈ [0.0, 1.0].

Usage:
    from training.exporter import export_sft_jsonl, export_reward_jsonl
    export_sft_jsonl(traces, Path("sft.jsonl"))
    export_reward_jsonl(traces, Path("reward.jsonl"))
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from training.collector import StoryTrace


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialise_content(content: Any) -> str:
    """Flatten an Anthropic content value to a plain string for reward lines."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"<tool_use name={block.get('name', '')}> {json.dumps(block.get('input', {}))}")
                elif block.get("type") == "tool_result":
                    parts.append(f"<tool_result> {block.get('content', '')}")
                else:
                    parts.append(json.dumps(block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _build_sft_messages(trace: StoryTrace) -> list[dict[str, Any]]:
    """Build the messages list for SFT export.

    The first user turn is overwritten with the story.md text so the model
    sees a clean story card as the initial prompt (matching inference time).
    Subsequent turns are kept verbatim from the FORGE conversation trace.
    """
    if not trace.messages:
        return []

    messages: list[dict[str, Any]] = []
    for i, msg in enumerate(trace.messages):
        if i == 0 and msg.get("role") == "user":
            # Replace FORGE's internal preamble with the plain story card.
            messages.append({"role": "user", "content": trace.story_md.strip()})
        else:
            messages.append(msg)
    return messages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_sft_jsonl(traces: list[StoryTrace], output_path: Path, append: bool = True) -> int:
    """Export traces to a JSONL file in Anthropic SFT format.

    Args:
        traces:      StoryTrace list (typically from collect_all_traces()).
        output_path: Destination file; created if absent.
        append:      When True (default), append to an existing file so that
                     each pipeline run grows the corpus incrementally.

    Returns:
        Number of lines written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    written = 0
    with output_path.open(mode, encoding="utf-8") as fh:
        for trace in traces:
            msgs = _build_sft_messages(trace)
            if not msgs:
                continue
            record: dict[str, Any] = {"messages": msgs}
            if trace.system_prompt:
                record["system"] = trace.system_prompt
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written


def export_reward_jsonl(traces: list[StoryTrace], output_path: Path, append: bool = True) -> int:
    """Export traces to a JSONL file for RLHF reward-model training.

    Each line encodes the (prompt, completion, reward) triple.

    Args:
        traces:      StoryTrace list.
        output_path: Destination file; created if absent.
        append:      Append mode flag (same semantics as export_sft_jsonl).

    Returns:
        Number of lines written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    written = 0
    with output_path.open(mode, encoding="utf-8") as fh:
        for trace in traces:
            if not trace.messages:
                continue

            # Build a compact prompt: system prompt + story card.
            prompt_parts: list[str] = []
            if trace.system_prompt:
                prompt_parts.append(trace.system_prompt.strip())
            prompt_parts.append(trace.story_md.strip())
            prompt = "\n\n".join(prompt_parts)

            # Build completion: serialised FORGE turns (skip the first user msg).
            completion_parts: list[str] = []
            for msg in trace.messages[1:]:
                role = msg.get("role", "")
                content_str = _serialise_content(msg.get("content", ""))
                completion_parts.append(f"[{role}] {content_str}")
            completion = "\n".join(completion_parts)

            record = {
                "prompt": prompt,
                "completion": completion,
                "reward": trace.reward_score,
                "metadata": {
                    "day": trace.day,
                    "gate_pass_rate": trace.gate_pass_rate,
                    "iterations_used": trace.iterations_used,
                    "forge_cost_usd": trace.forge_cost_usd,
                },
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written
