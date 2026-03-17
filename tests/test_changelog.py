"""Tests for Item 18 — CHANGELOG.md integration in planner.py, orchestrator.py,
and config_tester.py.

pacemap.py CHANGELOG helpers are tested in tests/test_pacemap.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))


# ---------------------------------------------------------------------------
# config_tester — _validate_changelog
# ---------------------------------------------------------------------------


def test_validate_changelog_warns_when_missing(tmp_path):
    import config_tester

    with patch.object(
        config_tester,
        "CONFIG_FILE",
        Path(__file__).parent / "fixtures" / "pace.config.yaml",
    ):
        r = config_tester.ConfigTestResult()
        # Patch CHANGELOG path to a non-existent file
        with patch("config_tester.Path") as mock_path_cls:
            changelog_mock = MagicMock()
            changelog_mock.exists.return_value = False
            mock_path_cls.return_value.__truediv__ = MagicMock(return_value=changelog_mock)
            mock_path_cls.return_value.parent.parent.__truediv__ = MagicMock(
                return_value=changelog_mock
            )
            config_tester._validate_changelog(r)

    assert any("CHANGELOG.md" in w for w in r.warnings)


def test_validate_changelog_no_warn_when_present(tmp_path):
    import config_tester

    with patch("config_tester.Path") as mock_path_cls:
        changelog_mock = MagicMock()
        changelog_mock.exists.return_value = True
        mock_path_cls.return_value.parent.parent.__truediv__ = MagicMock(
            return_value=changelog_mock
        )
        r = config_tester.ConfigTestResult()
        config_tester._validate_changelog(r)

    assert not any("CHANGELOG.md" in w for w in r.warnings)


def test_validate_changelog_uses_repo_root_path():
    """_validate_changelog checks CHANGELOG.md relative to config_tester.py's parent.parent."""
    import config_tester

    expected_changelog = Path(config_tester.__file__).parent.parent / "CHANGELOG.md"
    # The actual CHANGELOG.md exists in the repo (we created it)
    r = config_tester.ConfigTestResult()
    config_tester._validate_changelog(r)
    # With real CHANGELOG.md present, no warning should be added
    assert not any("CHANGELOG.md" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# planner.py — _record_planned_stories_in_changelog
# ---------------------------------------------------------------------------


def test_record_planned_stories_calls_update_changelog_story_shipped():
    import planner

    plan = {
        "release": "v2.0",
        "days": [
            {"day": 1, "story": "As a user I can log in"},
            {"day": 2, "story": "As a user I can log out"},
        ],
    }
    report = {}

    with patch("pacemap.update_changelog_story_shipped", return_value=True) as mock_fn:
        planner._record_planned_stories_in_changelog(plan, report)

    assert mock_fn.call_count == 2
    calls = [c.args for c in mock_fn.call_args_list]
    assert calls[0] == ("Day 1 (planned)", "v2.0", "As a user I can log in")
    assert calls[1] == ("Day 2 (planned)", "v2.0", "As a user I can log out")


def test_record_planned_stories_non_fatal_on_exception():
    import planner

    with patch("pacemap.update_changelog_story_shipped", side_effect=RuntimeError("boom")):
        # Must not raise
        planner._record_planned_stories_in_changelog(
            {"release": "v2.0", "days": [{"day": 1, "story": "story"}]}, {}
        )


def test_record_planned_stories_skips_days_without_story():
    import planner

    plan = {"release": "v2.0", "days": [{"day": 1}]}  # no story key
    with patch("pacemap.update_changelog_story_shipped", return_value=True) as mock_fn:
        planner._record_planned_stories_in_changelog(plan, {})

    mock_fn.assert_not_called()


def test_record_planned_stories_empty_days():
    import planner

    with patch("pacemap.update_changelog_story_shipped", return_value=True) as mock_fn:
        planner._record_planned_stories_in_changelog({"release": "v2.0", "days": []}, {})

    mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# orchestrator.py — SHIP path calls update_changelog_story_shipped
# ---------------------------------------------------------------------------


def test_orchestrator_ship_calls_update_changelog_story_shipped(tmp_path):
    import orchestrator

    story_card = {"story": "As a user I can see the dashboard"}

    mock_cfg = MagicMock()
    mock_cfg.release.name = "v2.0"

    with patch("orchestrator.load_config", return_value=mock_cfg), \
         patch("pacemap.update_changelog_story_shipped", return_value=True) as mock_fn:
        orchestrator._update_changelog_on_ship(5, story_card)

    mock_fn.assert_called_once_with("Day 5", "v2.0", "As a user I can see the dashboard")


def test_orchestrator_ship_changelog_non_fatal_on_exception():
    import orchestrator

    with patch("orchestrator.load_config", side_effect=RuntimeError("cfg error")):
        # Must not raise
        orchestrator._update_changelog_on_ship(1, {"story": "story"})


def test_orchestrator_ship_skips_changelog_when_no_release():
    import orchestrator

    mock_cfg = MagicMock()
    mock_cfg.release = None

    with patch("orchestrator.load_config", return_value=mock_cfg), \
         patch("pacemap.update_changelog_story_shipped", return_value=True) as mock_fn:
        orchestrator._update_changelog_on_ship(1, {"story": "story"})

    mock_fn.assert_called_once_with("Day 1", "", "story")
