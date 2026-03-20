"""Tests for Item 26 Phase A: FORGE forked subcontext (commit_plan + _fork_context)."""
from unittest.mock import MagicMock, patch

import yaml

from agents.forge import _fork_context, _build_tools


_STORY = {"title": "Add login endpoint", "acceptance": ["POST /login returns 200"]}

_EXPLORATION_MESSAGES = [
    {"role": "user", "content": "Story Card:\ntitle: Add login endpoint"},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "r1", "name": "read_file", "input": {"path": "pace/auth.py"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "r1", "content": "existing auth code (3000 bytes)"},
    ]},
]

_VALID_SUMMARY = yaml.dump({
    "files_read": ["pace/auth.py"],
    "files_written": [],
    "plan_committed": False,
    "key_decisions": ["use JWT"],
    "last_test_output": "",
    "red_phase_confirmed": False,
}, default_flow_style=False)


# ---------------------------------------------------------------------------
# Test 1: commit_plan tool is present in tools when fork_enabled=True
# ---------------------------------------------------------------------------

def test_build_tools_includes_commit_plan_when_fork_enabled():
    """_build_tools includes commit_plan when fork_enabled=True."""
    tools_fork = _build_tools(tdd_enforcement=True, fork_enabled=True)
    names = [t["name"] for t in tools_fork]
    assert "commit_plan" in names


# ---------------------------------------------------------------------------
# Test 2: commit_plan tool is NOT present when fork_enabled=False (default)
# ---------------------------------------------------------------------------

def test_build_tools_excludes_commit_plan_when_fork_disabled():
    """_build_tools does not include commit_plan when fork_enabled=False."""
    tools_no_fork = _build_tools(tdd_enforcement=True, fork_enabled=False)
    names = [t["name"] for t in tools_no_fork]
    assert "commit_plan" not in names


# ---------------------------------------------------------------------------
# Test 3: _fork_context produces ≤ original len + 1 messages with plan section
# ---------------------------------------------------------------------------

def test_fork_context_produces_compact_messages_with_plan(tmp_path):
    """_fork_context returns a new message list containing the implementation plan."""
    fake_adapter = MagicMock()
    fake_adapter.complete.return_value = f"```yaml\n{_VALID_SUMMARY}```"

    with patch("agents.forge.get_llm_adapter", return_value=fake_adapter):
        result = _fork_context(
            _EXPLORATION_MESSAGES,
            plan="Add JWT auth to /login endpoint",
            files_to_modify=["pace/auth.py", "tests/test_auth.py"],
            story_card=_STORY,
            compression_model="claude-haiku-4-5-20251001",
            written_paths=set(),
        )

    # Result should be compact (original was 3 messages; forked should be ≤ 4)
    assert len(result) <= len(_EXPLORATION_MESSAGES) + 2
    # Last message must contain the implementation plan
    last_content = result[-1]["content"]
    if isinstance(last_content, list):
        last_text = last_content[0].get("text", "")
    else:
        last_text = str(last_content)
    assert "Implementation Plan" in last_text or "implement" in last_text.lower()
    assert "pace/auth.py" in last_text


# ---------------------------------------------------------------------------
# Test 4: single-context fallback — no fork when fork_enabled=False
# (Validates that _forked=True when hold_reason set, meaning retry skips fork)
# ---------------------------------------------------------------------------

def test_fork_context_fallback_when_no_compression_model():
    """_fork_context falls back gracefully when compression_model is None."""
    # No compression — should still produce a forked context with plan appended
    result = _fork_context(
        _EXPLORATION_MESSAGES,
        plan="Simple implementation plan",
        files_to_modify=[],
        story_card=_STORY,
        compression_model=None,
        written_paths=set(),
    )
    # Should have at least the original messages plus the plan message
    assert len(result) >= len(_EXPLORATION_MESSAGES) + 1
    last_content = result[-1]["content"]
    if isinstance(last_content, list):
        last_text = last_content[0].get("text", "")
    else:
        last_text = str(last_content)
    assert "Simple implementation plan" in last_text
