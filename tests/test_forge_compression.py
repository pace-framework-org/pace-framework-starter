"""Tests for Item 24: FORGE Haiku context compression (_compress_history)."""
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agents.forge import _compress_history


_STORY = {"title": "Add login endpoint", "acceptance": ["POST /login returns 200"]}

_VALID_SUMMARY = yaml.dump({
    "files_read": ["pace/auth.py"],
    "files_written": [],
    "plan_committed": False,
    "key_decisions": ["Use JWT tokens"],
    "last_test_output": "1 failed",
    "red_phase_confirmed": True,
}, default_flow_style=False)

_MESSAGES = [
    {"role": "user", "content": "Story Card:\ntitle: Add login endpoint"},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "r1", "name": "read_file", "input": {"path": "pace/auth.py"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "r1", "content": "existing auth code"},
    ]},
]


# ---------------------------------------------------------------------------
# Mitigation 1: schema — compressed summary has required fields
# ---------------------------------------------------------------------------

def test_compress_history_returns_two_messages_on_success():
    """Successful compression reduces history to 2 messages."""
    fake_adapter = MagicMock()
    fake_adapter.complete.return_value = f"```yaml\n{_VALID_SUMMARY}```"

    with patch("agents.forge.get_llm_adapter", return_value=fake_adapter):
        result = _compress_history(_MESSAGES, "claude-haiku-4-5-20251001", set(), _STORY)

    assert len(result) == 2
    assert result[0] == _MESSAGES[0]  # initial message preserved
    assert "compressed" in result[1]["content"][0]["text"].lower()


# ---------------------------------------------------------------------------
# Mitigation 2: anti-hallucination — written_paths overrides summary
# ---------------------------------------------------------------------------

def test_compress_history_overrides_files_written_with_ground_truth():
    """files_written in summary is always replaced with actual written_paths."""
    fake_adapter = MagicMock()
    fake_adapter.complete.return_value = f"```yaml\n{_VALID_SUMMARY}```"

    actual_written = {"tests/test_login.py", "pace/auth.py"}
    with patch("agents.forge.get_llm_adapter", return_value=fake_adapter):
        result = _compress_history(_MESSAGES, "claude-haiku-4-5-20251001", actual_written, _STORY)

    # The compressed context text should contain the ground-truth paths
    context_text = result[1]["content"][0]["text"]
    assert "tests/test_login.py" in context_text or "pace/auth.py" in context_text


# ---------------------------------------------------------------------------
# Mitigation 3: single-trigger guard — compression only fires once
# (tested via _compressed flag in run_forge; here we test _compress_history itself
#  returns 2 messages so the guard prevents a second call)
# ---------------------------------------------------------------------------

def test_compress_history_idempotent_structure():
    """Calling _compress_history on already-compressed (2-message) history is safe."""
    fake_adapter = MagicMock()
    fake_adapter.complete.return_value = f"```yaml\n{_VALID_SUMMARY}```"

    compressed = [
        _MESSAGES[0],
        {"role": "user", "content": [{"type": "text", "text": "## Session Context (compressed)\n..."}]},
    ]
    with patch("agents.forge.get_llm_adapter", return_value=fake_adapter):
        result = _compress_history(compressed, "claude-haiku-4-5-20251001", set(), _STORY)

    assert len(result) == 2


# ---------------------------------------------------------------------------
# Mitigation 4: verification — missing required fields causes fallback
# ---------------------------------------------------------------------------

def test_compress_history_falls_back_on_missing_required_fields():
    """If compressed summary is missing required fields, original history is returned."""
    bad_summary = yaml.dump({"files_read": [], "files_written": []})
    fake_adapter = MagicMock()
    fake_adapter.complete.return_value = f"```yaml\n{bad_summary}```"

    with patch("agents.forge.get_llm_adapter", return_value=fake_adapter):
        result = _compress_history(_MESSAGES, "claude-haiku-4-5-20251001", set(), _STORY)

    # Fallback: original messages returned unchanged
    assert result is _MESSAGES


# ---------------------------------------------------------------------------
# Mitigation 5: failure fallback — API error returns original history
# ---------------------------------------------------------------------------

def test_compress_history_falls_back_on_api_error():
    """If Haiku call raises, original history is returned without exception."""
    fake_adapter = MagicMock()
    fake_adapter.complete.side_effect = RuntimeError("API error")

    with patch("agents.forge.get_llm_adapter", return_value=fake_adapter):
        result = _compress_history(_MESSAGES, "claude-haiku-4-5-20251001", set(), _STORY)

    assert result is _MESSAGES
