"""PACE Branching Adapter — release/sprint/story branch hierarchy management.

Creates and validates the branch hierarchy before each PACE run:

    main
    └── pace/release-{release-name}     # e.g. pace/release-v1.0.0
        └── pace/sprint-{N}             # e.g. pace/sprint-3
            └── pace/story-{issue}      # e.g. pace/story-32

All create_branch calls are idempotent — existing branches are left unchanged.
Only missing levels are created. The adapter is safe to call on every pipeline
run without risk of overwriting existing work.

Usage:
    from branching import get_branching_adapter
    adapter = get_branching_adapter()
    adapter.ensure_hierarchy("v1.0.0", sprint_num=3)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

BRANCH_MAIN = "main"


# ---------------------------------------------------------------------------
# Branch name helpers
# ---------------------------------------------------------------------------

def release_branch(release_name: str) -> str:
    """Return the canonical release branch name: pace/release-{name}."""
    return f"pace/release-{release_name}"


def sprint_branch(sprint_num: int) -> str:
    """Return the canonical sprint branch name: pace/sprint-{N}."""
    return f"pace/sprint-{sprint_num}"


def story_branch(issue_number: int) -> str:
    """Return the canonical story branch name: pace/story-{issue}."""
    return f"pace/story-{issue_number}"


def current_sprint_num(day: int, sprint_days: int) -> int:
    """Derive the sprint number from the current day and sprint length."""
    import math
    return max(1, math.ceil(day / sprint_days))


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BranchingAdapter(ABC):
    """Platform-agnostic interface for branch and PR management."""

    @abstractmethod
    def get_branch_sha(self, branch: str) -> str | None:
        """Return HEAD SHA of branch, or None if it doesn't exist."""

    @abstractmethod
    def create_branch(self, new_branch: str, from_branch: str) -> None:
        """Create new_branch from from_branch if new_branch does not exist.

        Must be a no-op if new_branch already exists.
        """

    @abstractmethod
    def create_pull_request(
        self,
        head: str,
        base: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> str:
        """Open a pull request from head → base. Returns the PR URL."""

    def ensure_hierarchy(self, release_name: str, sprint_num: int) -> None:
        """Idempotently create the full branch hierarchy for a release/sprint.

        Creates in order:
            pace/release-{name}   ← main
            pace/sprint-{N}       ← pace/release-{name}

        Any level that already exists is skipped. Missing levels are created
        from their parent. Story branches (pace/story-{issue}) are created
        on-demand by _setup_story_branch() in orchestrator.py.
        """
        if not self.get_branch_sha(BRANCH_MAIN):
            print("[Branching] Cannot resolve 'main' branch SHA — skipping hierarchy.")
            return

        # pace/release-{name} ← main
        rel = release_branch(release_name)
        if not self.get_branch_sha(rel):
            print(f"[Branching] Creating '{rel}' from '{BRANCH_MAIN}'")
            self.create_branch(rel, BRANCH_MAIN)
        else:
            print(f"[Branching] '{rel}' already exists — skipping")

        # pace/sprint-{N} ← pace/release-{name}
        sprint = sprint_branch(sprint_num)
        if not self.get_branch_sha(sprint):
            print(f"[Branching] Creating '{sprint}' from '{rel}'")
            self.create_branch(sprint, rel)
        else:
            print(f"[Branching] '{sprint}' already exists — skipping")

        print(
            f"[Branching] Hierarchy ready: "
            f"{BRANCH_MAIN} → {rel} → {sprint}"
        )


# ---------------------------------------------------------------------------
# Local (no-op) adapter
# ---------------------------------------------------------------------------

class LocalBranchingAdapter(BranchingAdapter):
    """No-op adapter for local development (platform.ci: local)."""

    def get_branch_sha(self, branch: str) -> str | None:
        return "local"

    def create_branch(self, new_branch: str, from_branch: str) -> None:
        print(f"[Branching] local mode — skipping branch creation: {new_branch}")

    def create_pull_request(
        self,
        head: str,
        base: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> str:
        print(f"[Branching] local mode — skipping PR: {head} → {base} | {title}")
        return ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_branching_adapter() -> BranchingAdapter:
    """Return the platform-appropriate BranchingAdapter from config."""
    from config import load_config
    cfg = load_config()
    if cfg.ci_type == "github":
        from platforms.github import GitHubBranchingAdapter
        return GitHubBranchingAdapter(
            token=os.environ.get("GITHUB_TOKEN", ""),
            repo_name=os.environ.get("GITHUB_REPOSITORY", ""),
        )
    if cfg.ci_type == "gitlab":
        from platforms.gitlab import GitLabBranchingAdapter
        return GitLabBranchingAdapter(
            url=os.environ.get("GITLAB_URL", "https://gitlab.com"),
            token=os.environ.get("GITLAB_TOKEN", ""),
            project=os.environ.get("GITLAB_PROJECT", ""),
        )
    if cfg.ci_type == "bitbucket":
        from platforms.bitbucket import BitbucketBranchingAdapter
        return BitbucketBranchingAdapter(
            token=os.environ.get("BITBUCKET_API_TOKEN", ""),
            workspace=os.environ.get("BITBUCKET_WORKSPACE", ""),
            repo_slug=os.environ.get("BITBUCKET_REPO_SLUG", ""),
        )
    print(
        f"[Branching] No BranchingAdapter implemented for platform '{cfg.ci_type}' — "
        "using local no-op adapter."
    )
    return LocalBranchingAdapter()
