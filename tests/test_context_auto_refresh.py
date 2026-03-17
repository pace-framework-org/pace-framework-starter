"""Tests for Item 13: Context Auto-Refresh on Document Updates (Sprint 6.3)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import yaml
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))

# ---------------------------------------------------------------------------
# preflight._archive_context
# ---------------------------------------------------------------------------

def _make_context(tmp_path: Path, docs: list[str], manifest_release: str = "v1.0") -> Path:
    ctx = tmp_path / ".pace" / "context"
    ctx.mkdir(parents=True)
    for doc in docs:
        (ctx / doc).write_text(f"content of {doc}")
    manifest = {
        "release": manifest_release,
        "generated_at": "2026-01-01T00:00:00Z",
        "source_hashes": {},
        "files": docs,
    }
    (ctx / "context.manifest.yaml").write_text(yaml.dump(manifest))
    return ctx


def test_archive_context_creates_dated_archives(tmp_path):
    import preflight
    ctx = _make_context(tmp_path, ["product.md", "engineering.md"])

    with patch("preflight.CONTEXT_DIR", ctx), \
         patch("preflight.REQUIRED_DOCS", ["product.md", "engineering.md"]):
        preflight._archive_context("v1.0")

    archived = [f.name for f in ctx.iterdir()]
    assert not (ctx / "product.md").exists()
    assert any("product.v1.0." in n and n.endswith(".md") for n in archived)
    assert any("engineering.v1.0." in n and n.endswith(".md") for n in archived)
    assert any("context.manifest.v1.0." in n and n.endswith(".yaml") for n in archived)


def test_archive_context_handles_same_day_collision(tmp_path):
    import preflight
    ctx = _make_context(tmp_path, ["product.md"])

    with patch("preflight.CONTEXT_DIR", ctx), \
         patch("preflight.REQUIRED_DOCS", ["product.md"]):
        # First archive — creates product.v1.0.<date>.md
        preflight._archive_context("v1.0")
        # Re-create the file and archive again same day
        (ctx / "product.md").write_text("new content")
        (ctx / "context.manifest.yaml").write_text(yaml.dump({"release": "v1.0", "files": ["product.md"], "generated_at": "t", "source_hashes": {}}))
        preflight._archive_context("v1.0")

    names = [f.name for f in ctx.iterdir()]
    product_archives = [n for n in names if n.startswith("product.v1.0.")]
    assert len(product_archives) == 2


def test_archive_context_non_fatal_on_error(tmp_path):
    import preflight
    # Point at a non-existent dir — should not raise
    with patch("preflight.CONTEXT_DIR", tmp_path / "nonexistent"), \
         patch("preflight.REQUIRED_DOCS", ["product.md"]):
        preflight._archive_context("v1.0")  # must not raise


# ---------------------------------------------------------------------------
# preflight._check_context_freshness
# ---------------------------------------------------------------------------

def test_check_context_freshness_returns_empty_no_manifest(tmp_path):
    import preflight
    ctx = tmp_path / ".pace" / "context"
    ctx.mkdir(parents=True)

    with patch("preflight.CONTEXT_DIR", ctx):
        result = preflight._check_context_freshness()

    assert result == []


def test_check_context_freshness_returns_empty_no_hashes(tmp_path):
    import preflight
    ctx = tmp_path / ".pace" / "context"
    ctx.mkdir(parents=True)
    manifest = {"release": "v1.0", "generated_at": "t", "source_hashes": {}, "files": []}
    (ctx / "context.manifest.yaml").write_text(yaml.dump(manifest))

    with patch("preflight.CONTEXT_DIR", ctx):
        result = preflight._check_context_freshness()

    assert result == []


def test_check_context_freshness_detects_changed_doc(tmp_path):
    import preflight
    ctx = tmp_path / ".pace" / "context"
    ctx.mkdir(parents=True)

    prd = tmp_path / "PRD.md"
    prd.write_text("original content")

    import hashlib
    old_hash = hashlib.sha256(b"old content").hexdigest()
    manifest = {
        "release": "v1.0", "generated_at": "t",
        "source_hashes": {"PRD.md": old_hash},
        "files": ["product.md"],
    }
    (ctx / "context.manifest.yaml").write_text(yaml.dump(manifest))

    mock_release = MagicMock()
    mock_release.name = "v1.0"
    mock_cfg = MagicMock()
    mock_cfg.active_release = mock_release

    with patch("preflight.CONTEXT_DIR", ctx), \
         patch("preflight.REPO_ROOT", tmp_path), \
         patch("preflight.REQUIRED_DOCS", ["product.md"]), \
         patch("config.load_config", return_value=mock_cfg), \
         patch("preflight._archive_context") as mock_archive, \
         patch("agents.scribe.run_scribe") as mock_scribe:
        result = preflight._check_context_freshness()

    assert "PRD.md" in result
    mock_archive.assert_called_once()
    mock_scribe.assert_called_once()


def test_check_context_freshness_no_change_no_scribe(tmp_path):
    import preflight, hashlib
    ctx = tmp_path / ".pace" / "context"
    ctx.mkdir(parents=True)

    prd = tmp_path / "PRD.md"
    prd.write_text("content")
    current_hash = hashlib.sha256(b"content").hexdigest()
    manifest = {
        "release": "v1.0", "generated_at": "t",
        "source_hashes": {"PRD.md": current_hash},
        "files": [],
    }
    (ctx / "context.manifest.yaml").write_text(yaml.dump(manifest))

    with patch("preflight.CONTEXT_DIR", ctx), \
         patch("preflight.REPO_ROOT", tmp_path), \
         patch("preflight._archive_context") as mock_archive, \
         patch("agents.scribe.run_scribe") as mock_scribe:
        result = preflight._check_context_freshness()

    assert result == []
    mock_archive.assert_not_called()
    mock_scribe.assert_not_called()


def test_check_context_freshness_non_fatal_on_exception(tmp_path):
    import preflight
    with patch("preflight.CONTEXT_DIR", tmp_path / "ctx"), \
         patch("preflight.REPO_ROOT", tmp_path):
        # Manifest exists but is invalid YAML — should return []
        ctx = tmp_path / "ctx"
        ctx.mkdir()
        (ctx / "context.manifest.yaml").write_text("not: valid: yaml: {{{")
        result = preflight._check_context_freshness()

    assert result == []


# ---------------------------------------------------------------------------
# preflight.force_refresh_context
# ---------------------------------------------------------------------------

def test_force_refresh_context_archives_and_reruns_scribe(tmp_path):
    import preflight
    ctx = _make_context(tmp_path, ["product.md"])

    mock_release = MagicMock()
    mock_release.name = "v2.0"
    mock_cfg = MagicMock()
    mock_cfg.active_release = mock_release

    with patch("preflight.CONTEXT_DIR", ctx), \
         patch("preflight.REQUIRED_DOCS", ["product.md"]), \
         patch("config.load_config", return_value=mock_cfg), \
         patch("preflight._archive_context") as mock_archive, \
         patch("agents.scribe.run_scribe") as mock_scribe:
        preflight.force_refresh_context()

    mock_archive.assert_called_once_with("v2.0", reason="forced refresh")
    mock_scribe.assert_called_once()


def test_force_refresh_context_uses_unknown_when_no_release(tmp_path):
    import preflight
    with patch("config.load_config", side_effect=RuntimeError("no cfg")), \
         patch("preflight._archive_context") as mock_archive, \
         patch("agents.scribe.run_scribe"):
        preflight.force_refresh_context()

    mock_archive.assert_called_once_with("unknown", reason="forced refresh")


# ---------------------------------------------------------------------------
# planner.py — _check_context_freshness called on replan
# ---------------------------------------------------------------------------

def test_planner_calls_freshness_check_on_replan(tmp_path):
    import planner
    with patch("preflight._check_context_freshness") as mock_fresh, \
         patch("planner.PACE_DIR", tmp_path / ".pace"), \
         patch("planner._load_existing_actuals", return_value={}), \
         patch("planner._estimate_day_cost", return_value={"estimated_usd": 0.1, "rationale": "x"}):
        planner.run_planner({"days": []}, "claude-sonnet-4-6", replan=True)

    mock_fresh.assert_called_once()


def test_planner_skips_freshness_check_when_not_replan(tmp_path):
    import planner
    with patch("preflight._check_context_freshness") as mock_fresh, \
         patch("planner.PACE_DIR", tmp_path / ".pace"), \
         patch("planner._load_existing_actuals", return_value={}), \
         patch("planner._estimate_day_cost", return_value={"estimated_usd": 0.1, "rationale": "x"}):
        planner.run_planner({"days": []}, "claude-sonnet-4-6", replan=False)

    mock_fresh.assert_not_called()


# ---------------------------------------------------------------------------
# config_tester._validate_source_docs
# ---------------------------------------------------------------------------

def test_validate_source_docs_suggests_when_none_present(tmp_path):
    from config_tester import _validate_source_docs, ConfigTestResult
    r = ConfigTestResult()
    with patch("config_tester.Path") as mock_path_cls:
        # Make repo_root / doc.exists() return False for all
        fake_root = MagicMock()
        fake_root.__truediv__ = lambda s, x: MagicMock(**{"exists.return_value": False})
        mock_path_cls.return_value.parent.parent = fake_root
        # Just call directly with a real tmp_path that has no docs
        pass
    # Manual: call with actual filesystem pointing at empty tmp_path
    import config_tester as ct
    orig = ct.Path
    try:
        # Patch __file__ parent parent to tmp_path
        with patch.object(ct, "_KNOWN_SOURCE_DOCS", ["NOEXIST1.md", "NOEXIST2.md"]):
            r2 = ConfigTestResult()
            ct._validate_source_docs(r2)
            assert any("No source documents found" in s for s in r2.suggestions)
    finally:
        pass


def test_validate_source_docs_no_suggestion_when_readme_exists(tmp_path):
    from config_tester import ConfigTestResult
    import config_tester as ct

    readme = Path(ct.__file__).parent.parent / "README.md"
    if not readme.exists():
        pytest.skip("README.md not present in repo root — skip")

    r = ConfigTestResult()
    ct._validate_source_docs(r)
    assert not any("No source documents found" in s for s in r.suggestions)
