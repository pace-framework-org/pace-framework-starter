"""Migration v3: Rename day-N entries to story-N in plan.yaml.

Adds status: shipped to entries that have a corresponding
.pace/day-N/handoff.yaml. Backs up plan.yaml before writing.

Usage:
    python pace/migrations/v3_plan_naming.py
    python pace/migrations/v3_plan_naming.py --dry-run
    python pace/migrations/v3_plan_naming.py --plan path/to/plan.yaml
"""

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
PLAN_FILE = REPO_ROOT / "plan.yaml"
PACE_DIR = REPO_ROOT / ".pace"


def migrate(
    plan_file: Path = PLAN_FILE,
    pace_dir: Path = PACE_DIR,
    dry_run: bool = False,
) -> int:
    """Migrate plan.yaml from days: format to stories: format.

    Returns 0 on success.
    """
    if not plan_file.exists():
        print(f"[v3_plan_naming] {plan_file} not found — skipping.")
        return 0

    try:
        data = yaml.safe_load(plan_file.read_text()) or {}
    except yaml.YAMLError as exc:
        print(f"[v3_plan_naming] YAML parse error: {exc}")
        return 1

    if "stories" in data:
        print("[v3_plan_naming] plan.yaml already uses stories: format — no migration needed.")
        return 0

    days = data.get("days", [])
    if not days:
        print("[v3_plan_naming] plan.yaml has no days entries — nothing to migrate.")
        return 0

    stories = []
    for entry in days:
        day_num = entry.get("day")
        if day_num is None:
            continue

        handoff = pace_dir / f"day-{day_num}" / "handoff.yaml"
        if handoff.exists():
            status = "shipped"
            shipped_at = datetime.fromtimestamp(handoff.stat().st_mtime).strftime("%Y-%m-%d")
        else:
            status = "pending"
            shipped_at = None

        story: dict = {
            "id": f"story-{day_num}",
            "title": entry.get("target", ""),
            "status": status,
        }
        if shipped_at:
            story["shipped_at"] = shipped_at

        # Preserve fields other than day/target
        for k, v in entry.items():
            if k not in ("day", "target"):
                story[k] = v

        stories.append(story)

    if dry_run:
        print(
            f"[v3_plan_naming] Dry run: would rename {len(days)} day entries "
            f"to story entries in {plan_file}."
        )
        return 0

    # Backup before modifying
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = plan_file.parent / f"plan.yaml.pre-v3.{ts}"
    shutil.copy2(plan_file, backup)
    print(f"[v3_plan_naming] Backed up {plan_file.name} → {backup.name}")

    new_data = {k: v for k, v in data.items() if k != "days"}
    new_data["stories"] = stories
    plan_file.write_text(yaml.dump(new_data, default_flow_style=False, allow_unicode=True))
    print(f"[v3_plan_naming] Migrated {len(days)} day entries to story entries.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate plan.yaml day-N keys to story-N (PACE v3)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--plan", default=str(PLAN_FILE), metavar="PATH",
                        help="Path to plan.yaml (default: repo root)")
    args = parser.parse_args()
    raise SystemExit(migrate(Path(args.plan), dry_run=args.dry_run))
