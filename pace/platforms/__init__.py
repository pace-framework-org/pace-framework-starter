"""PACE Platform Factory.

Call get_ci_adapter() and get_tracker_adapter() to get the correct adapters for
the configured platform types. Adapters are selected from pace.config.yaml:

    platform:
      ci:      github   # CI/CD and Git hosting
      tracker: github   # Sprint tracker / issue platform

Supported CI platforms:      github | gitlab | bitbucket | jenkins | local
Supported tracker platforms: jira | github | gitlab | bitbucket | local

Legacy config (platform.type) is still supported — both adapters default to
that single type when ci/tracker are not explicitly set.

CI environment variables:
    GitHub:    GITHUB_TOKEN + GITHUB_REPOSITORY
    GitLab:    GITLAB_TOKEN + GITLAB_PROJECT [+ GITLAB_URL]
    Bitbucket: BITBUCKET_API_TOKEN + BITBUCKET_WORKSPACE + BITBUCKET_REPO_SLUG
    Jenkins:   JENKINS_URL + JENKINS_USER + JENKINS_TOKEN + JENKINS_JOB_NAME

Tracker environment variables:
    Jira:      JIRA_URL + JIRA_EMAIL + JIRA_TOKEN + JIRA_PROJECT_KEY
    GitHub:    GITHUB_TOKEN + GITHUB_REPOSITORY
    GitLab:    GITLAB_TOKEN + GITLAB_PROJECT [+ GITLAB_URL]
    Bitbucket: BITBUCKET_API_TOKEN + BITBUCKET_WORKSPACE + BITBUCKET_REPO_SLUG
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the pace/ directory importable when this package is used standalone
sys.path.insert(0, str(Path(__file__).parent.parent))

from platforms.base import CIAdapter, TrackerAdapter


def get_ci_adapter() -> CIAdapter:
    """Instantiate and return the CIAdapter for the configured CI platform."""
    from config import load_config
    cfg = load_config()
    ci_type = cfg.ci_type

    if ci_type == "github":
        from platforms.github import GitHubCIAdapter
        return GitHubCIAdapter(
            token=os.environ.get("GITHUB_TOKEN", ""),
            repo_name=os.environ.get("GITHUB_REPOSITORY", ""),
        )

    if ci_type == "gitlab":
        from platforms.gitlab import GitLabCIAdapter
        return GitLabCIAdapter(
            url=os.environ.get("GITLAB_URL", "https://gitlab.com"),
            token=os.environ.get("GITLAB_TOKEN", ""),
            project=os.environ.get("GITLAB_PROJECT", ""),
        )

    if ci_type == "bitbucket":
        from platforms.bitbucket import BitbucketCIAdapter
        return BitbucketCIAdapter(
            token=os.environ.get("BITBUCKET_API_TOKEN", ""),
            workspace=os.environ.get("BITBUCKET_WORKSPACE", ""),
            repo_slug=os.environ.get("BITBUCKET_REPO_SLUG", ""),
        )

    if ci_type == "jenkins":
        from platforms.jenkins import JenkinsCIAdapter
        return JenkinsCIAdapter(
            url=os.environ.get("JENKINS_URL", ""),
            user=os.environ.get("JENKINS_USER", ""),
            token=os.environ.get("JENKINS_TOKEN", ""),
            job_name=os.environ.get("JENKINS_JOB_NAME", ""),
        )

    # "local" or any unrecognised value — safe no-op adapter
    from platforms.local import LocalCIAdapter
    return LocalCIAdapter()


def get_tracker_adapter() -> TrackerAdapter:
    """Instantiate and return the TrackerAdapter for the configured tracker platform."""
    from config import load_config
    cfg = load_config()
    tracker_type = cfg.tracker_type

    if tracker_type == "jira":
        from platforms.jira import JiraTrackerAdapter
        return JiraTrackerAdapter(
            url=os.environ.get("JIRA_URL", ""),
            email=os.environ.get("JIRA_EMAIL", ""),
            token=os.environ.get("JIRA_TOKEN", ""),
            project_key=os.environ.get("JIRA_PROJECT_KEY", ""),
        )

    if tracker_type == "github":
        from platforms.github import GitHubTrackerAdapter
        return GitHubTrackerAdapter(
            token=os.environ.get("GITHUB_TOKEN", ""),
            repo_name=os.environ.get("GITHUB_REPOSITORY", ""),
        )

    if tracker_type == "gitlab":
        from platforms.gitlab import GitLabTrackerAdapter
        return GitLabTrackerAdapter(
            url=os.environ.get("GITLAB_URL", "https://gitlab.com"),
            token=os.environ.get("GITLAB_TOKEN", ""),
            project=os.environ.get("GITLAB_PROJECT", ""),
        )

    if tracker_type == "bitbucket":
        from platforms.bitbucket import BitbucketTrackerAdapter
        return BitbucketTrackerAdapter(
            token=os.environ.get("BITBUCKET_API_TOKEN", ""),
            workspace=os.environ.get("BITBUCKET_WORKSPACE", ""),
            repo_slug=os.environ.get("BITBUCKET_REPO_SLUG", ""),
        )

    # "local", "jenkins", or any unrecognised value — safe no-op adapter
    from platforms.local import LocalTrackerAdapter
    return LocalTrackerAdapter()


__all__ = ["CIAdapter", "TrackerAdapter", "get_ci_adapter", "get_tracker_adapter"]