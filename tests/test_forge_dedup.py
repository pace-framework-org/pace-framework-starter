"""Tests for Item 22: FORGE test output deduplication (_dedup_bash_results)."""
from agents.forge import _dedup_bash_results


def _bash_call(tool_id, cmd):
    return {"type": "tool_use", "id": tool_id, "name": "run_bash", "input": {"command": cmd}}


def _bash_result(tool_use_id, content):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}


def test_dedup_replaces_earlier_runs_of_same_command():
    """Earlier run_bash results for repeated commands are replaced with placeholder."""
    messages = [
        {"role": "assistant", "content": [_bash_call("b1", "pytest -x")]},
        {"role": "user", "content": [_bash_result("b1", "3 failed")]},
        {"role": "assistant", "content": [_bash_call("b2", "pytest -x")]},
        {"role": "user", "content": [_bash_result("b2", "0 failed")]},
    ]
    _dedup_bash_results(messages)
    # Earlier result replaced
    assert "dedup" in messages[1]["content"][0]["content"]
    # Latest result preserved
    assert messages[3]["content"][0]["content"] == "0 failed"


def test_dedup_preserves_unique_commands():
    """Results for distinct commands are not modified."""
    messages = [
        {"role": "assistant", "content": [_bash_call("b1", "pytest -x")]},
        {"role": "user", "content": [_bash_result("b1", "test output")]},
        {"role": "assistant", "content": [_bash_call("b2", "git diff")]},
        {"role": "user", "content": [_bash_result("b2", "diff output")]},
    ]
    _dedup_bash_results(messages)
    assert messages[1]["content"][0]["content"] == "test output"
    assert messages[3]["content"][0]["content"] == "diff output"


def test_dedup_noop_with_single_occurrence():
    """Single occurrence of a command is not modified."""
    messages = [
        {"role": "assistant", "content": [_bash_call("b1", "pytest -x")]},
        {"role": "user", "content": [_bash_result("b1", "only run")]},
    ]
    _dedup_bash_results(messages)
    assert messages[1]["content"][0]["content"] == "only run"


def test_dedup_three_runs_keeps_only_last():
    """With three runs of the same command, only the last is preserved."""
    messages = [
        {"role": "assistant", "content": [_bash_call("b1", "pytest")]},
        {"role": "user", "content": [_bash_result("b1", "run 1")]},
        {"role": "assistant", "content": [_bash_call("b2", "pytest")]},
        {"role": "user", "content": [_bash_result("b2", "run 2")]},
        {"role": "assistant", "content": [_bash_call("b3", "pytest")]},
        {"role": "user", "content": [_bash_result("b3", "run 3 — final")]},
    ]
    _dedup_bash_results(messages)
    assert "dedup" in messages[1]["content"][0]["content"]
    assert "dedup" in messages[3]["content"][0]["content"]
    assert messages[5]["content"][0]["content"] == "run 3 — final"
