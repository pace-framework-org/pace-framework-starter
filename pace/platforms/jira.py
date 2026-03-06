"""PACE Jira Platform Adapter.

Uses the Jira Cloud REST API v3 to open tickets for HOLD escalations and
advisory findings.

PR/MR creation and CI polling are not natively supported — Jira has no CI
concept. Use this adapter when your team tracks work in Jira but runs CI
on GitHub Actions, Jenkins, or another system.

Required environment variables:
    JIRA_URL          — base URL of your Jira Cloud instance
                        e.g. https://mycompany.atlassian.net
    JIRA_EMAIL        — Atlassian account email (used for Basic auth)
    JIRA_TOKEN        — API token from id.atlassian.com → Security → API tokens
    JIRA_PROJECT_KEY  — Jira project key (e.g. "MYPROJ", "ENG")

Optional environment variables:
    JIRA_HOLD_ISSUE_TYPE      — issue type for HOLD escalations (default: "Bug")
    JIRA_ADVISORY_ISSUE_TYPE  — issue type for advisory findings (default: "Task")
    JIRA_REVIEW_ISSUE_TYPE    — issue type for review gate tickets (default: "Task")
    JIRA_HOLD_PRIORITY        — priority for HOLD issues (default: "High")
    JIRA_ADVISORY_PRIORITY    — priority for advisory issues (default: "Medium")
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from platforms.base import PlatformAdapter

_REPO_ROOT = Path(__file__).parent.parent.parent


def _adf(sections: list[dict]) -> dict:
    """Build an Atlassian Document Format document from a list of section dicts.

    Each section dict must have a 'type' key:
      {"type": "paragraph", "text": "..."}
      {"type": "heading", "level": 2, "text": "..."}
      {"type": "code", "language": "yaml", "text": "..."}
      {"type": "rule"}
    """
    content = []
    for sec in sections:
        t = sec.get("type")
        if t == "paragraph":
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": sec["text"]}],
            })
        elif t == "heading":
            content.append({
                "type": "heading",
                "attrs": {"level": sec.get("level", 2)},
                "content": [{"type": "text", "text": sec["text"]}],
            })
        elif t == "code":
            content.append({
                "type": "codeBlock",
                "attrs": {"language": sec.get("language", "text")},
                "content": [{"type": "text", "text": sec["text"]}],
            })
        elif t == "rule":
            content.append({"type": "rule"})
        elif t == "bulletList":
            items = [
                {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": item}]}],
                }
                for item in sec.get("items", [])
            ]
            content.append({"type": "bulletList", "content": items})
    return {"version": 1, "type": "doc", "content": content}


class JiraAdapter(PlatformAdapter):
    def __init__(self, url: str, email: str, token: str, project_key: str) -> None:
        self._base = url.rstrip("/") if url else ""
        self._auth = (email, token) if email and token else None
        self._project_key = project_key
        self._available = (
            _REQUESTS_AVAILABLE
            and bool(self._base)
            and self._auth is not None
            and bool(project_key)
        )

        if not _REQUESTS_AVAILABLE:
            print("[Jira] 'requests' not installed. Run: pip install requests")
        elif not self._base:
            print("[Jira] JIRA_URL not set.")
        elif not self._auth:
            print("[Jira] JIRA_EMAIL and JIRA_TOKEN are required.")
        elif not project_key:
            print("[Jira] JIRA_PROJECT_KEY not set.")

    def _api(self, path: str) -> str:
        return f"{self._base}/rest/api/3/{path.lstrip('/')}"

    def _create_issue(
        self,
        summary: str,
        description_adf: dict,
        issue_type: str,
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> str:
        """Create a Jira issue and return its URL, or '' on failure."""
        if not self._available:
            return ""

        fields: dict = {
            "project": {"key": self._project_key},
            "summary": summary,
            "description": description_adf,
            "issuetype": {"name": issue_type},
        }
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = labels

        try:
            resp = _requests.post(
                self._api("issue"),
                auth=self._auth,
                json={"fields": fields},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            key = data.get("key", "")
            url = f"{self._base}/browse/{key}" if key else ""
            return url
        except Exception as e:
            print(f"[Jira] Failed to create issue: {e}")
            return ""

    # ------------------------------------------------------------------
    # Review gate — Jira Task ticket (Jira has no native PR concept)
    # ------------------------------------------------------------------

    def open_review_pr(self, day: int, pace_dir: Path) -> str:
        if not self._available:
            print("[Jira] Adapter not configured — skipping review gate ticket.")
            return ""

        start_day = 1
        for candidate_start in [15, 29]:
            if day >= candidate_start:
                start_day = candidate_start
        period = f"Days {start_day}–{day}"

        ship_count, hold_count, deferred_items = 0, 0, []
        for d in range(start_day, day):
            gate_file = pace_dir / f"day-{d}" / "gate.md"
            if gate_file.exists():
                report = yaml.safe_load(gate_file.read_text())
                if report.get("gate_decision") == "SHIP":
                    ship_count += 1
                else:
                    hold_count += 1
                deferred_items.extend(report.get("deferred", []))

        total = ship_count + hold_count
        ship_rate = f"{(ship_count / total * 100):.0f}%" if total else "N/A"

        sections = [
            {"type": "heading", "level": 2, "text": f"PACE Review Gate — {period}"},
            {"type": "paragraph", "text": (
                f"Stories completed: {ship_count}/{total}  |  "
                f"SHIP rate: {ship_rate}  |  "
                f"Escalated HOLDs: {hold_count}"
            )},
        ]
        if deferred_items:
            sections.append({"type": "heading", "level": 3, "text": "Deferred Acceptance Criteria"})
            sections.append({"type": "bulletList", "items": deferred_items})
        sections += [
            {"type": "rule"},
            {"type": "paragraph", "text": (
                "To resume: resolve any open issues, then re-trigger the PACE workflow "
                f"for Day {day + 1}. Close this ticket when done."
            )},
            {"type": "paragraph", "text": f"Generated by PACE Orchestrator — Day {day}"},
        ]

        issue_type = os.environ.get("JIRA_REVIEW_ISSUE_TYPE", "Task")
        url = self._create_issue(
            summary=f"[PACE Review Gate] {period}",
            description_adf=_adf(sections),
            issue_type=issue_type,
            labels=["pace-review", f"pace-day-{day}"],
        )
        if url:
            print(f"[Jira] Review gate ticket opened: {url}")
        return url

    # ------------------------------------------------------------------
    # Escalation issue — Jira Bug ticket for HOLD
    # ------------------------------------------------------------------

    def open_escalation_issue(self, day: int, day_dir: Path) -> str:
        if not self._available:
            print("[Jira] Adapter not configured — skipping escalation ticket.")
            return ""

        story_text = (day_dir / "story.md").read_text() if (day_dir / "story.md").exists() else "Not available"
        handoff_text = (day_dir / "handoff.md").read_text() if (day_dir / "handoff.md").exists() else "Not available"
        gate_text = (day_dir / "gate.md").read_text() if (day_dir / "gate.md").exists() else "Not available"
        gate_data = yaml.safe_load(gate_text) if (day_dir / "gate.md").exists() else {}
        hold_reason = gate_data.get("hold_reason", "Unknown — see gate report")

        sections = [
            {"type": "heading", "level": 2, "text": f"Escalated HOLD — Day {day}"},
            {"type": "paragraph", "text": (
                "PACE could not resolve this HOLD after 2 retries. "
                "Human intervention required."
            )},
            {"type": "paragraph", "text": f"Blocker: {hold_reason}"},
            {"type": "rule"},
            {"type": "heading", "level": 3, "text": "Story Card"},
            {"type": "code", "language": "yaml", "text": story_text},
            {"type": "heading", "level": 3, "text": "FORGE Handoff (last attempt)"},
            {"type": "code", "language": "yaml", "text": handoff_text},
            {"type": "heading", "level": 3, "text": "GATE Report (last attempt)"},
            {"type": "code", "language": "yaml", "text": gate_text},
            {"type": "rule"},
            {"type": "heading", "level": 3, "text": "To Resume"},
            {"type": "bulletList", "items": [
                "Resolve the blocker described above",
                "Close this ticket",
                f"The PACE loop will re-run Day {day} on the next scheduled trigger",
            ]},
            {"type": "paragraph", "text": "Generated by PACE Orchestrator"},
        ]

        issue_type = os.environ.get("JIRA_HOLD_ISSUE_TYPE", "Bug")
        priority = os.environ.get("JIRA_HOLD_PRIORITY", "High")
        url = self._create_issue(
            summary=f"[PACE HOLD] Day {day} — {hold_reason[:80]}",
            description_adf=_adf(sections),
            issue_type=issue_type,
            priority=priority,
            labels=["pace-hold", f"pace-day-{day}"],
        )
        if url:
            print(f"[Jira] Escalation ticket opened: {url}")
        return url

    # ------------------------------------------------------------------
    # Advisory findings — Jira Task ticket per backlisted batch
    # ------------------------------------------------------------------

    def push_advisory_items(self, day: int, items: list[dict], agent: str) -> str:
        if not self._available:
            print(f"[Jira] Adapter not configured — skipping advisory ticket for {agent}.")
            return ""
        if not items:
            return ""

        finding_bullets = [
            f"[{item['id']}] {item['finding']}"
            for item in items
        ]

        sections = [
            {"type": "heading", "level": 2, "text": f"PACE Advisory — {agent} Day {day}"},
            {"type": "paragraph", "text": (
                f"{agent} raised {len(items)} advisory finding(s) on Day {day} that "
                "were not resolved after one retry. These are non-blocking but must be "
                "cleared on the next clearance day."
            )},
            {"type": "heading", "level": 3, "text": "Findings"},
            {"type": "bulletList", "items": finding_bullets},
            {"type": "rule"},
            {"type": "heading", "level": 3, "text": "Resolution"},
            {"type": "bulletList", "items": [
                "Address each finding before the next clearance day",
                "On a clearance day, SENTINEL/CONDUIT will verify and clear resolved items",
                "Unresolved items on a clearance day become blockers (HOLD)",
            ]},
            {"type": "paragraph", "text": f"Generated by PACE Orchestrator — Day {day}"},
        ]

        issue_type = os.environ.get("JIRA_ADVISORY_ISSUE_TYPE", "Task")
        priority = os.environ.get("JIRA_ADVISORY_PRIORITY", "Medium")
        url = self._create_issue(
            summary=f"[PACE Advisory] {agent} Day {day} — {len(items)} finding(s)",
            description_adf=_adf(sections),
            issue_type=issue_type,
            priority=priority,
            labels=["pace-advisory", f"pace-{agent.lower()}", f"pace-day-{day}"],
        )
        if url:
            print(f"[Jira] Advisory ticket opened: {url}")
        return url

    # ------------------------------------------------------------------
    # CI polling — not supported (Jira has no CI)
    # ------------------------------------------------------------------

    def wait_for_commit_ci(
        self,
        sha: str,
        timeout_minutes: int = 15,
        poll_interval: int = 20,
    ) -> dict:
        print(
            f"[Jira] CI polling is not supported in Jira mode. "
            f"Configure a CI platform (github/gitlab/jenkins) for CI status."
        )
        return {"conclusion": "no_runs", "url": "", "name": "", "sha": sha or ""}

    # ------------------------------------------------------------------
    # Summary / reporting
    # ------------------------------------------------------------------

    def post_daily_summary(self, day: int, gate_report: dict) -> None:
        decision = gate_report.get("gate_decision", "UNKNOWN")
        icon = "✅" if decision == "SHIP" else "🔴"
        print(f"[Jira] Day {day} summary: {icon} {decision}")

    def write_job_summary(self, markdown: str) -> None:
        out_file = _REPO_ROOT / "pace-summary.md"
        out_file.write_text(markdown)
        print(f"[Jira] Job summary written to: {out_file}")
