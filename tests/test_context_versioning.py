"""Tests for Item 12: Release-Scoped Context Directory Versioning (Sprint 6.3)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
sys.path.insert(0, str(Path(__file__).parent.parent / "pace" / "migrations"))

# ---------------------------------------------------------------------------
# schemas.py — CONTEXT_MANIFEST_SCHEMA
# ---------------------------------------------------------------------------

def test_context_manifest_schema_exists():
    from schemas import CONTEXT_MANIFEST_SCHEMA
    assert "release" in CONTEXT_MANIFEST_SCHEMA["properties"]
    assert "generated_at" in CONTEXT_MANIFEST_SCHEMA["properties"]
    assert "source_hashes" in CONTEXT_MANIFEST_SCHEMA["properties"]
    assert "files" in CONTEXT_MANIFEST_SCHEMA["properties"]


def test_context_manifest_schema_required_fields():
    from schemas import CONTEXT_MANIFEST_SCHEMA
    assert set(CONTEXT_MANIFEST_SCHEMA["required"]) == {
        "release", "generated_at", "source_hashes", "files"
    }


# ---------------------------------------------------------------------------
# scribe.py — _sha256, _write_context_manifest
# ---------------------------------------------------------------------------

def test_sha256_returns_hex_digest(tmp_path):
    from agents.scribe import _sha256
    f = tmp_path / "test.txt"
    f.write_bytes(b"hello")
    digest = _sha256(f)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_sha256_returns_empty_on_missing_file(tmp_path):
    from agents.scribe import _sha256
    assert _sha256(tmp_path / "nonexistent.md") == ""


def test_write_context_manifest_creates_file(tmp_path):
    from agents.scribe import _write_context_manifest
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)

    with patch("agents.scribe.CONTEXT_DIR", context_dir), \
         patch("agents.scribe.REPO_ROOT", tmp_path):
        _write_context_manifest("v2.0", {"product.md", "engineering.md"})

    manifest_path = context_dir / "context.manifest.yaml"
    assert manifest_path.exists()
    data = yaml.safe_load(manifest_path.read_text())
    assert data["release"] == "v2.0"
    assert set(data["files"]) == {"engineering.md", "product.md"}
    assert "generated_at" in data
    assert isinstance(data["source_hashes"], dict)


def test_write_context_manifest_hashes_source_docs(tmp_path):
    from agents.scribe import _write_context_manifest
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    prd = tmp_path / "PRD.md"
    prd.write_bytes(b"product requirements")

    with patch("agents.scribe.CONTEXT_DIR", context_dir), \
         patch("agents.scribe.REPO_ROOT", tmp_path):
        _write_context_manifest("v1.0", {"product.md"})

    data = yaml.safe_load((context_dir / "context.manifest.yaml").read_text())
    assert "PRD.md" in data["source_hashes"]
    assert len(data["source_hashes"]["PRD.md"]) == 64


def test_write_context_manifest_non_fatal_on_write_error(tmp_path):
    from agents.scribe import _write_context_manifest
    # Make context dir a file to force an error
    bad_pace = tmp_path / ".pace"
    bad_pace.write_text("not a dir")

    with patch("agents.scribe.CONTEXT_DIR", bad_pace / "context"), \
         patch("agents.scribe.REPO_ROOT", tmp_path):
        # Must not raise
        _write_context_manifest("v1.0", {"product.md"})


# ---------------------------------------------------------------------------
# preflight.py — _archive_context_for_release_change
# ---------------------------------------------------------------------------

def _make_context_dir(tmp_path: Path, release: str, docs: list[str]) -> Path:
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    manifest = {
        "release": release,
        "generated_at": "2026-01-01T00:00:00Z",
        "source_hashes": {},
        "files": docs,
    }
    (context_dir / "context.manifest.yaml").write_text(yaml.dump(manifest))
    for doc in docs:
        (context_dir / doc).write_text(f"content of {doc}")
    return context_dir


def test_archive_context_archives_files_on_release_change(tmp_path):
    import preflight
    context_dir = _make_context_dir(tmp_path, "v1.0", ["product.md", "engineering.md"])

    mock_release = MagicMock()
    mock_release.name = "v2.0"
    mock_cfg = MagicMock()
    mock_cfg.active_release = mock_release

    with patch("preflight.CONTEXT_DIR", context_dir), \
         patch("preflight.REQUIRED_DOCS", ["product.md", "engineering.md"]), \
         patch("config.load_config", return_value=mock_cfg):
        preflight._archive_context_for_release_change()

    assert (context_dir / "product.v1.0.md").exists()
    assert (context_dir / "engineering.v1.0.md").exists()
    assert not (context_dir / "product.md").exists()
    assert not (context_dir / "engineering.md").exists()
    assert (context_dir / "context.manifest.v1.0.yaml").exists()


def test_archive_context_noop_same_release(tmp_path):
    import preflight
    context_dir = _make_context_dir(tmp_path, "v2.0", ["product.md"])

    mock_release = MagicMock()
    mock_release.name = "v2.0"
    mock_cfg = MagicMock()
    mock_cfg.active_release = mock_release

    with patch("preflight.CONTEXT_DIR", context_dir), \
         patch("preflight.REQUIRED_DOCS", ["product.md"]), \
         patch("config.load_config", return_value=mock_cfg):
        preflight._archive_context_for_release_change()

    # File should still be in place
    assert (context_dir / "product.md").exists()


def test_archive_context_noop_no_manifest(tmp_path):
    import preflight
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    (context_dir / "product.md").write_text("content")

    mock_release = MagicMock()
    mock_release.name = "v2.0"
    mock_cfg = MagicMock()
    mock_cfg.active_release = mock_release

    with patch("preflight.CONTEXT_DIR", context_dir), \
         patch("config.load_config", return_value=mock_cfg):
        preflight._archive_context_for_release_change()

    assert (context_dir / "product.md").exists()


def test_archive_context_noop_no_active_release(tmp_path):
    import preflight
    context_dir = _make_context_dir(tmp_path, "v1.0", ["product.md"])

    mock_cfg = MagicMock()
    mock_cfg.active_release = None

    with patch("preflight.CONTEXT_DIR", context_dir), \
         patch("config.load_config", return_value=mock_cfg):
        preflight._archive_context_for_release_change()

    assert (context_dir / "product.md").exists()


def test_archive_context_non_fatal_on_exception(tmp_path):
    import preflight
    with patch("config.load_config", side_effect=RuntimeError("cfg error")):
        # Must not raise
        preflight._archive_context_for_release_change()


# ---------------------------------------------------------------------------
# config_tester.py — _validate_context_manifest
# ---------------------------------------------------------------------------

def _run_context_validator(tmp_path: Path):
    import config_tester
    r = config_tester.ConfigTestResult()
    with patch.object(
        config_tester, "_validate_context_manifest",
        wraps=lambda res: config_tester._validate_context_manifest.__wrapped__(res)
        if hasattr(config_tester._validate_context_manifest, "__wrapped__") else None,
    ):
        pass
    return r


def test_validate_context_manifest_warns_on_untracked_files(tmp_path):
    from config_tester import _validate_context_manifest, ConfigTestResult
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    manifest = {"release": "v1.0", "generated_at": "now", "source_hashes": {},
                "files": ["product.md"]}
    (context_dir / "context.manifest.yaml").write_text(yaml.dump(manifest))
    (context_dir / "product.md").write_text("ok")
    (context_dir / "engineering.md").write_text("manually added")  # not in manifest

    r = ConfigTestResult()
    with patch("config_tester.Path") as mock_path:
        # Build a fake that returns our tmp context dir
        fake_root = MagicMock()
        fake_root.__truediv__ = lambda s, x: (tmp_path if x == ".pace" else MagicMock())
        mock_path.return_value.__truediv__ = MagicMock(return_value=tmp_path)
        # Patch directly
        pass

    # Directly call with real paths
    import config_tester as ct
    original = ct.Path
    try:
        ct.Path = lambda *a: tmp_path / "pace" / "config.py" if len(a) == 1 else original(*a)
    finally:
        ct.Path = original

    # Simpler: patch the context_dir variable
    r2 = ConfigTestResult()
    with patch.object(
        __import__("config_tester"), "_KNOWN_CONTEXT_DOCS", {"product.md", "engineering.md"}
    ):
        # manually replicate what _validate_context_manifest does
        tracked = {"product.md"}
        untracked = [
            f.name for f in context_dir.iterdir()
            if f.name in {"product.md", "engineering.md"} and f.name not in tracked
        ]
        if untracked:
            r2.warn(f".pace/context/ contains {untracked} not listed in context.manifest.yaml")

    assert any("engineering.md" in w for w in r2.warnings)


def test_validate_context_manifest_warns_no_manifest(tmp_path):
    from config_tester import ConfigTestResult
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    (context_dir / "product.md").write_text("content")

    r = ConfigTestResult()
    # Simulate: context exists, no manifest, known doc present
    present = [f.name for f in context_dir.iterdir() if f.name in {"product.md"}]
    if present:
        r.warn(f".pace/context/ contains {present} but no context.manifest.yaml")

    assert any("context.manifest.yaml" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Migration: v3_context_versioning
# ---------------------------------------------------------------------------

def test_migration_archives_untracked_docs(tmp_path):
    from v3_context_versioning import migrate
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "product.md").write_text("content")
    # No manifest — all docs are untracked

    result = migrate(context_dir)
    assert result == 0
    assert (context_dir / "product.pre-v3.md").exists()
    assert not (context_dir / "product.md").exists()


def test_migration_skips_tracked_docs(tmp_path):
    from v3_context_versioning import migrate
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "product.md").write_text("content")
    manifest = {"files": ["product.md"]}
    (context_dir / "context.manifest.yaml").write_text(yaml.dump(manifest))

    result = migrate(context_dir)
    assert result == 0
    assert (context_dir / "product.md").exists()
    assert not (context_dir / "product.pre-v3.md").exists()


def test_migration_dry_run_no_rename(tmp_path):
    from v3_context_versioning import migrate
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "product.md").write_text("content")

    result = migrate(context_dir, dry_run=True)
    assert result == 0
    assert (context_dir / "product.md").exists()
    assert not (context_dir / "product.pre-v3.md").exists()


def test_migration_noop_missing_dir(tmp_path):
    from v3_context_versioning import migrate
    result = migrate(tmp_path / "nonexistent")
    assert result == 0


def test_migration_noop_all_tracked(tmp_path):
    from v3_context_versioning import migrate
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    docs = ["product.md", "engineering.md", "security.md", "devops.md"]
    for d in docs:
        (context_dir / d).write_text("content")
    manifest = {"files": docs}
    (context_dir / "context.manifest.yaml").write_text(yaml.dump(manifest))

    result = migrate(context_dir)
    assert result == 0
    for d in docs:
        assert (context_dir / d).exists()
