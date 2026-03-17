"""Tests for Item 14: Multi-Release Configuration (Sprint 6.2)."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(raw_yaml: str, tmp_path: Path):
    """Write a pace.config.yaml to tmp_path and return a load_config() result."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config import _load_config_from_path  # noqa: PLC0415
    cfg_file = tmp_path / "pace.config.yaml"
    cfg_file.write_text(textwrap.dedent(raw_yaml))
    return _load_config_from_path(cfg_file)


def _run_tester(raw_yaml: str, tmp_path: Path):
    """Run config_tester._validate_releases on raw_yaml; return ConfigTestResult."""
    import sys
    import yaml
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config_tester import _validate_releases, ConfigTestResult  # noqa: PLC0415
    raw = yaml.safe_load(textwrap.dedent(raw_yaml)) or {}
    r = ConfigTestResult()
    _validate_releases(raw, r)
    return r


# ---------------------------------------------------------------------------
# ReleaseConfig dataclass
# ---------------------------------------------------------------------------

def test_release_config_has_plan_file_and_status():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config import ReleaseConfig  # noqa: PLC0415
    rc = ReleaseConfig(name="v2.0", release_days=60, sprint_days=14,
                       plan_file=".pace/releases/v2.0/plan.yaml", status="completed")
    assert rc.plan_file == ".pace/releases/v2.0/plan.yaml"
    assert rc.status == "completed"


def test_release_config_defaults():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config import ReleaseConfig  # noqa: PLC0415
    rc = ReleaseConfig(name="v1.0")
    assert rc.status == "active"
    assert rc.plan_file == ""


# ---------------------------------------------------------------------------
# PaceConfig.active_release property
# ---------------------------------------------------------------------------

def _make_pace_config(releases):
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    import config as _cfg  # noqa: PLC0415
    return _cfg.PaceConfig(
        product_name="Test", product_description="test", github_org="org",
        sprint_duration_days=14, source_dirs=[], docs_dir=None,
        tech=_cfg.TechConfig(
            primary_language="Python 3.12", secondary_language=None,
            ci_system="GitHub Actions", test_command="pytest", build_command=None,
        ),
        ci_type="github", tracker_type="github",
        llm=_cfg.LLMConfig(provider="anthropic", model="claude-sonnet-4-6",
                            analysis_model="claude-sonnet-4-6", base_url=None),
        cost_control=_cfg.CostControlConfig(),
        forge=_cfg.ForgeConfig(),
        advisory_push_to_issues=False,
        releases=releases,
    )


def test_active_release_returns_active_entry():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config import ReleaseConfig  # noqa: PLC0415
    cfg = _make_pace_config([
        ReleaseConfig(name="v1.0", status="completed"),
        ReleaseConfig(name="v2.0", status="active"),
    ])
    assert cfg.active_release.name == "v2.0"


def test_active_release_none_when_releases_empty():
    cfg = _make_pace_config([])
    assert cfg.active_release is None


def test_active_release_none_when_releases_is_none():
    cfg = _make_pace_config(None)
    assert cfg.active_release is None


def test_active_release_raises_on_multiple_active():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config import ReleaseConfig  # noqa: PLC0415
    cfg = _make_pace_config([
        ReleaseConfig(name="v1.0", status="active"),
        ReleaseConfig(name="v2.0", status="active"),
    ])
    with pytest.raises(ValueError, match="2 releases have status: active"):
        _ = cfg.active_release


def test_active_release_env_var_override():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config import ReleaseConfig  # noqa: PLC0415
    cfg = _make_pace_config([
        ReleaseConfig(name="v1.0", status="completed"),
        ReleaseConfig(name="v2.0", status="active"),
    ])
    with patch.dict(os.environ, {"PACE_RELEASE": "v1.0"}):
        assert cfg.active_release.name == "v1.0"


def test_active_release_env_var_no_match_returns_none():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))
    from config import ReleaseConfig  # noqa: PLC0415
    cfg = _make_pace_config([ReleaseConfig(name="v2.0", status="active")])
    with patch.dict(os.environ, {"PACE_RELEASE": "v99.0"}):
        assert cfg.active_release is None


# ---------------------------------------------------------------------------
# config.py parser — releases: list
# ---------------------------------------------------------------------------

_BASE_YAML = """
product:
  name: "TestProduct"
  description: "A test product."
  github_org: "test-org"
sprint:
  duration_days: 14
source:
  dirs:
    - name: src
      path: src/
      language: python
      description: main
tech:
  languages: [python]
  frameworks: []
  test_framework: pytest
platform:
  ci: github
  tracker: github
llm:
  model: claude-sonnet-4-6
  api_key: "test-key"
"""


def test_load_config_parses_releases_list(tmp_path):
    yaml_text = _BASE_YAML + textwrap.dedent("""
    releases:
      - name: "v2.0"
        release_days: 90
        sprint_days: 14
        status: completed
      - name: "v3.0"
        release_days: 60
        sprint_days: 7
        plan_file: ".pace/releases/v3.0/plan.yaml"
        status: active
    """)
    cfg = _make_config(yaml_text, tmp_path)
    assert cfg.releases is not None
    assert len(cfg.releases) == 2
    assert cfg.active_release.name == "v3.0"
    assert cfg.releases[0].status == "completed"
    assert cfg.releases[1].plan_file == ".pace/releases/v3.0/plan.yaml"


def test_load_config_legacy_release_key_wrapped(tmp_path):
    yaml_text = _BASE_YAML + textwrap.dedent("""
    release:
      name: "v1.0"
      release_days: 30
      sprint_days: 7
    """)
    cfg = _make_config(yaml_text, tmp_path)
    assert cfg.releases is not None
    assert len(cfg.releases) == 1
    assert cfg.releases[0].name == "v1.0"
    assert cfg.releases[0].status == "active"
    assert cfg.active_release.name == "v1.0"


def test_load_config_no_release_section(tmp_path):
    cfg = _make_config(_BASE_YAML, tmp_path)
    assert cfg.releases is None
    assert cfg.active_release is None


# ---------------------------------------------------------------------------
# config_tester._validate_releases
# ---------------------------------------------------------------------------

def test_validate_releases_no_section_suggests():
    r = _run_tester("{}", None)
    assert any("releases section is not configured" in s for s in r.suggestions)


def test_validate_releases_valid_list_no_errors():
    r = _run_tester("""
    releases:
      - name: v1.0
        release_days: 60
        sprint_days: 7
        status: completed
      - name: v2.0
        release_days: 90
        sprint_days: 14
        status: active
    """, None)
    assert r.errors == []


def test_validate_releases_duplicate_name_error():
    r = _run_tester("""
    releases:
      - name: v1.0
        release_days: 60
        sprint_days: 7
        status: completed
      - name: v1.0
        release_days: 90
        sprint_days: 14
        status: active
    """, None)
    assert any("duplicated" in e for e in r.errors)


def test_validate_releases_sprint_exceeds_release_error():
    r = _run_tester("""
    releases:
      - name: v1.0
        release_days: 10
        sprint_days: 20
        status: active
    """, None)
    assert any("sprint_days" in e and "release_days" in e for e in r.errors)


def test_validate_releases_zero_active_error():
    r = _run_tester("""
    releases:
      - name: v1.0
        release_days: 60
        sprint_days: 7
        status: completed
    """, None)
    assert any("no entry has status: active" in e for e in r.errors)


def test_validate_releases_multiple_active_error():
    r = _run_tester("""
    releases:
      - name: v1.0
        release_days: 60
        sprint_days: 7
        status: active
      - name: v2.0
        release_days: 90
        sprint_days: 14
        status: active
    """, None)
    assert any("2 entries have status: active" in e for e in r.errors)


def test_validate_releases_invalid_status_error():
    r = _run_tester("""
    releases:
      - name: v1.0
        release_days: 60
        sprint_days: 7
        status: unknown
    """, None)
    assert any("invalid" in e for e in r.errors)


def test_validate_releases_legacy_suggests_migration():
    r = _run_tester("""
    release:
      name: v1.0
      release_days: 60
      sprint_days: 7
    """, None)
    assert any("migrate" in s for s in r.suggestions)
    assert r.errors == []


# ---------------------------------------------------------------------------
# Migration script
# ---------------------------------------------------------------------------

def test_migration_converts_release_to_releases(tmp_path):
    import yaml
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace" / "migrations"))
    from v3_multi_release import migrate  # noqa: PLC0415

    cfg_file = tmp_path / "pace.config.yaml"
    cfg_file.write_text(textwrap.dedent("""
    product:
      name: Test
    release:
      name: v1.0
      release_days: 60
      sprint_days: 7
    """))
    result = migrate(cfg_file)
    assert result == 0
    raw = yaml.safe_load(cfg_file.read_text())
    assert "releases" in raw
    assert "release" not in raw
    assert raw["releases"][0]["name"] == "v1.0"
    assert raw["releases"][0]["status"] == "active"


def test_migration_noop_when_already_migrated(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace" / "migrations"))
    from v3_multi_release import migrate  # noqa: PLC0415

    cfg_file = tmp_path / "pace.config.yaml"
    cfg_file.write_text("releases:\n  - name: v1.0\n    status: active\n")
    original = cfg_file.read_text()
    result = migrate(cfg_file)
    assert result == 0
    assert cfg_file.read_text() == original


def test_migration_noop_when_no_release_section(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace" / "migrations"))
    from v3_multi_release import migrate  # noqa: PLC0415

    cfg_file = tmp_path / "pace.config.yaml"
    cfg_file.write_text("product:\n  name: Test\n")
    result = migrate(cfg_file)
    assert result == 0


def test_migration_dry_run_does_not_write(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace" / "migrations"))
    from v3_multi_release import migrate  # noqa: PLC0415

    cfg_file = tmp_path / "pace.config.yaml"
    cfg_file.write_text("release:\n  name: v1.0\n  release_days: 60\n  sprint_days: 7\n")
    original = cfg_file.read_text()
    migrate(cfg_file, dry_run=True)
    assert cfg_file.read_text() == original


def test_migration_preserves_plan_file(tmp_path):
    import yaml
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pace" / "migrations"))
    from v3_multi_release import migrate  # noqa: PLC0415

    cfg_file = tmp_path / "pace.config.yaml"
    cfg_file.write_text(
        "release:\n  name: v1.0\n  release_days: 60\n  sprint_days: 7\n"
        "  plan_file: .pace/releases/v1.0/plan.yaml\n"
    )
    migrate(cfg_file)
    raw = yaml.safe_load(cfg_file.read_text())
    assert raw["releases"][0]["plan_file"] == ".pace/releases/v1.0/plan.yaml"
