"""Tests for Item 25: FORGE pre-seeded file hints (_build_file_hints)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from agents.forge import _build_file_hints


def _make_cfg(enabled=True, threshold=0.7, compression_model=None, analysis_model="claude-haiku-4-5-20251001"):
    cfg = MagicMock()
    cfg.forge.file_hints_enabled = enabled
    cfg.forge.file_hints_confidence_threshold = threshold
    cfg.forge.compression_model = compression_model
    cfg.llm.analysis_model = analysis_model
    return cfg


_STORY = {"title": "Add login endpoint", "acceptance": ["POST /login returns 200"]}

_HINTS_YAML = yaml.dump({
    "file_hints": [
        {"path": "pace/auth.py", "confidence": 0.9, "reason": "auth logic"},
        {"path": "tests/test_auth.py", "confidence": 0.85, "reason": "existing auth tests"},
        {"path": "pace/views.py", "confidence": 0.5, "reason": "low confidence"},
    ]
})


# ---------------------------------------------------------------------------
# Test 1: Returns ## File Hints section when engineering.md and manifest exist
# ---------------------------------------------------------------------------

def test_build_file_hints_returns_section_when_configured(tmp_path):
    """_build_file_hints returns a non-empty ## File Hints section."""
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    (context_dir / "engineering.md").write_text("## Modules\npace/auth.py — authentication")
    (context_dir / "context.manifest.yaml").write_text(
        yaml.dump({"files": ["engineering.md", "security.md"]})
    )

    fake_adapter = MagicMock()
    fake_adapter.complete.return_value = f"```yaml\n{_HINTS_YAML}```"

    with (
        patch("agents.forge.get_llm_adapter", return_value=fake_adapter),
        patch("agents.forge.REPO_ROOT", tmp_path),
    ):
        result = _build_file_hints(_STORY, _make_cfg())

    assert "## File Hints" in result
    assert "pace/auth.py" in result
    assert "tests/test_auth.py" in result
    # Low-confidence hint (0.5 < 0.7) should be excluded
    assert "pace/views.py" not in result


# ---------------------------------------------------------------------------
# Test 2: Skipped when file_hints_enabled = False
# ---------------------------------------------------------------------------

def test_build_file_hints_skipped_when_disabled():
    """_build_file_hints returns empty string when globally disabled."""
    result = _build_file_hints(_STORY, _make_cfg(enabled=False))
    assert result == ""


# ---------------------------------------------------------------------------
# Test 3: Skipped when story has disable_file_hints = True
# ---------------------------------------------------------------------------

def test_build_file_hints_skipped_for_story_override():
    """_build_file_hints returns empty string when story sets disable_file_hints."""
    story = {**_STORY, "disable_file_hints": True}
    result = _build_file_hints(story, _make_cfg())
    assert result == ""


# ---------------------------------------------------------------------------
# Test 4: Skipped when engineering.md not in context.manifest.yaml
# ---------------------------------------------------------------------------

def test_build_file_hints_skipped_when_engineering_not_tracked(tmp_path):
    """_build_file_hints returns empty string when engineering.md is not tracked in manifest."""
    context_dir = tmp_path / ".pace" / "context"
    context_dir.mkdir(parents=True)
    (context_dir / "engineering.md").write_text("# Engineering")
    # Manifest exists but engineering.md NOT in files list
    (context_dir / "context.manifest.yaml").write_text(
        yaml.dump({"files": ["security.md", "devops.md"]})
    )

    with patch("agents.forge.REPO_ROOT", tmp_path):
        result = _build_file_hints(_STORY, _make_cfg())

    assert result == ""
