"""Advisory backlog management for PACE.

Tracks non-blocking findings from SENTINEL and CONDUIT across days.
Backlog persists in .pace/advisory_backlog.yaml.

Lifecycle:
  - SENTINEL/CONDUIT raises ADVISORY → FORGE gets one retry
  - If still ADVISORY after retry → finding added to backlog (non-blocking)
  - Every 7th day → all open backlog items are mandatory; must SHIP to clear them
"""

import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BACKLOG_FILE = REPO_ROOT / ".pace" / "advisory_backlog.yaml"


def _load_all() -> list[dict]:
    if not BACKLOG_FILE.exists():
        return []
    return yaml.safe_load(BACKLOG_FILE.read_text()) or []


def _save_all(items: list[dict]) -> None:
    BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKLOG_FILE.write_text(yaml.dump(items, default_flow_style=False, allow_unicode=True))


def load_open_backlog() -> list[dict]:
    """Return all items with status 'open'."""
    return [i for i in _load_all() if i.get("status") == "open"]


def add_advisory_items(day: int, findings: list[str], agent: str) -> None:
    """Append new advisory findings to the backlog (deduplicated by finding text)."""
    all_items = _load_all()
    existing_findings = {i["finding"] for i in all_items}
    for finding in findings:
        if finding not in existing_findings:
            all_items.append({
                "id": f"{agent.lower()}-day{day}-{len(all_items) + 1}",
                "day_raised": day,
                "agent": agent,
                "finding": finding,
                "status": "open",
            })
            existing_findings.add(finding)
    _save_all(all_items)


def clear_advisory_items(agent: str) -> None:
    """Mark all open items for the given agent as cleared."""
    all_items = _load_all()
    for item in all_items:
        if item.get("agent") == agent and item.get("status") == "open":
            item["status"] = "cleared"
    _save_all(all_items)


def format_backlog_for_forge(backlog_items: list[dict]) -> str:
    """Format open backlog items as a readable block for FORGE's context."""
    lines = []
    for item in backlog_items:
        lines.append(f"- [{item['agent']}] (raised Day {item['day_raised']}): {item['finding']}")
    return "\n".join(lines)
