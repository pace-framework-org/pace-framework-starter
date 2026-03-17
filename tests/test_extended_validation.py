"""Tests for Item 16: Pre-run Configuration Validation (Extended) (Sprint 6.3)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))


# ---------------------------------------------------------------------------
# config_tester._validate_plan_files
# ---------------------------------------------------------------------------

def _make_releases_raw(name: str, status: str, plan_file: str) -> dict:
    return {"releases": [{"name": name, "status": status, "plan_file": plan_file,
                          "release_days": 10, "sprint_days": 5}]}


def test_validate_plan_files_warns_no_plan_file_for_active(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    raw = _make_releases_raw("v1.0", "active", "")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert any("no plan_file" in w for w in r.warnings)


def test_validate_plan_files_warns_missing_file(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    raw = _make_releases_raw("v1.0", "active", "releases/v1.0/plan.yaml")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert any("does not exist" in w for w in r.warnings)


def test_validate_plan_files_errors_invalid_yaml(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text("not: valid: yaml: {{{")
    raw = _make_releases_raw("v1.0", "active", "plan.yaml")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert any("YAML parse error" in e for e in r.errors)


def test_validate_plan_files_warns_missing_release_field(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({"stories": []}))
    raw = _make_releases_raw("v1.0", "active", "plan.yaml")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert any("missing 'release' field" in w for w in r.warnings)


def test_validate_plan_files_warns_no_stories_or_days(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({"release": "v1.0"}))
    raw = _make_releases_raw("v1.0", "active", "plan.yaml")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert any("neither" in w for w in r.warnings)


def test_validate_plan_files_clean(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump({
        "release": "v1.0",
        "stories": [{"id": "story-1", "title": "x", "status": "pending"}],
    }))
    raw = _make_releases_raw("v1.0", "active", "plan.yaml")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert r.errors == [] and r.warnings == []


def test_validate_plan_files_skips_planned_status(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    # planned release with no plan_file — should NOT warn
    raw = _make_releases_raw("v2.0", "planned", "")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert r.warnings == []


def test_validate_plan_files_checks_completed_status(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    # completed release with no plan_file — SHOULD warn
    raw = _make_releases_raw("v1.0", "completed", "")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r)
    assert any("no plan_file" in w for w in r.warnings)


def test_validate_plan_files_noop_no_releases(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    r = ConfigTestResult()
    _validate_plan_files({}, r)
    assert r.errors == [] and r.warnings == []


# ---------------------------------------------------------------------------
# config_tester._validate_plan_files — release_filter
# ---------------------------------------------------------------------------

def test_validate_plan_files_release_filter_skips_others(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    # v1.0 has no plan_file (would warn), but we filter to v2.0 which is fine
    plan_file = tmp_path / "v2_plan.yaml"
    plan_file.write_text(yaml.dump({"release": "v2.0", "stories": []}))
    raw = {"releases": [
        {"name": "v1.0", "status": "active", "plan_file": "",
         "release_days": 10, "sprint_days": 5},
        {"name": "v2.0", "status": "active", "plan_file": "v2_plan.yaml",
         "release_days": 10, "sprint_days": 5},
    ]}
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r, release_filter="v2.0")
    assert r.warnings == []


def test_validate_plan_files_release_filter_targets_named(tmp_path):
    from config_tester import _validate_plan_files, ConfigTestResult
    raw = _make_releases_raw("v1.0", "active", "")
    r = ConfigTestResult()
    with patch("config_tester._REPO_ROOT", tmp_path):
        _validate_plan_files(raw, r, release_filter="v1.0")
    assert any("no plan_file" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# --strict mode (tested via run_config_test + direct logic)
# ---------------------------------------------------------------------------

def test_strict_mode_promotes_warnings_to_errors():
    from config_tester import ConfigTestResult
    r = ConfigTestResult()
    r.warn("something smells")
    r.warn("another warning")
    # Simulate --strict promotion
    r.errors.extend(r.warnings)
    r.warnings.clear()
    assert len(r.errors) == 2
    assert r.warnings == []
    assert r.exit_code == 2


def test_strict_exit_code_is_two_on_warnings():
    from config_tester import ConfigTestResult
    r = ConfigTestResult()
    r.warn("a warning")
    # Without strict: exit code 1
    assert r.exit_code == 1
    # After strict promotion: exit code 2
    r.errors.extend(r.warnings)
    r.warnings.clear()
    assert r.exit_code == 2


def test_run_config_test_accepts_release_filter(tmp_path):
    """run_config_test passes release_filter to _validate_plan_files without error."""
    from config_tester import run_config_test, ConfigTestResult
    # A non-existent config file → early return with error, but no TypeError
    result = run_config_test(tmp_path / "missing.yaml", release_filter="v1.0")
    assert any("not found" in e for e in result.errors)
