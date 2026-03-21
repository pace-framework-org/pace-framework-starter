"""Tests for Item 21: FORGE stale file read eviction (_evict_stale_reads)."""
from agents.forge import _evict_stale_reads


def _read_result(tool_use_id, content):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}


def _read_call(tool_id, path):
    return {"type": "tool_use", "id": tool_id, "name": "read_file", "input": {"path": path}}


def _write_call(tool_id, path):
    return {"type": "tool_use", "id": tool_id, "name": "write_file",
            "input": {"path": path, "content": "new content"}}


def test_evict_replaces_stale_read_content():
    """read_file result is replaced when the path was subsequently written."""
    messages = [
        {"role": "assistant", "content": [_read_call("r1", "pace/foo.py")]},
        {"role": "user", "content": [_read_result("r1", "original file content")]},
    ]
    _evict_stale_reads(messages, {"pace/foo.py"})
    content = messages[1]["content"][0]["content"]
    assert "evicted" in content
    assert "pace/foo.py" in content
    assert "original file content" not in content


def test_evict_preserves_reads_for_unwritten_paths():
    """read_file results for paths NOT written are left untouched."""
    messages = [
        {"role": "assistant", "content": [_read_call("r1", "pace/bar.py")]},
        {"role": "user", "content": [_read_result("r1", "untouched content")]},
    ]
    _evict_stale_reads(messages, {"pace/other.py"})
    assert messages[1]["content"][0]["content"] == "untouched content"


def test_evict_noop_when_written_paths_empty():
    """No mutations when written_paths is empty."""
    messages = [
        {"role": "assistant", "content": [_read_call("r1", "pace/foo.py")]},
        {"role": "user", "content": [_read_result("r1", "content")]},
    ]
    _evict_stale_reads(messages, set())
    assert messages[1]["content"][0]["content"] == "content"


def test_evict_multiple_reads_same_path():
    """All read_file results for a written path are evicted."""
    messages = [
        {"role": "assistant", "content": [_read_call("r1", "pace/foo.py")]},
        {"role": "user", "content": [_read_result("r1", "first read")]},
        {"role": "assistant", "content": [_read_call("r2", "pace/foo.py")]},
        {"role": "user", "content": [_read_result("r2", "second read")]},
    ]
    _evict_stale_reads(messages, {"pace/foo.py"})
    assert "evicted" in messages[1]["content"][0]["content"]
    assert "evicted" in messages[3]["content"][0]["content"]
