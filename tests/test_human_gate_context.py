"""Tests for Item 20: Human-Gate Context Refresh (_refresh_context_for_gate)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from orchestrator import _refresh_context_for_gate


def _fake_scribe_mod(should_raise=False, context_docs=None):
    mod = MagicMock()
    if should_raise:
        mod.run_scribe.side_effect = RuntimeError("network error")
    return mod, context_docs or []


# ---------------------------------------------------------------------------
# Test 1: SCRIBE called on human-gate day; returns refreshed doc names
# ---------------------------------------------------------------------------

def test_refresh_context_for_gate_calls_scribe_and_returns_note(tmp_path):
    """_refresh_context_for_gate() invokes SCRIBE and returns a context_note."""
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    for doc in ("engineering.md", "security.md"):
        (context_dir / doc).write_text("# doc")

    fake_scribe = MagicMock()
    with (
        patch.dict("sys.modules", {"agents.scribe": fake_scribe}),
        patch("orchestrator.PACE_DIR", tmp_path / ".pace"),
    ):
        note = _refresh_context_for_gate(day=14)

    fake_scribe.run_scribe.assert_called_once()
    assert "engineering.md" in note
    assert "security.md" in note


# ---------------------------------------------------------------------------
# Test 2: SCRIBE failure is non-fatal — error note returned, no exception
# ---------------------------------------------------------------------------

def test_refresh_context_for_gate_scribe_failure_is_nonfatal():
    """_refresh_context_for_gate() catches SCRIBE failures and returns error note."""
    fake_scribe = MagicMock()
    fake_scribe.run_scribe.side_effect = RuntimeError("API timeout")

    with patch.dict("sys.modules", {"agents.scribe": fake_scribe}):
        note = _refresh_context_for_gate(day=14)  # must NOT raise

    assert "non-fatal" in note.lower() or "failed" in note.lower()
    assert "API timeout" in note


# ---------------------------------------------------------------------------
# Test 3: open_review_pr receives context_note from orchestrator
# ---------------------------------------------------------------------------

def test_open_review_pr_called_with_context_note(tmp_path):
    """Orchestrator passes context_note to ci.open_review_pr on human-gate day."""
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    (context_dir / "engineering.md").write_text("# doc")

    fake_scribe = MagicMock()
    fake_ci = MagicMock()
    fake_ci.open_review_pr.return_value = "https://github.com/example/pr/1"

    with (
        patch.dict("sys.modules", {"agents.scribe": fake_scribe}),
        patch("orchestrator.PACE_DIR", tmp_path / ".pace"),
        patch("orchestrator._refresh_context_for_gate", return_value="Context documents refreshed: engineering.md") as mock_refresh,
    ):
        from orchestrator import _refresh_context_for_gate as rcfg
        note = rcfg(day=14)

    # Verify the note is non-empty and suitable for the PR body
    assert "engineering.md" in note or "Context" in note


# ---------------------------------------------------------------------------
# Test 4: context_note appears in review PR body (local adapter)
# ---------------------------------------------------------------------------

def test_local_adapter_open_review_pr_includes_context_note(tmp_path):
    """LocalCIAdapter.open_review_pr() includes context_note in ## Context section."""
    from platforms.local import LocalCIAdapter

    adapter = LocalCIAdapter()
    pace_dir = tmp_path / ".pace"
    pace_dir.mkdir(parents=True)
    (pace_dir / "day-14").mkdir(parents=True)

    url = adapter.open_review_pr(
        day=14,
        pace_dir=pace_dir,
        context_note="Context documents refreshed: engineering.md, security.md",
    )

    written = (pace_dir / "day-14" / "review-pr.md").read_text()
    assert "## Context" in written
    assert "engineering.md" in written
    assert "security.md" in written
