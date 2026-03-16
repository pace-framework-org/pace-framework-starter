"""Tests for pace/training/exporter.py."""
import json
from pathlib import Path

import pytest

from training.collector import StoryTrace
from training.exporter import (
    _build_sft_messages,
    _serialise_content,
    export_reward_jsonl,
    export_sft_jsonl,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_trace(day=1, gate_pass_rate=1.0, reward_score=0.9, messages=None, system_prompt="SYS"):
    if messages is None:
        messages = [
            {"role": "user", "content": "do the thing"},
            {"role": "assistant", "content": "done"},
        ]
    return StoryTrace(
        day=day,
        story_md=f"# Story Day {day}\n\nAcceptance: implement feature X.",
        system_prompt=system_prompt,
        messages=messages,
        red_phase_confirmed=True,
        iterations_used=8,
        commit="abc123",
        approach="TDD",
        coverage_delta="+5%",
        tests_added=5,
        forge_cost_usd=0.3,
        gate_decision="SHIP",
        gate_pass_rate=gate_pass_rate,
        criteria_results=[],
        reward_score=reward_score,
    )


# ---------------------------------------------------------------------------
# _serialise_content
# ---------------------------------------------------------------------------

def test_serialise_content_string():
    assert _serialise_content("hello") == "hello"


def test_serialise_content_list_text_block():
    content = [{"type": "text", "text": "hello world"}]
    assert _serialise_content(content) == "hello world"


def test_serialise_content_list_tool_use():
    content = [{"type": "tool_use", "name": "write_file", "input": {"path": "foo.py"}}]
    result = _serialise_content(content)
    assert "<tool_use name=write_file>" in result
    assert "foo.py" in result


def test_serialise_content_list_tool_result():
    content = [{"type": "tool_result", "content": "File written."}]
    result = _serialise_content(content)
    assert "<tool_result>" in result
    assert "File written." in result


def test_serialise_content_list_unknown_block():
    content = [{"type": "image", "data": "base64..."}]
    result = _serialise_content(content)
    assert "image" in result


def test_serialise_content_list_mixed():
    content = [
        {"type": "text", "text": "first"},
        {"type": "tool_use", "name": "bash", "input": {"cmd": "ls"}},
        {"type": "text", "text": "second"},
    ]
    result = _serialise_content(content)
    assert "first" in result
    assert "bash" in result
    assert "second" in result


def test_serialise_content_list_non_dict_element():
    content = ["plain string item"]
    result = _serialise_content(content)
    assert "plain string item" in result


def test_serialise_content_other_type():
    assert _serialise_content(42) == "42"


# ---------------------------------------------------------------------------
# _build_sft_messages
# ---------------------------------------------------------------------------

def test_build_sft_messages_empty():
    trace = _make_trace(messages=[])
    assert _build_sft_messages(trace) == []


def test_build_sft_messages_replaces_first_user_turn():
    trace = _make_trace()
    msgs = _build_sft_messages(trace)
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == trace.story_md.strip()


def test_build_sft_messages_keeps_subsequent_turns():
    messages = [
        {"role": "user", "content": "original preamble"},
        {"role": "assistant", "content": "assistant reply"},
        {"role": "user", "content": "tool result"},
    ]
    trace = _make_trace(messages=messages)
    msgs = _build_sft_messages(trace)
    assert len(msgs) == 3
    assert msgs[1]["content"] == "assistant reply"
    assert msgs[2]["content"] == "tool result"


def test_build_sft_messages_first_non_user_turn_kept():
    messages = [
        {"role": "assistant", "content": "assistant first"},
        {"role": "user", "content": "user follow-up"},
    ]
    trace = _make_trace(messages=messages)
    msgs = _build_sft_messages(trace)
    # First message is not user — kept as-is
    assert msgs[0]["content"] == "assistant first"


# ---------------------------------------------------------------------------
# export_sft_jsonl
# ---------------------------------------------------------------------------

def test_export_sft_jsonl_writes_lines(tmp_path):
    traces = [_make_trace(day=1), _make_trace(day=2)]
    out = tmp_path / "sft.jsonl"
    count = export_sft_jsonl(traces, out)
    assert count == 2
    lines = out.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert "messages" in record


def test_export_sft_jsonl_includes_system(tmp_path):
    trace = _make_trace(system_prompt="MY SYSTEM PROMPT")
    out = tmp_path / "sft.jsonl"
    export_sft_jsonl([trace], out)
    record = json.loads(out.read_text())
    assert record["system"] == "MY SYSTEM PROMPT"


def test_export_sft_jsonl_no_system_when_empty(tmp_path):
    trace = _make_trace(system_prompt="")
    out = tmp_path / "sft.jsonl"
    export_sft_jsonl([trace], out)
    record = json.loads(out.read_text())
    assert "system" not in record


def test_export_sft_jsonl_append(tmp_path):
    out = tmp_path / "sft.jsonl"
    export_sft_jsonl([_make_trace(day=1)], out, append=True)
    export_sft_jsonl([_make_trace(day=2)], out, append=True)
    lines = out.read_text().splitlines()
    assert len(lines) == 2


def test_export_sft_jsonl_overwrite(tmp_path):
    out = tmp_path / "sft.jsonl"
    export_sft_jsonl([_make_trace(day=1), _make_trace(day=2)], out, append=False)
    export_sft_jsonl([_make_trace(day=3)], out, append=False)
    lines = out.read_text().splitlines()
    assert len(lines) == 1


def test_export_sft_jsonl_skips_empty_messages(tmp_path):
    trace = _make_trace(messages=[])
    out = tmp_path / "sft.jsonl"
    count = export_sft_jsonl([trace], out)
    assert count == 0
    assert out.read_text() == ""


def test_export_sft_jsonl_creates_parent_dirs(tmp_path):
    out = tmp_path / "deep" / "nested" / "sft.jsonl"
    export_sft_jsonl([_make_trace()], out)
    assert out.exists()


# ---------------------------------------------------------------------------
# export_reward_jsonl
# ---------------------------------------------------------------------------

def test_export_reward_jsonl_writes_lines(tmp_path):
    traces = [_make_trace(day=1, reward_score=0.85), _make_trace(day=2, reward_score=0.7)]
    out = tmp_path / "reward.jsonl"
    count = export_reward_jsonl(traces, out)
    assert count == 2
    lines = out.read_text().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["reward"] == 0.85
    assert "prompt" in record
    assert "completion" in record
    assert "metadata" in record


def test_export_reward_jsonl_metadata_fields(tmp_path):
    trace = _make_trace(day=5, gate_pass_rate=0.9, reward_score=0.8)
    out = tmp_path / "reward.jsonl"
    export_reward_jsonl([trace], out)
    record = json.loads(out.read_text())
    meta = record["metadata"]
    assert meta["day"] == 5
    assert meta["gate_pass_rate"] == 0.9
    assert "iterations_used" in meta
    assert "forge_cost_usd" in meta


def test_export_reward_jsonl_prompt_contains_system(tmp_path):
    trace = _make_trace(system_prompt="SYS PROMPT")
    out = tmp_path / "reward.jsonl"
    export_reward_jsonl([trace], out)
    record = json.loads(out.read_text())
    assert "SYS PROMPT" in record["prompt"]
    assert trace.story_md.strip() in record["prompt"]


def test_export_reward_jsonl_skips_empty_messages(tmp_path):
    trace = _make_trace(messages=[])
    out = tmp_path / "reward.jsonl"
    count = export_reward_jsonl([trace], out)
    assert count == 0


def test_export_reward_jsonl_append(tmp_path):
    out = tmp_path / "reward.jsonl"
    export_reward_jsonl([_make_trace(day=1)], out, append=True)
    export_reward_jsonl([_make_trace(day=2)], out, append=True)
    lines = out.read_text().splitlines()
    assert len(lines) == 2


def test_export_reward_jsonl_completion_skips_first_user_msg(tmp_path):
    messages = [
        {"role": "user", "content": "FIRST"},
        {"role": "assistant", "content": "SECOND"},
    ]
    trace = _make_trace(messages=messages)
    out = tmp_path / "reward.jsonl"
    export_reward_jsonl([trace], out)
    record = json.loads(out.read_text())
    assert "FIRST" not in record["completion"]
    assert "SECOND" in record["completion"]
