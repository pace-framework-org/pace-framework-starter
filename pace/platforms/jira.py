"""PACE Jira Tracker Adapter.

Uses the Jira Cloud REST API v3 to open tickets for HOLD escalations and
advisory findings.

Jira has no CI concept — use this adapter as the tracker alongside a CI
platform (github/gitlab/bitbucket/jenkins) configured under platform.ci.

Required environment variables:
    JIRA_URL          — base URL of your Jira Cloud instance
                        e.g. https://mycompany.atlassian.net
    JIRA_EMAIL        — Atlassian account email (used for Basic auth)
    JIRA_TOKEN        — API token from id.atlassian.com → Security → API tokens
    JIRA_PROJECT_KEY  — Jira project key (e.g. "MYPROJ", "ENG")

Optional environment variables:
    JIRA_HOLD_ISSUE_TYPE      — issue type for HOLD escalations (default: "Bug")
    JIRA_ADVISORY_ISSUE_TYPE  — issue type for advisory findings (default: "Task")
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

from platforms.base import TrackerAdapter

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


class JiraTrackerAdapter(TrackerAdapter):
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
    # Escalation issue — Jira Bug ticket for HOLD
    # ------------------------------------------------------------------

    def open_escalation_issue(self, day: int, day_dir: Path, hold_reason: str = "") -> str:
        if not self._available:
            print("[Jira] Adapter not configured — skipping escalation ticket.")
            return ""

        story_text = (day_dir / "story.md").read_text() if (day_dir / "story.md").exists() else "Not available"
        handoff_text = (day_dir / "handoff.md").read_text() if (day_dir / "handoff.md").exists() else "Not available"
        gate_text = (day_dir / "gate.md").read_text() if (day_dir / "gate.md").exists() else "Not available"
        if not hold_reason:
            gate_data = yaml.safe_load(gate_text) if (day_dir / "gate.md").exists() else {}
            hold_reason = (gate_data or {}).get("hold_reason", "")
        if not hold_reason and (day_dir / "sentinel.md").exists():
            hold_reason = (yaml.safe_load((day_dir / "sentinel.md").read_text()) or {}).get("hold_reason", "")
        if not hold_reason and (day_dir / "conduit.md").exists():
            hold_reason = (yaml.safe_load((day_dir / "conduit.md").read_text()) or {}).get("hold_reason", "")
        if not hold_reason:
            hold_reason = "Unknown — see agent reports below"

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
                "In your CI/CD platform, set PACE_PAUSED to false",
                f"The PACE loop will re-run Day {day} on the next scheduled trigger",
            ]},
            {"type": "paragraph", "text": (
                "Note: PACE_PAUSED was automatically set to true when this ticket was "
                "opened to prevent the pipeline from retrying indefinitely."
            )},
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