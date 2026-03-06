"""PACE Platform Adapter — abstract base class.

All platform-specific integrations (GitHub, GitLab, Jenkins, Local) implement this
interface. The orchestrator only calls methods defined here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class PlatformAdapter(ABC):
    """Abstract interface for all PACE platform integrations.

    Five operations are required:
      1. open_review_pr      — human gate: open a PR/MR for human review
      2. open_escalation_issue — open a ticket/issue when retries are exhausted
      3. wait_for_commit_ci  — poll CI until the commit reaches a terminal state
      4. post_daily_summary  — brief status line to the platform (comment, log, etc.)
      5. write_job_summary   — write the full markdown report to the job/run UI
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
    def open_escalation_issue(self, day: int, day_dir: Path) -> str:
        """Open an escalation issue/ticket when FORGE exhausts all retries.

        Args:
            day:     PACE day number.
            day_dir: Path to .pace/day-N/ directory (contains story/handoff/gate files).

        Returns:
            URL of the opened issue, or empty string if unsupported / failed.
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
            timeout_minutes: Hard timeout before returning `timed_out`.
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
