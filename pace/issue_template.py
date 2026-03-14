"""PACE Issue Template helpers.

Shared formatters for tracker artifact bodies (story tickets, handoff comments).
Used by all TrackerAdapter implementations to produce consistent markup.
"""

from __future__ import annotations

import yaml


def story_body_markdown(day: int, story_card: dict) -> str:
    """Format a PRIME story card as a tracker issue body (Markdown)."""
    target = story_card.get("target", f"Day {day} story")
    acceptance = story_card.get("acceptance", [])
    ac_lines = "\n".join(f"- [ ] {ac}" for ac in acceptance) if acceptance else "_No acceptance criteria listed._"

    raw_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True).strip()

    return f"""## PACE Story — Day {day}

**Target:** {target}

### Acceptance Criteria

{ac_lines}

---

### Full Story Card

```yaml
{raw_yaml}
```

---

_Opened automatically by PACE Orchestrator — Day {day}_"""


def handoff_comment_markdown(day: int, handoff: dict) -> str:
    """Format a FORGE handoff note as a tracker issue comment body (Markdown)."""
    status = handoff.get("status", "unknown")
    summary = handoff.get("summary", "")
    cost = handoff.get("forge_cost_usd")
    cost_str = f"${cost:.4f}" if cost is not None else "N/A"

    raw_yaml = yaml.dump(handoff, default_flow_style=False, allow_unicode=True).strip()

    return f"""### FORGE Handoff — Day {day}

**Status:** `{status}`
**Cost:** {cost_str}

{('**Summary:** ' + summary) if summary else ''}

<details>
<summary>Full handoff note (YAML)</summary>

```yaml
{raw_yaml}
```

</details>

_Posted automatically by PACE Orchestrator on SHIP — Day {day}_"""


def story_body_adf(day: int, story_card: dict) -> dict:
    """Format a PRIME story card as an Atlassian Document Format (ADF) body.

    Used by JiraTrackerAdapter which requires ADF for issue descriptions.
    """
    from platforms.jira import _adf  # type: ignore[import]

    target = story_card.get("target", f"Day {day} story")
    acceptance = story_card.get("acceptance", [])
    raw_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True).strip()

    sections: list[dict] = [
        {"type": "heading", "level": 2, "text": f"PACE Story — Day {day}"},
        {"type": "paragraph", "text": f"Target: {target}"},
    ]
    if acceptance:
        sections.append({"type": "heading", "level": 3, "text": "Acceptance Criteria"})
        sections.append({"type": "bulletList", "items": [str(ac) for ac in acceptance]})
    sections.append({"type": "rule"})
    sections.append({"type": "heading", "level": 3, "text": "Full Story Card"})
    sections.append({"type": "code", "language": "yaml", "text": raw_yaml})
    sections.append({"type": "rule"})
    sections.append({"type": "paragraph", "text": f"Opened automatically by PACE Orchestrator — Day {day}"})
    return _adf(sections)


def handoff_comment_adf(day: int, handoff: dict) -> dict:
    """Format a FORGE handoff note as an ADF document for Jira comments."""
    from platforms.jira import _adf  # type: ignore[import]

    status = handoff.get("status", "unknown")
    cost = handoff.get("forge_cost_usd")
    cost_str = f"${cost:.4f}" if cost is not None else "N/A"
    raw_yaml = yaml.dump(handoff, default_flow_style=False, allow_unicode=True).strip()

    sections: list[dict] = [
        {"type": "heading", "level": 3, "text": f"FORGE Handoff — Day {day}"},
        {"type": "paragraph", "text": f"Status: {status}  |  Cost: {cost_str}"},
        {"type": "heading", "level": 4, "text": "Full Handoff Note"},
        {"type": "code", "language": "yaml", "text": raw_yaml},
        {"type": "paragraph", "text": f"Posted automatically by PACE Orchestrator on SHIP — Day {day}"},
    ]
    return _adf(sections)
