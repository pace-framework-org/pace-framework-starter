"""Tests for Item 19: Planner-Triggered Context Refresh (_run_context_refresh)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

# conftest.py adds pace/ to sys.path
from planner import _run_context_refresh, run_pipeline


def _fake_preflight(stale=None, missing=None):
    mod = MagicMock()
    mod._check_context_freshness.return_value = stale or []
    mod._missing_docs.return_value = missing or []
    return mod


def _fake_scribe(should_raise=False):
    mod = MagicMock()
    if should_raise:
        mod.run_scribe.side_effect = RuntimeError("API timeout")
    return mod


# ---------------------------------------------------------------------------
# Test 1: Fresh context — no stale, no missing → SCRIBE not called
# ---------------------------------------------------------------------------

def test_context_refresh_skipped_when_fresh():
    """_run_context_refresh() returns empty summary when context is up to date."""
    scribe_mod = _fake_scribe()
    with patch.dict("sys.modules", {
        "preflight": _fake_preflight(stale=[], missing=[]),
        "agents.scribe": scribe_mod,
    }):
        summary = _run_context_refresh()

    scribe_mod.run_scribe.assert_not_called()
    assert summary["docs_refreshed"] == []
    assert summary["triggered_by"] == []
    assert summary["scribe_error"] is None


# ---------------------------------------------------------------------------
# Test 2: Stale hash → SCRIBE called, docs_refreshed populated
# ---------------------------------------------------------------------------

def test_context_refresh_triggers_scribe_on_stale_hash(tmp_path):
    """_run_context_refresh() calls run_scribe() when hashes are stale."""
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    for doc in ("engineering.md", "product.md"):
        (context_dir / doc).write_text("# doc")

    scribe_mod = _fake_scribe()
    with (
        patch.dict("sys.modules", {
            "preflight": _fake_preflight(stale=["engineering.md"], missing=[]),
            "agents.scribe": scribe_mod,
        }),
        patch("planner.PACE_DIR", tmp_path / ".pace"),
    ):
        summary = _run_context_refresh()

    scribe_mod.run_scribe.assert_called_once()
    assert "engineering.md" in summary["triggered_by"]
    assert set(summary["docs_refreshed"]) == {"engineering.md", "product.md"}
    assert summary["scribe_error"] is None


# ---------------------------------------------------------------------------
# Test 3: SCRIBE failure is non-fatal — scribe_error set, no exception raised
# ---------------------------------------------------------------------------

def test_context_refresh_scribe_failure_is_nonfatal():
    """_run_context_refresh() catches SCRIBE exceptions and sets scribe_error."""
    with patch.dict("sys.modules", {
        "preflight": _fake_preflight(stale=[], missing=["security.md"]),
        "agents.scribe": _fake_scribe(should_raise=True),
    }):
        summary = _run_context_refresh()  # must NOT raise

    assert summary["scribe_error"] == "API timeout"
    assert summary["docs_refreshed"] == []
    assert "missing:security.md" in summary["triggered_by"]


# ---------------------------------------------------------------------------
# Test 4: planner.md contains context_refresh_summary after run_pipeline()
# ---------------------------------------------------------------------------

def test_run_pipeline_writes_context_refresh_summary_to_planner_md(tmp_path):
    """run_pipeline() patches planner.md with context_refresh_summary."""
    day0 = tmp_path / ".pace" / "day-0"
    day0.mkdir(parents=True)
    planner_md = day0 / "planner.md"
    planner_md.write_text(yaml.dump({"total_estimated_usd": 1.5, "estimates": {}}))

    fake_ci = MagicMock()
    fake_ci.set_variable.return_value = True
    fake_platforms = MagicMock()
    fake_platforms.get_ci_adapter.return_value = fake_ci

    with (
        patch.dict("sys.modules", {
            "preflight": _fake_preflight(stale=[], missing=[]),
            "platforms": fake_platforms,
        }),
        patch("planner.PACE_DIR", tmp_path / ".pace"),
        patch("planner._collect_shipped_days", return_value=[]),
        patch("planner._write_shipped_manifest"),
        patch("planner.run_planner", return_value={"total_estimated_usd": 1.5}),
    ):
        run_pipeline(plan={}, model="test-model")

    data = yaml.safe_load(planner_md.read_text())
    assert "context_refresh_summary" in data
    s = data["context_refresh_summary"]
    assert isinstance(s["docs_refreshed"], list)
    assert isinstance(s["triggered_by"], list)
    assert s["scribe_error"] is None
