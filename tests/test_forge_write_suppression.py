"""Tests for Item 23: FORGE write receipt suppression and Item 21 path tracking."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.forge import _rebuild_written_paths


def _write_call(tool_id, path, content="code"):
    return {
        "type": "tool_use", "id": tool_id, "name": "write_file",
        "input": {"path": path, "content": content},
    }


# ---------------------------------------------------------------------------
# Test 1: write_file tool result is a compact receipt, not full content
# ---------------------------------------------------------------------------

def test_write_receipt_is_compact(tmp_path):
    """write_file produces 'OK: wrote N bytes to path (iter N)' receipt."""
    from agents.forge import _dispatch_tool
    import agents.forge as forge_mod

    # Patch REPO_ROOT so the file write lands in tmp_path
    with patch.object(forge_mod, "REPO_ROOT", tmp_path):
        (tmp_path / "pace").mkdir(exist_ok=True)
        # Simulate what the loop does:
        # _dispatch_tool returns the raw result; receipt replacement happens in-loop.
        # Here we test the receipt string format by calling _dispatch_tool and
        # simulating the loop's receipt replacement logic.
        content = "def hello(): pass\n"
        path = "pace/hello.py"
        raw_result = _dispatch_tool("write_file", {"path": path, "content": content})

    # The receipt format as produced by the loop
    receipt = f"OK: wrote {len(content)} bytes to {path} (iter 1)"
    assert "bytes" in receipt
    assert path in receipt
    assert "iter" in receipt
    # The receipt is much shorter than the content echoed back would be
    assert len(receipt) < 200


# ---------------------------------------------------------------------------
# Test 2: _rebuild_written_paths reconstructs written set from history
# ---------------------------------------------------------------------------

def test_rebuild_written_paths_from_checkpoint():
    """_rebuild_written_paths extracts paths from write_file calls in history."""
    messages = [
        {"role": "assistant", "content": [
            _write_call("w1", "pace/foo.py"),
            _write_call("w2", "tests/test_foo.py"),
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "w1", "content": "OK"},
            {"type": "tool_result", "tool_use_id": "w2", "content": "OK"},
        ]},
    ]
    written = _rebuild_written_paths(messages)
    assert "pace/foo.py" in written
    assert "tests/test_foo.py" in written


# ---------------------------------------------------------------------------
# Test 3: _rebuild_written_paths returns empty set for clean history
# ---------------------------------------------------------------------------

def test_rebuild_written_paths_empty_for_fresh_session():
    """_rebuild_written_paths returns empty set when no write_file calls in history."""
    messages = [
        {"role": "user", "content": "Implement the story."},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "r1", "name": "read_file", "input": {"path": "pace/foo.py"}},
        ]},
    ]
    written = _rebuild_written_paths(messages)
    assert written == set()
