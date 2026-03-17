"""Tests for Item 15: plan.yaml Versioning & Story Naming (Sprint 6.3)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
sys.path.insert(0, str(Path(__file__).parent.parent / "pace" / "migrations"))


# ---------------------------------------------------------------------------
# schemas.py — PLAN_SCHEMA
# ---------------------------------------------------------------------------

def test_plan_schema_exists():
    from schemas import PLAN_SCHEMA
    assert "release" in PLAN_SCHEMA["properties"]
    assert "stories" in PLAN_SCHEMA["properties"]


def test_plan_schema_required_fields():
    from schemas import PLAN_SCHEMA
    assert set(PLAN_SCHEMA["required"]) == {"release", "stories"}


def test_plan_schema_story_item_required():
    from schemas import PLAN_SCHEMA
    story_schema = PLAN_SCHEMA["properties"]["stories"]["items"]
    assert set(story_schema["required"]) == {"id", "title", "status"}


def test_plan_schema_status_enum():
    from schemas import PLAN_SCHEMA
    status_enum = PLAN_SCHEMA["properties"]["stories"]["items"]["properties"]["status"]["enum"]
    assert set(status_enum) == {"pending", "in_progress", "shipped", "hold"}


# ---------------------------------------------------------------------------
# planner.py — _iter_stories
# ---------------------------------------------------------------------------

def test_iter_stories_new_format():
    import planner
    plan = {"stories": [
        {"id": "story-1", "title": "First", "status": "shipped"},
        {"id": "story-2", "title": "Second", "status": "pending"},
    ]}
    result = list(planner._iter_stories(plan))
    assert result[0] == (1, plan["stories"][0])
    assert result[1] == (2, plan["stories"][1])


def test_iter_stories_legacy_format():
    import planner
    plan = {"days": [
        {"day": 1, "target": "First"},
        {"day": 2, "target": "Second"},
    ]}
    result = list(planner._iter_stories(plan))
    assert result[0] == (1, plan["days"][0])
    assert result[1] == (2, plan["days"][1])


def test_iter_stories_skips_invalid_ids():
    import planner
    plan = {"stories": [
        {"id": "story-1", "title": "Good"},
        {"id": "bad-id", "title": "Bad"},
        {"id": "story-3", "title": "Good3"},
    ]}
    result = list(planner._iter_stories(plan))
    assert len(result) == 2
    assert result[0][0] == 1
    assert result[1][0] == 3


# ---------------------------------------------------------------------------
# planner.py — _get_replan_boundary
# ---------------------------------------------------------------------------

def test_get_replan_boundary_no_shipped():
    import planner
    stories = [{"status": "pending"}, {"status": "in_progress"}]
    assert planner._get_replan_boundary(stories) == -1


def test_get_replan_boundary_last_shipped():
    import planner
    stories = [
        {"status": "shipped"},
        {"status": "shipped"},
        {"status": "pending"},
    ]
    assert planner._get_replan_boundary(stories) == 1


def test_get_replan_boundary_all_shipped():
    import planner
    stories = [{"status": "shipped"}, {"status": "shipped"}]
    assert planner._get_replan_boundary(stories) == 1


# ---------------------------------------------------------------------------
# planner.py — _backup_plan
# ---------------------------------------------------------------------------

def test_backup_plan_creates_backup(tmp_path):
    import planner
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text("release: v1.0\n")
    with patch("planner.PACE_DIR", tmp_path / ".pace"):
        result = planner._backup_plan(plan_file, "v1.0")
    assert result is not None
    assert result.exists()
    assert result.name.startswith("plan.yaml.bak.")


def test_backup_plan_noop_missing_plan(tmp_path):
    import planner
    with patch("planner.PACE_DIR", tmp_path / ".pace"):
        result = planner._backup_plan(tmp_path / "nonexistent.yaml", "v1.0")
    assert result is None


def test_backup_plan_prunes_old_backups(tmp_path):
    import planner, time
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text("release: v1.0\n")
    backup_dir = tmp_path / ".pace" / "releases" / "v1.0"
    backup_dir.mkdir(parents=True)
    # Create a fake old backup
    old_backup = backup_dir / "plan.yaml.bak.20200101T000000Z"
    old_backup.write_text("old")
    # Set mtime far in the past
    old_time = 0.0
    old_backup.touch()
    import os
    os.utime(old_backup, (old_time, old_time))
    with patch("planner.PACE_DIR", tmp_path / ".pace"):
        planner._backup_plan(plan_file, "v1.0", retention_days=30)
    assert not old_backup.exists()


# ---------------------------------------------------------------------------
# planner.py — run_planner with stories format
# ---------------------------------------------------------------------------

def test_run_planner_stories_preserves_shipped(tmp_path):
    import planner
    plan = {
        "release": "v1.0",
        "stories": [
            {"id": "story-1", "title": "First", "status": "shipped"},
            {"id": "story-2", "title": "Second", "status": "pending"},
        ],
    }
    with patch("planner.PACE_DIR", tmp_path / ".pace"), \
         patch("planner._estimate_day_cost", return_value={
             "day": 2, "predicted_iterations": 5,
             "predicted_cost_usd": 1.5, "reasoning": "medium",
         }) as mock_est:
        report = planner.run_planner(plan, "claude-sonnet-4-6", replan=True)

    # _estimate_day_cost must only be called for story-2 (pending), not story-1 (shipped)
    assert mock_est.call_count == 1
    assert mock_est.call_args[0][1] == 2  # day=2


def test_run_planner_stories_calls_backup(tmp_path):
    import planner
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text("release: v1.0\nstories: []\n")
    plan = {"release": "v1.0", "stories": []}
    with patch("planner.PACE_DIR", tmp_path / ".pace"), \
         patch("planner._backup_plan") as mock_backup:
        planner.run_planner(plan, "claude-sonnet-4-6", replan=True, plan_file=plan_file)
    mock_backup.assert_called_once_with(plan_file, "v1.0")


def test_run_planner_legacy_days_still_works(tmp_path):
    import planner
    plan = {"days": [{"day": 1, "target": "task"}]}
    with patch("planner.PACE_DIR", tmp_path / ".pace"), \
         patch("planner._load_existing_actuals", return_value={}), \
         patch("planner._estimate_day_cost", return_value={
             "day": 1, "predicted_iterations": 5,
             "predicted_cost_usd": 1.0, "reasoning": "simple",
         }):
        report = planner.run_planner(plan, "claude-sonnet-4-6")
    assert report["total_estimated_usd"] == 1.0


# ---------------------------------------------------------------------------
# orchestrator.py — get_day_plan
# ---------------------------------------------------------------------------

def test_get_day_plan_stories_format():
    from orchestrator import get_day_plan
    plan = {"stories": [
        {"id": "story-1", "title": "First task", "status": "pending"},
        {"id": "story-2", "title": "Second task", "status": "pending"},
    ]}
    entry = get_day_plan(plan, 1)
    assert entry["id"] == "story-1"
    assert entry["target"] == "First task"  # aliased from title


def test_get_day_plan_stories_format_with_existing_target():
    from orchestrator import get_day_plan
    plan = {"stories": [
        {"id": "story-1", "title": "Title", "target": "Override", "status": "pending"},
    ]}
    entry = get_day_plan(plan, 1)
    assert entry["target"] == "Override"


def test_get_day_plan_legacy_days():
    from orchestrator import get_day_plan
    plan = {"days": [{"day": 1, "target": "old style"}]}
    entry = get_day_plan(plan, 1)
    assert entry["target"] == "old style"


def test_get_day_plan_raises_not_found():
    from orchestrator import get_day_plan
    with pytest.raises(ValueError, match="story-5"):
        get_day_plan({"stories": []}, 5)


# ---------------------------------------------------------------------------
# config_tester.py — _validate_plan
# ---------------------------------------------------------------------------

def test_validate_plan_warns_missing_release(tmp_path):
    from config_tester import _validate_plan, ConfigTestResult
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({"stories": []}))

    r = ConfigTestResult()
    with patch("config_tester._PLAN_FILE", plan_file):
        _validate_plan(r)

    assert any("release" in w for w in r.warnings)


def test_validate_plan_warns_shipped_without_shipped_at(tmp_path):
    from config_tester import _validate_plan, ConfigTestResult
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({
        "release": "v1.0",
        "stories": [{"id": "story-1", "title": "x", "status": "shipped"}],
    }))

    r = ConfigTestResult()
    with patch("config_tester._PLAN_FILE", plan_file):
        _validate_plan(r)

    assert any("story-1" in w and "shipped_at" in w for w in r.warnings)


def test_validate_plan_clean_plan(tmp_path):
    from config_tester import _validate_plan, ConfigTestResult
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({
        "release": "v1.0",
        "stories": [
            {"id": "story-1", "title": "x", "status": "shipped", "shipped_at": "2026-03-10"},
            {"id": "story-2", "title": "y", "status": "pending"},
        ],
    }))

    r = ConfigTestResult()
    with patch("config_tester._PLAN_FILE", plan_file):
        _validate_plan(r)

    assert r.warnings == []


def test_validate_plan_noop_no_plan_file(tmp_path):
    from config_tester import _validate_plan, ConfigTestResult
    r = ConfigTestResult()
    with patch("config_tester._PLAN_FILE", tmp_path / "nonexistent.yaml"):
        _validate_plan(r)
    assert r.warnings == []


# ---------------------------------------------------------------------------
# Migration: v3_plan_naming
# ---------------------------------------------------------------------------

def test_migration_renames_day_to_story(tmp_path):
    from v3_plan_naming import migrate
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({
        "release": "v1.0",
        "days": [
            {"day": 1, "target": "Bootstrap scaffolding"},
            {"day": 2, "target": "Add auth"},
        ],
    }))

    result = migrate(plan_file, tmp_path / ".pace")
    assert result == 0
    data = yaml.safe_load(plan_file.read_text())
    assert "stories" in data
    assert data["stories"][0]["id"] == "story-1"
    assert data["stories"][1]["id"] == "story-2"


def test_migration_adds_shipped_status(tmp_path):
    from v3_plan_naming import migrate
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({
        "release": "v1.0",
        "days": [{"day": 1, "target": "Bootstrap"}],
    }))
    # Create a handoff.yaml so day-1 counts as shipped
    handoff_dir = tmp_path / ".pace" / "day-1"
    handoff_dir.mkdir(parents=True)
    (handoff_dir / "handoff.yaml").write_text("day: 1\n")

    result = migrate(plan_file, tmp_path / ".pace")
    assert result == 0
    data = yaml.safe_load(plan_file.read_text())
    assert data["stories"][0]["status"] == "shipped"
    assert "shipped_at" in data["stories"][0]


def test_migration_dry_run_no_write(tmp_path):
    from v3_plan_naming import migrate
    plan_file = tmp_path / "plan.yaml"
    original = yaml.dump({"release": "v1.0", "days": [{"day": 1, "target": "x"}]})
    plan_file.write_text(original)

    result = migrate(plan_file, dry_run=True)
    assert result == 0
    assert plan_file.read_text() == original


def test_migration_noop_missing_plan(tmp_path):
    from v3_plan_naming import migrate
    result = migrate(tmp_path / "nonexistent.yaml")
    assert result == 0


def test_migration_noop_already_stories(tmp_path):
    from v3_plan_naming import migrate
    plan_file = tmp_path / "plan.yaml"
    original = yaml.dump({
        "release": "v1.0",
        "stories": [{"id": "story-1", "title": "x", "status": "pending"}],
    })
    plan_file.write_text(original)

    result = migrate(plan_file)
    assert result == 0
    assert plan_file.read_text() == original
