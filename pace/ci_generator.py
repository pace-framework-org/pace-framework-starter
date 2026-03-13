"""PACE CI Generator (ROADMAP Item 8 — Cron Configuration).

Reads the `cron` section from pace.config.yaml and regenerates the cron
schedule fields in CI workflow files so teams only need to edit one place.

Supported platforms (determined by platform.ci in config):
    github   — .github/workflows/pace.yml + .github/workflows/pace-planner.yml
    gitlab   — .gitlab-ci.yml  (stub)
    jenkins  — Jenkinsfile     (stub)
    bitbucket — bitbucket-pipelines.yml (stub)

Usage:
    python pace/ci_generator.py              # preview changes (dry run)
    python pace/ci_generator.py --apply      # write changes to disk
    python pace/ci_generator.py --check      # exit 1 if files are out of sync

The --check mode is suitable for use in config_tester.py or CI preflight.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def _load_config():
    sys.path.insert(0, str(Path(__file__).parent))
    from config import load_config
    return load_config()


# ---------------------------------------------------------------------------
# GitHub Actions helpers
# ---------------------------------------------------------------------------

_GITHUB_PACE_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "pace.yml"
_GITHUB_PLANNER_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "pace-planner.yml"

# Regex that matches the schedule block inside a GitHub Actions workflow.
# Captures the indentation and the existing cron expression so we can replace it.
_GHA_SCHEDULE_RE = re.compile(
    r"(  schedule:\n    - cron: \")([^\"]+)(\")",
    re.MULTILINE,
)


def _update_gha_cron(file: Path, new_cron: str, dry_run: bool = True) -> tuple[bool, str]:
    """Replace the schedule.cron value in a GitHub Actions workflow file.

    Returns (changed: bool, message: str).
    """
    if not file.exists():
        return False, f"[ci_generator] {file.name} not found — skipping."

    content = file.read_text()
    match = _GHA_SCHEDULE_RE.search(content)
    if not match:
        return False, f"[ci_generator] {file.name}: no schedule block found — skipping."

    old_cron = match.group(2)
    if old_cron == new_cron:
        return False, f"[ci_generator] {file.name}: cron already up to date ({new_cron})."

    new_content = _GHA_SCHEDULE_RE.sub(
        lambda m: m.group(1) + new_cron + m.group(3),
        content,
    )
    if not dry_run:
        file.write_text(new_content)

    action = "would update" if dry_run else "updated"
    return True, f"[ci_generator] {file.name}: {action} cron  {old_cron!r} → {new_cron!r}"


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def generate(apply: bool = False, check: bool = False) -> bool:
    """Run the generator. Returns True if all files are in sync (or were synced).

    apply=True  — write changes to disk
    check=True  — return False (exit 1) if any file is out of sync
    """
    cfg = _load_config()
    cron = cfg.cron
    ci = cfg.ci_type.lower()

    all_in_sync = True
    messages: list[str] = []

    if ci == "github":
        for workflow_file, cron_expr, label in [
            (_GITHUB_PACE_WORKFLOW, cron.pace_pipeline, "pace.yml"),
            (_GITHUB_PLANNER_WORKFLOW, cron.planner_pipeline, "pace-planner.yml"),
        ]:
            changed, msg = _update_gha_cron(workflow_file, cron_expr, dry_run=not apply)
            messages.append(msg)
            if changed:
                all_in_sync = False

    elif ci == "gitlab":
        messages.append(
            "[ci_generator] GitLab CI generator not yet implemented — see ROADMAP Item 7."
        )

    elif ci == "jenkins":
        messages.append(
            "[ci_generator] Jenkins generator not yet implemented — see ROADMAP Item 7."
        )

    elif ci == "bitbucket":
        messages.append(
            "[ci_generator] Bitbucket Pipelines generator not yet implemented — see ROADMAP Item 7."
        )

    else:
        messages.append(
            f"[ci_generator] Unknown ci_type '{ci}' — no workflow files to update."
        )

    for msg in messages:
        print(msg)

    if check and not all_in_sync:
        print(
            "\n[ci_generator] Workflow cron schedules are out of sync with pace.config.yaml.\n"
            "  Run: python pace/ci_generator.py --apply  to regenerate them."
        )
        return False

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Regenerate CI workflow cron schedules from pace.config.yaml"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write updated cron schedules to workflow files (default: dry run)",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if workflow files are out of sync with config (for CI use)",
    )
    args = parser.parse_args()

    ok = generate(apply=args.apply, check=args.check)
    sys.exit(0 if ok else 1)
