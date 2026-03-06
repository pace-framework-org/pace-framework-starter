"""PACE Platform Factory.

Call get_platform_adapter() to get the correct PlatformAdapter for the
configured platform type. The adapter is selected from pace.config.yaml
(platform.type) and credentials are read from environment variables.

Supported platforms:
    github    — GitHub (default): GITHUB_TOKEN + GITHUB_REPOSITORY
    gitlab    — GitLab:           GITLAB_TOKEN + GITLAB_PROJECT [+ GITLAB_URL]
    bitbucket — Bitbucket Cloud:  BITBUCKET_USER + BITBUCKET_APP_PASSWORD
                                  + BITBUCKET_WORKSPACE + BITBUCKET_REPO_SLUG
    jenkins   — Jenkins:          JENKINS_URL + JENKINS_USER + JENKINS_TOKEN + JENKINS_JOB_NAME
    local     — No platform:      no credentials required
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the pace/ directory importable when this package is used standalone
sys.path.insert(0, str(Path(__file__).parent.parent))

from platforms.base import PlatformAdapter


def get_platform_adapter() -> PlatformAdapter:
    """Instantiate and return the PlatformAdapter for the configured platform.

    Platform type is read from pace.config.yaml → platform.type.
    Credentials are always read from environment variables (never from config).
    """
    from config import load_config
    cfg = load_config()
    platform_type = cfg.platform_type  # "github" | "gitlab" | "bitbucket" | "jenkins" | "local"

    if platform_type == "github":
        from platforms.github import GitHubAdapter
        return GitHubAdapter(
            token=os.environ.get("GITHUB_TOKEN", ""),
            repo_name=os.environ.get("GITHUB_REPOSITORY", ""),
        )

    if platform_type == "gitlab":
        from platforms.gitlab import GitLabAdapter
        return GitLabAdapter(
            url=os.environ.get("GITLAB_URL", "https://gitlab.com"),
            token=os.environ.get("GITLAB_TOKEN", ""),
            project=os.environ.get("GITLAB_PROJECT", ""),
        )

    if platform_type == "bitbucket":
        from platforms.bitbucket import BitbucketAdapter
        return BitbucketAdapter(
            user=os.environ.get("BITBUCKET_USER", ""),
            app_password=os.environ.get("BITBUCKET_APP_PASSWORD", ""),
            workspace=os.environ.get("BITBUCKET_WORKSPACE", ""),
            repo_slug=os.environ.get("BITBUCKET_REPO_SLUG", ""),
        )

    if platform_type == "jenkins":
        from platforms.jenkins import JenkinsAdapter
        return JenkinsAdapter(
            url=os.environ.get("JENKINS_URL", ""),
            user=os.environ.get("JENKINS_USER", ""),
            token=os.environ.get("JENKINS_TOKEN", ""),
            job_name=os.environ.get("JENKINS_JOB_NAME", ""),
        )

    # "local" or any unrecognised value — safe no-op adapter
    from platforms.local import LocalAdapter
    return LocalAdapter()


__all__ = ["PlatformAdapter", "get_platform_adapter"]
