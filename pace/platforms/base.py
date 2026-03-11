"""PACE Platform Adapter — abstract base classes.

Two separate adapters are required for each deployment:

  CIAdapter      — CI/CD and Git-hosting integration (PRs/MRs, CI polling,
                   job summaries).  Implementations: GitHub, GitLab, Bitbucket,
                   Jenkins, Local.

  TrackerAdapter — Sprint-tracker / issue-platform integration (HOLD escalations,
                   advisory findings).  Implementations: Jira, GitHub Issues,
                   GitLab Issues, Bitbucket Issues, Local.

This two-adapter design lets you mix platforms (e.g. Bitbucket CI + Jira tracker)
without coupling them together.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class CIAdapter(ABC):
    """Abstract interface for CI/CD and Git-hosting integrations.

    Required operations:
      1. open_review_pr     — human gate: open a PR/MR for human review
      2. wait_for_commit_ci — poll CI until the commit reaches a terminal state
      3. post_daily_summary — brief status line to the platform
      4. write_job_summary  — write the full markdown report to the job/run UI
    """

    @abstractmethod
    def open_review_pr(self, day: int, pace_dir: Path) -> str:
        """Open a review PR or MR for a human gate day.

        Args:
            day:      PACE day number (used for branch name and title).
            pace_dir: Path to the .pace/ directory (for reading prior gate reports).

        Returns:
            URL of the opened PR/MR, or empty string if unsupported / failed.
        """

    @abstractmethod
    def wait_for_commit_ci(
        self,
        sha: str,
        timeout_minutes: int = 15,
        poll_interval: int = 20,
    ) -> dict:
        """Poll CI until the given commit SHA reaches a terminal state.

        Args:
            sha:             Git commit SHA to watch.
            timeout_minutes: Hard timeout before returning ``timed_out``.
            poll_interval:   Seconds between poll requests.

        Returns:
            Dict with keys:
              conclusion: "success" | "failure" | "cancelled" | "timed_out"
                          | "no_runs" | "timeout"
              url:        URL of the CI run (may be empty)
              name:       Name of the CI job/pipeline (may be empty)
              sha:        Full commit SHA
        """

    @abstractmethod
    def post_daily_summary(self, day: int, gate_report: dict) -> None:
        """Post a one-line daily status to the platform (comment, annotation, log).

        This is a best-effort notification; failures should be caught internally.
        """

    @abstractmethod
    def write_job_summary(self, markdown: str) -> None:
        """Write the full markdown job report to the platform's summary interface.

        For GitHub: appends to $GITHUB_STEP_SUMMARY.
        For GitLab: appends to $CI_JOB_SUMMARY (15.5+) or writes to a file.
        For Jenkins: writes to a workspace file (jenkins-summary.md).
        For Local:  writes to pace-summary.md in the repo root.
        """

    def set_variable(self, name: str, value: str) -> bool:
        """Set a CI/CD pipeline variable by name.

        Used by the orchestrator to auto-pause the loop (PACE_PAUSED=true)
        after a HOLD exhausts retries, and to update spend-tracking variables.

        Adapters that support mutable pipeline variables (GitHub, GitLab) override
        this method. All others return False and log a message — the orchestrator
        treats a False return as non-fatal.

        Returns:
            True on success, False if unsupported or if the API call fails.
        """
        return False


class TrackerAdapter(ABC):
    """Abstract interface for sprint-tracker / issue-platform integrations.

    Required operations:
      1. open_escalation_issue — open a ticket when FORGE exhausts all retries
      2. push_advisory_items   — open a ticket for backlisted advisory findings
    """

    @abstractmethod
    def open_escalation_issue(self, day: int, day_dir: Path, hold_reason: str = "") -> str:
        """Open an escalation issue/ticket when FORGE exhausts all retries.

        Args:
            day:         PACE day number.
            day_dir:     Path to .pace/day-N/ directory (contains story/handoff/gate files).
            hold_reason: The blocker string accumulated by the orchestrator. When provided,
                         this is used as the primary blocker description. If empty, each
                         adapter falls back to reading the agent artifact files.

        Returns:
            URL of the opened issue, or empty string if unsupported / failed.
        """

    @abstractmethod
    def push_advisory_items(self, day: int, items: list[dict], agent: str) -> str:
        """Open an issue/ticket for newly backlisted advisory findings.

        Called when advisory findings are added to the backlog after a retry
        was given but the issue was not resolved. Only called when
        advisory.push_to_issues is true in pace.config.yaml.

        Args:
            day:   PACE day number the advisory was raised.
            items: List of advisory item dicts (keys: id, day_raised, agent,
                   finding, status) — only the newly added items for this call.
            agent: "SENTINEL" or "CONDUIT" — the reporting agent.

        Returns:
            URL of the opened issue/ticket, or empty string if unsupported / failed.
        """