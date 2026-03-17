"""Tests for pace/pacemap.py (Item 17 + partial Item 18 CHANGELOG helpers)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure pace/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_roadmap_text(version: str) -> str:
    return f"# PACE Roadmap\n\n**Roadmap Version:** {version} (some notes)\n"


# ---------------------------------------------------------------------------
# _read_roadmap_version
# ---------------------------------------------------------------------------


def test_read_roadmap_version_extracts_version():
    import pacemap
    text = _make_roadmap_text("1.5")
    assert pacemap._read_roadmap_version(text) == "1.5"


def test_read_roadmap_version_returns_none_when_absent():
    import pacemap
    assert pacemap._read_roadmap_version("# No version header\n") is None


def test_read_roadmap_version_ignores_trailing_notes():
    import pacemap
    text = "**Roadmap Version:** 2.0 (revised 2026-03-17)\n"
    assert pacemap._read_roadmap_version(text) == "2.0"


# ---------------------------------------------------------------------------
# snapshot_roadmap
# ---------------------------------------------------------------------------


def test_snapshot_roadmap_creates_versioned_file(tmp_path):
    import pacemap as pm

    pacemap_dir = tmp_path / ".pacemap"
    roadmap_file = pacemap_dir / "ROADMAP.md"
    roadmap_file.parent.mkdir(parents=True)
    roadmap_file.write_text("# Roadmap v1.5 content")

    with patch.object(pm, "PACEMAP_DIR", pacemap_dir), \
         patch.object(pm, "VERSIONS_DIR", pacemap_dir / "versions"), \
         patch.object(pm, "ROADMAP_FILE", roadmap_file), \
         patch.object(pm, "REPO_ROOT", tmp_path), \
         patch("pacemap._git_commit_pacemap", return_value=True):
        result = pm.snapshot_roadmap("1.5", "test snapshot")

    assert result is True
    snapshot = pacemap_dir / "versions" / "ROADMAP-v1.5.md"
    assert snapshot.exists()
    assert snapshot.read_text() == "# Roadmap v1.5 content"


def test_snapshot_roadmap_skips_if_snapshot_exists(tmp_path):
    import pacemap as pm

    pacemap_dir = tmp_path / ".pacemap"
    versions_dir = pacemap_dir / "versions"
    versions_dir.mkdir(parents=True)
    roadmap_file = pacemap_dir / "ROADMAP.md"
    roadmap_file.write_text("new content")
    existing = versions_dir / "ROADMAP-v1.5.md"
    existing.write_text("old content")

    with patch.object(pm, "PACEMAP_DIR", pacemap_dir), \
         patch.object(pm, "VERSIONS_DIR", versions_dir), \
         patch.object(pm, "ROADMAP_FILE", roadmap_file), \
         patch.object(pm, "REPO_ROOT", tmp_path), \
         patch("pacemap._git_commit_pacemap", return_value=True) as mock_commit:
        result = pm.snapshot_roadmap("1.5", "should skip")

    assert result is True
    assert existing.read_text() == "old content"  # not overwritten
    mock_commit.assert_not_called()


def test_snapshot_roadmap_returns_false_when_roadmap_missing(tmp_path):
    import pacemap as pm

    pacemap_dir = tmp_path / ".pacemap"
    pacemap_dir.mkdir()

    with patch.object(pm, "PACEMAP_DIR", pacemap_dir), \
         patch.object(pm, "ROADMAP_FILE", pacemap_dir / "ROADMAP.md"), \
         patch.object(pm, "REPO_ROOT", tmp_path):
        result = pm.snapshot_roadmap("1.5", "missing roadmap")

    assert result is False


def test_snapshot_roadmap_non_fatal_on_exception(tmp_path):
    import pacemap as pm

    with patch.object(pm, "ROADMAP_FILE", MagicMock(exists=MagicMock(side_effect=RuntimeError("boom")))):
        result = pm.snapshot_roadmap("1.5", "error case")

    assert result is False


# ---------------------------------------------------------------------------
# snapshot_roadmap_if_version_changed
# ---------------------------------------------------------------------------


def test_snapshot_if_version_changed_triggers_on_version_bump(tmp_path):
    import pacemap as pm

    prev = _make_roadmap_text("1.4")
    curr = _make_roadmap_text("1.5")

    with patch("pacemap.snapshot_roadmap", return_value=True) as mock_snap:
        result = pm.snapshot_roadmap_if_version_changed(prev, curr)

    assert result is True
    mock_snap.assert_called_once_with("1.4", "snapshot before upgrade to v1.5")


def test_snapshot_if_version_changed_skips_same_version():
    import pacemap as pm

    text = _make_roadmap_text("1.5")

    with patch("pacemap.snapshot_roadmap") as mock_snap:
        result = pm.snapshot_roadmap_if_version_changed(text, text)

    assert result is True
    mock_snap.assert_not_called()


def test_snapshot_if_version_changed_skips_when_no_header():
    import pacemap as pm

    with patch("pacemap.snapshot_roadmap") as mock_snap:
        result = pm.snapshot_roadmap_if_version_changed("no header", "no header")

    assert result is True
    mock_snap.assert_not_called()


# ---------------------------------------------------------------------------
# update_changelog
# ---------------------------------------------------------------------------


def test_update_changelog_inserts_versioned_block(tmp_path):
    import pacemap as pm

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [v1.0.0] — 2026-01-01\n")

    with patch.object(pm, "CHANGELOG_FILE", changelog), \
         patch("pacemap._today_iso", return_value="2026-03-17"):
        result = pm.update_changelog("v2.0.0", added=["New feature A"], fixed=["Bug B"])

    assert result is True
    text = changelog.read_text()
    assert "## [v2.0.0] — 2026-03-17" in text
    assert "### Added" in text
    assert "- New feature A" in text
    assert "### Fixed" in text
    assert "- Bug B" in text


def test_update_changelog_returns_false_when_file_missing(tmp_path):
    import pacemap as pm

    with patch.object(pm, "CHANGELOG_FILE", tmp_path / "CHANGELOG.md"):
        result = pm.update_changelog("v2.0.0", added=["x"])

    assert result is False


def test_update_changelog_non_fatal_on_exception():
    import pacemap as pm

    with patch.object(pm, "CHANGELOG_FILE", MagicMock(exists=MagicMock(side_effect=OSError("disk full")))):
        result = pm.update_changelog("v2.0.0")

    assert result is False


def test_update_changelog_no_unreleased_section(tmp_path):
    import pacemap as pm

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [v1.0.0] — 2026-01-01\n")

    with patch.object(pm, "CHANGELOG_FILE", changelog), \
         patch("pacemap._today_iso", return_value="2026-03-17"):
        result = pm.update_changelog("v2.0.0", added=["X"])

    assert result is True
    assert "## [v2.0.0] — 2026-03-17" in changelog.read_text()


# ---------------------------------------------------------------------------
# update_changelog_story_shipped
# ---------------------------------------------------------------------------


def test_update_changelog_story_shipped_appends_line(tmp_path):
    import pacemap as pm

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n")

    with patch.object(pm, "CHANGELOG_FILE", changelog):
        result = pm.update_changelog_story_shipped("Day 3", "v2.0", "User can login")

    assert result is True
    assert "- [v2.0] Day 3: User can login" in changelog.read_text()


def test_update_changelog_story_shipped_creates_unreleased_section(tmp_path):
    import pacemap as pm

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [v1.0.0] — 2026-01-01\n")

    with patch.object(pm, "CHANGELOG_FILE", changelog):
        pm.update_changelog_story_shipped("Day 1", "v2.0", "First story")

    text = changelog.read_text()
    assert "## [Unreleased]" in text
    assert "Day 1" in text


def test_update_changelog_story_shipped_truncates_long_summary(tmp_path):
    import pacemap as pm

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [Unreleased]\n")

    with patch.object(pm, "CHANGELOG_FILE", changelog):
        pm.update_changelog_story_shipped("Day 1", "v2.0", "A" * 100)

    text = changelog.read_text()
    # summary truncated to 80 chars
    assert "A" * 80 in text
    assert "A" * 81 not in text


def test_update_changelog_story_shipped_skips_when_file_missing(tmp_path):
    import pacemap as pm

    with patch.object(pm, "CHANGELOG_FILE", tmp_path / "CHANGELOG.md"):
        result = pm.update_changelog_story_shipped("Day 1", "v2.0", "story")

    assert result is True  # silently skips


def test_update_changelog_story_shipped_non_fatal_on_exception():
    import pacemap as pm

    with patch.object(pm, "CHANGELOG_FILE", MagicMock(exists=MagicMock(side_effect=OSError("boom")))):
        result = pm.update_changelog_story_shipped("Day 1", "v2.0", "story")

    assert result is False


# ---------------------------------------------------------------------------
# ci_generator integration — _maybe_snapshot_roadmap
# ---------------------------------------------------------------------------


def test_ci_generator_calls_snapshot_on_apply(tmp_path):
    import ci_generator

    with patch("ci_generator._load_config") as mock_cfg, \
         patch("ci_generator._maybe_snapshot_roadmap") as mock_snap:
        mock_cfg.return_value.cron.pace_pipeline = "0 5 * * *"
        mock_cfg.return_value.cron.planner_pipeline = "0 8 * * 1"
        mock_cfg.return_value.ci_type = "github"
        ci_generator.generate(apply=True)

    mock_snap.assert_called_once()


def test_ci_generator_skips_snapshot_on_check(tmp_path):
    import ci_generator

    with patch("ci_generator._load_config") as mock_cfg, \
         patch("ci_generator._maybe_snapshot_roadmap") as mock_snap:
        mock_cfg.return_value.cron.pace_pipeline = "0 5 * * *"
        mock_cfg.return_value.cron.planner_pipeline = "0 8 * * 1"
        mock_cfg.return_value.ci_type = "github"
        ci_generator.generate(apply=False, check=True)

    mock_snap.assert_not_called()
