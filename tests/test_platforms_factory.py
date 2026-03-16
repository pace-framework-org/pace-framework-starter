"""Tests for pace/platforms/__init__.py — adapter factory functions."""
import os
from unittest.mock import patch, MagicMock

import pytest

import platforms
from platforms.local import LocalCIAdapter, LocalTrackerAdapter
from config import load_config


@pytest.fixture(autouse=True)
def clear_cache():
    load_config.cache_clear()
    yield
    load_config.cache_clear()


def _mock_cfg(ci_type="github", tracker_type="github"):
    cfg = MagicMock()
    cfg.ci_type = ci_type
    cfg.tracker_type = tracker_type
    return cfg


def test_get_ci_adapter_github():
    with patch("config.load_config", return_value=_mock_cfg("github")), \
         patch.dict(os.environ, {"GITHUB_TOKEN": "tok", "GITHUB_REPOSITORY": "org/repo"}):
        adapter = platforms.get_ci_adapter()
    from platforms.github import GitHubCIAdapter
    assert isinstance(adapter, GitHubCIAdapter)


def test_get_ci_adapter_gitlab():
    with patch("config.load_config", return_value=_mock_cfg("gitlab")), \
         patch.dict(os.environ, {"GITLAB_TOKEN": "tok", "GITLAB_PROJECT": "grp/proj"}):
        adapter = platforms.get_ci_adapter()
    from platforms.gitlab import GitLabCIAdapter
    assert isinstance(adapter, GitLabCIAdapter)


def test_get_ci_adapter_bitbucket():
    with patch("config.load_config", return_value=_mock_cfg("bitbucket")), \
         patch.dict(os.environ, {
             "BITBUCKET_API_TOKEN": "tok",
             "BITBUCKET_WORKSPACE": "ws",
             "BITBUCKET_REPO_SLUG": "repo",
         }):
        adapter = platforms.get_ci_adapter()
    from platforms.bitbucket import BitbucketCIAdapter
    assert isinstance(adapter, BitbucketCIAdapter)


def test_get_ci_adapter_jenkins():
    with patch("config.load_config", return_value=_mock_cfg("jenkins")), \
         patch.dict(os.environ, {
             "JENKINS_URL": "http://jenkins",
             "JENKINS_USER": "admin",
             "JENKINS_TOKEN": "tok",
             "JENKINS_JOB_NAME": "pace-job",
         }):
        adapter = platforms.get_ci_adapter()
    from platforms.jenkins import JenkinsCIAdapter
    assert isinstance(adapter, JenkinsCIAdapter)


def test_get_ci_adapter_local():
    with patch("config.load_config", return_value=_mock_cfg("local")):
        adapter = platforms.get_ci_adapter()
    assert isinstance(adapter, LocalCIAdapter)


def test_get_ci_adapter_unknown_returns_local():
    with patch("config.load_config", return_value=_mock_cfg("unknown-platform")):
        adapter = platforms.get_ci_adapter()
    assert isinstance(adapter, LocalCIAdapter)


def test_get_tracker_adapter_jira():
    with patch("config.load_config", return_value=_mock_cfg(tracker_type="jira")), \
         patch.dict(os.environ, {
             "JIRA_URL": "https://jira.example.com",
             "JIRA_EMAIL": "user@example.com",
             "JIRA_TOKEN": "tok",
             "JIRA_PROJECT_KEY": "PROJ",
         }):
        adapter = platforms.get_tracker_adapter()
    from platforms.jira import JiraTrackerAdapter
    assert isinstance(adapter, JiraTrackerAdapter)


def test_get_tracker_adapter_github():
    with patch("config.load_config", return_value=_mock_cfg(tracker_type="github")), \
         patch.dict(os.environ, {"GITHUB_TOKEN": "tok", "GITHUB_REPOSITORY": "org/repo"}):
        adapter = platforms.get_tracker_adapter()
    from platforms.github import GitHubTrackerAdapter
    assert isinstance(adapter, GitHubTrackerAdapter)


def test_get_tracker_adapter_gitlab():
    with patch("config.load_config", return_value=_mock_cfg(tracker_type="gitlab")), \
         patch.dict(os.environ, {"GITLAB_TOKEN": "tok", "GITLAB_PROJECT": "grp/proj"}):
        adapter = platforms.get_tracker_adapter()
    from platforms.gitlab import GitLabTrackerAdapter
    assert isinstance(adapter, GitLabTrackerAdapter)


def test_get_tracker_adapter_bitbucket():
    with patch("config.load_config", return_value=_mock_cfg(tracker_type="bitbucket")), \
         patch.dict(os.environ, {
             "BITBUCKET_API_TOKEN": "tok",
             "BITBUCKET_WORKSPACE": "ws",
             "BITBUCKET_REPO_SLUG": "repo",
         }):
        adapter = platforms.get_tracker_adapter()
    from platforms.bitbucket import BitbucketTrackerAdapter
    assert isinstance(adapter, BitbucketTrackerAdapter)


def test_get_tracker_adapter_local():
    with patch("config.load_config", return_value=_mock_cfg(tracker_type="local")):
        adapter = platforms.get_tracker_adapter()
    assert isinstance(adapter, LocalTrackerAdapter)


def test_get_tracker_adapter_jenkins_falls_back_to_local():
    with patch("config.load_config", return_value=_mock_cfg(tracker_type="jenkins")):
        adapter = platforms.get_tracker_adapter()
    assert isinstance(adapter, LocalTrackerAdapter)
