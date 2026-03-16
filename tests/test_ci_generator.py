"""Tests for pace/ci_generator.py."""
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import ci_generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gha_content(cron: str = "0 9 * * 1-5") -> str:
    return f"""on:
  schedule:
    - cron: "{cron}"
"""


def _make_jenkins_content(cron: str = "0 9 * * 1-5") -> str:
    return f"""pipeline {{
    triggers {{
        cron('{cron}')
    }}
}}"""


def _make_gitlab_content() -> str:
    return "stages:\n  - pace\n\npace:\n  stage: pace\n"


def _make_bitbucket_content() -> str:
    return "image: python:3.12-slim\n\npipelines:\n  custom:\n    pace-daily:\n      - step:\n"


# ---------------------------------------------------------------------------
# _update_cron_in_file
# ---------------------------------------------------------------------------

def test_update_cron_in_file_file_not_found(tmp_path):
    missing = tmp_path / "missing.yml"
    pattern = re.compile(r"(cron\(')([^']+)('\))")
    changed, msg = ci_generator._update_cron_in_file(missing, pattern, "0 8 * * *", 2)
    assert not changed
    assert "not found" in msg


def test_update_cron_in_file_no_match(tmp_path):
    f = tmp_path / "noschedule.yml"
    f.write_text("no cron here\n")
    pattern = re.compile(r"(cron\(')([^']+)('\))")
    changed, msg = ci_generator._update_cron_in_file(f, pattern, "0 8 * * *", 2)
    assert not changed
    assert "no schedule pattern" in msg


def test_update_cron_in_file_already_up_to_date(tmp_path):
    content = _make_jenkins_content("0 9 * * 1-5")
    f = tmp_path / "Jenkinsfile"
    f.write_text(content)
    pattern = re.compile(r"(        cron\(')([^']+)('\))", re.MULTILINE)
    changed, msg = ci_generator._update_cron_in_file(f, pattern, "0 9 * * 1-5", 2)
    assert not changed
    assert "already up to date" in msg


def test_update_cron_in_file_dry_run(tmp_path):
    content = _make_jenkins_content("0 9 * * 1-5")
    f = tmp_path / "Jenkinsfile"
    f.write_text(content)
    pattern = re.compile(r"(        cron\(')([^']+)('\))", re.MULTILINE)
    changed, msg = ci_generator._update_cron_in_file(f, pattern, "0 8 * * *", 2, dry_run=True)
    assert changed
    assert "would update" in msg
    assert f.read_text() == content  # file unchanged


def test_update_cron_in_file_apply(tmp_path):
    content = _make_jenkins_content("0 9 * * 1-5")
    f = tmp_path / "Jenkinsfile"
    f.write_text(content)
    pattern = re.compile(r"(        cron\(')([^']+)('\))", re.MULTILINE)
    changed, msg = ci_generator._update_cron_in_file(f, pattern, "0 8 * * *", 2, dry_run=False)
    assert changed
    assert "updated" in msg
    assert "0 8 * * *" in f.read_text()


# ---------------------------------------------------------------------------
# _update_gha_cron
# ---------------------------------------------------------------------------

def test_update_gha_cron_not_found(tmp_path):
    changed, msg = ci_generator._update_gha_cron(tmp_path / "pace.yml", "0 8 * * *")
    assert not changed
    assert "not found" in msg


def test_update_gha_cron_no_schedule(tmp_path):
    f = tmp_path / "pace.yml"
    f.write_text("on:\n  push:\n    branches: [main]\n")
    changed, msg = ci_generator._update_gha_cron(f, "0 8 * * *")
    assert not changed
    assert "no schedule block" in msg


def test_update_gha_cron_already_up_to_date(tmp_path):
    f = tmp_path / "pace.yml"
    f.write_text(_make_gha_content("0 9 * * 1-5"))
    changed, msg = ci_generator._update_gha_cron(f, "0 9 * * 1-5")
    assert not changed
    assert "already up to date" in msg


def test_update_gha_cron_dry_run(tmp_path):
    f = tmp_path / "pace.yml"
    original = _make_gha_content("0 9 * * 1-5")
    f.write_text(original)
    changed, msg = ci_generator._update_gha_cron(f, "0 8 * * *", dry_run=True)
    assert changed
    assert "would update" in msg
    assert f.read_text() == original  # unchanged


def test_update_gha_cron_apply(tmp_path):
    f = tmp_path / "pace.yml"
    f.write_text(_make_gha_content("0 9 * * 1-5"))
    changed, msg = ci_generator._update_gha_cron(f, "0 8 * * *", dry_run=False)
    assert changed
    assert "0 8 * * *" in f.read_text()


# ---------------------------------------------------------------------------
# _update_gitlab_cron
# ---------------------------------------------------------------------------

def test_update_gitlab_cron_not_found(tmp_path):
    changed, msg = ci_generator._update_gitlab_cron(tmp_path / ".gitlab-ci.yml", "0 9 * * 1-5")
    assert not changed
    assert "not found" in msg


def test_update_gitlab_cron_always_advisory(tmp_path):
    f = tmp_path / ".gitlab-ci.yml"
    f.write_text(_make_gitlab_content())
    changed, msg = ci_generator._update_gitlab_cron(f, "0 9 * * 1-5")
    assert not changed
    assert "GitLab UI" in msg
    assert "0 9 * * 1-5" in msg


# ---------------------------------------------------------------------------
# _update_jenkins_cron
# ---------------------------------------------------------------------------

def test_update_jenkins_cron_not_found(tmp_path):
    changed, msg = ci_generator._update_jenkins_cron(tmp_path / "Jenkinsfile", "0 8 * * *")
    assert not changed
    assert "not found" in msg


def test_update_jenkins_cron_no_trigger(tmp_path):
    f = tmp_path / "Jenkinsfile"
    f.write_text("pipeline { agent any }")
    changed, msg = ci_generator._update_jenkins_cron(f, "0 8 * * *")
    assert not changed
    assert "no cron() trigger" in msg


def test_update_jenkins_cron_already_up_to_date(tmp_path):
    f = tmp_path / "Jenkinsfile"
    f.write_text(_make_jenkins_content("0 9 * * 1-5"))
    changed, msg = ci_generator._update_jenkins_cron(f, "0 9 * * 1-5")
    assert not changed
    assert "already up to date" in msg


def test_update_jenkins_cron_apply(tmp_path):
    f = tmp_path / "Jenkinsfile"
    f.write_text(_make_jenkins_content("0 9 * * 1-5"))
    changed, msg = ci_generator._update_jenkins_cron(f, "0 7 * * *", dry_run=False)
    assert changed
    assert "0 7 * * *" in f.read_text()


# ---------------------------------------------------------------------------
# _update_bitbucket_cron
# ---------------------------------------------------------------------------

def test_update_bitbucket_cron_not_found(tmp_path):
    changed, msg = ci_generator._update_bitbucket_cron(tmp_path / "bb.yml", "0 9 * * 1-5")
    assert not changed
    assert "not found" in msg


def test_update_bitbucket_cron_always_advisory(tmp_path):
    f = tmp_path / "bitbucket-pipelines.yml"
    f.write_text(_make_bitbucket_content())
    changed, msg = ci_generator._update_bitbucket_cron(f, "0 9 * * 1-5")
    assert not changed
    assert "Repository Settings" in msg


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------

def _mock_cfg(ci_type: str, cron_expr: str = "0 9 * * 1-5") -> MagicMock:
    cfg = MagicMock()
    cfg.ci_type = ci_type
    cfg.cron.pace_pipeline = cron_expr
    cfg.cron.planner_pipeline = "0 8 * * 1"
    return cfg


def test_generate_github_both_files_missing(tmp_path, capsys):
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("github")), \
         patch.object(ci_generator, "_GITHUB_PACE_WORKFLOW", tmp_path / "pace.yml"), \
         patch.object(ci_generator, "_GITHUB_PLANNER_WORKFLOW", tmp_path / "planner.yml"):
        result = ci_generator.generate()
    out = capsys.readouterr().out
    assert "not found" in out
    assert result is True  # missing files don't count as out-of-sync


def test_generate_github_in_sync(tmp_path, capsys):
    pace_yml = tmp_path / "pace.yml"
    planner_yml = tmp_path / "planner.yml"
    pace_yml.write_text(_make_gha_content("0 9 * * 1-5"))
    planner_yml.write_text(_make_gha_content("0 8 * * 1"))
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("github")), \
         patch.object(ci_generator, "_GITHUB_PACE_WORKFLOW", pace_yml), \
         patch.object(ci_generator, "_GITHUB_PLANNER_WORKFLOW", planner_yml):
        result = ci_generator.generate()
    assert result is True


def test_generate_github_out_of_sync_check_mode(tmp_path, capsys):
    pace_yml = tmp_path / "pace.yml"
    pace_yml.write_text(_make_gha_content("0 1 * * *"))  # stale cron
    planner_yml = tmp_path / "planner.yml"
    planner_yml.write_text(_make_gha_content("0 8 * * 1"))
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("github")), \
         patch.object(ci_generator, "_GITHUB_PACE_WORKFLOW", pace_yml), \
         patch.object(ci_generator, "_GITHUB_PLANNER_WORKFLOW", planner_yml):
        result = ci_generator.generate(check=True)
    assert result is False


def test_generate_github_apply(tmp_path, capsys):
    pace_yml = tmp_path / "pace.yml"
    pace_yml.write_text(_make_gha_content("0 1 * * *"))
    planner_yml = tmp_path / "planner.yml"
    planner_yml.write_text(_make_gha_content("0 8 * * 1"))
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("github")), \
         patch.object(ci_generator, "_GITHUB_PACE_WORKFLOW", pace_yml), \
         patch.object(ci_generator, "_GITHUB_PLANNER_WORKFLOW", planner_yml):
        result = ci_generator.generate(apply=True)
    assert result is True
    assert "0 9 * * 1-5" in pace_yml.read_text()


def test_generate_gitlab(tmp_path, capsys):
    gitlab_yml = tmp_path / ".gitlab-ci.yml"
    gitlab_yml.write_text(_make_gitlab_content())
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("gitlab")), \
         patch.object(ci_generator, "_GITLAB_CI_FILE", gitlab_yml):
        result = ci_generator.generate()
    out = capsys.readouterr().out
    assert "GitLab UI" in out
    assert result is True  # always in-sync for advisory-only platforms


def test_generate_jenkins_in_sync(tmp_path, capsys):
    jf = tmp_path / "Jenkinsfile"
    jf.write_text(_make_jenkins_content("0 9 * * 1-5"))
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("jenkins")), \
         patch.object(ci_generator, "_JENKINSFILE", jf):
        result = ci_generator.generate()
    assert result is True


def test_generate_jenkins_out_of_sync(tmp_path, capsys):
    jf = tmp_path / "Jenkinsfile"
    jf.write_text(_make_jenkins_content("0 1 * * *"))
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("jenkins")), \
         patch.object(ci_generator, "_JENKINSFILE", jf):
        result = ci_generator.generate(check=True)
    assert result is False


def test_generate_bitbucket(tmp_path, capsys):
    bb_yml = tmp_path / "bitbucket-pipelines.yml"
    bb_yml.write_text(_make_bitbucket_content())
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("bitbucket")), \
         patch.object(ci_generator, "_BITBUCKET_PIPELINES_FILE", bb_yml):
        result = ci_generator.generate()
    out = capsys.readouterr().out
    assert "Repository Settings" in out
    assert result is True


def test_generate_unknown_ci_type(capsys):
    with patch.object(ci_generator, "_load_config", return_value=_mock_cfg("local")):
        result = ci_generator.generate()
    out = capsys.readouterr().out
    assert "Unknown ci_type" in out


def test_generate_loads_real_config():
    # Smoke test — just ensure _load_config() doesn't raise with the real config
    cfg = ci_generator._load_config()
    assert hasattr(cfg, "ci_type")
    assert hasattr(cfg, "cron")
