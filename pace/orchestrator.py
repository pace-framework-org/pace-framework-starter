#!/usr/bin/env python3
"""PACE Orchestrator — drives the daily PRIME -> FORGE -> GATE -> SENTINEL -> CONDUIT cycle.

Usage:
    PACE_DAY=1 ANTHROPIC_API_KEY=... python orchestrator.py

Environment variables:
    PACE_DAY              Current day number (1-N, where N = sprint.duration_days in config)
    ANTHROPIC_API_KEY     Anthropic API key
    PACE_PAUSED           Set to "true" to skip execution (loop is paused)

Platform credentials (set the ones matching your platform.type in pace.config.yaml):
    GitHub:   GITHUB_TOKEN, GITHUB_REPOSITORY
    GitLab:   GITLAB_TOKEN, GITLAB_PROJECT [, GITLAB_URL]
    Jenkins:  JENKINS_URL, JENKINS_USER, JENKINS_TOKEN, JENKINS_JOB_NAME
    Local:    (none required)
"""

import os
import shlex
import sys
import yaml
import subprocess
from pathlib import Path

# Add the pace directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from agents.prime import run_prime
from agents.forge import run_forge
from agents.gate import run_gate
from agents.sentinel import run_sentinel
from agents.conduit import run_conduit
from preflight import run_preflight
from advisory import (
    load_open_backlog,
    add_advisory_items,
    clear_advisory_items,
    format_backlog_for_forge,
)
from config import load_config
from platforms import get_platform_adapter
from platforms.base import PlatformAdapter
from reporter import write_job_summary, update_progress_md

REPO_ROOT = Path(__file__).parent.parent
PACE_DIR = REPO_ROOT / ".pace"
PLAN_FILE = Path(__file__).parent / "plan.yaml"
PROGRESS_FILE = REPO_ROOT / "PROGRESS.md"
MAX_RETRIES = 1


class CycleAbortError(Exception):
    """Raised when a cycle cannot start due to an infrastructure failure (e.g. PRIME error).
    Unlike a HOLD, this does not trigger a platform escalation issue."""


def load_plan() -> dict:
    with open(PLAN_FILE) as f:
        return yaml.safe_load(f)


def get_current_day() -> int:
    raw = os.environ.get("PACE_DAY", "").strip()
    if not raw.isdigit():
        print(f"[PACE] ERROR: PACE_DAY must be an integer, got: '{raw}'")
        sys.exit(1)
    return int(raw)


def get_day_plan(plan: dict, day: int) -> dict:
    for d in plan["days"]:
        if d["day"] == day:
            return d
    raise ValueError(f"Day {day} not found in plan.yaml — add the day entry and retry.")


def get_recent_gate_reports(day: int, count: int = 3) -> list[str]:
    reports = []
    for d in range(max(1, day - count), day):
        gate_file = PACE_DIR / f"day-{d}" / "gate.md"
        if gate_file.exists():
            reports.append(gate_file.read_text())
    return reports


def commit_artifact(path: Path, message: str) -> None:
    subprocess.run(
        f'git add {shlex.quote(str(path))} && git commit -m {shlex.quote(message)} --allow-empty && git push origin HEAD',
        shell=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


def run_cycle(day: int, day_plan: dict, recent_gates: list[str], platform: PlatformAdapter) -> bool:
    day_dir = PACE_DIR / f"day-{day}"
    day_dir.mkdir(parents=True, exist_ok=True)

    is_clearance_day = (day % 7 == 0)

    # Step 1: PRIME
    print(f"[PACE] Day {day}: Invoking PRIME...")
    try:
        story_card = run_prime(day, day_plan["target"], recent_gates)
    except Exception as exc:
        import traceback
        print(f"[PACE] PRIME failed — cannot continue cycle:\n{traceback.format_exc()}")
        raise CycleAbortError(str(exc)) from exc
    story_file = day_dir / "story.md"
    story_file.write_text(yaml.dump(story_card, default_flow_style=False, allow_unicode=True))
    commit_artifact(story_file, f"Day {day}: PRIME story card")
    print(f"[PACE] Story card written.")

    open_backlog = load_open_backlog() if is_clearance_day else []
    if is_clearance_day and open_backlog:
        print(f"[PACE] Day {day}: Clearance day — {len(open_backlog)} open advisory item(s) to resolve.")

    # Tracks whether the one advisory retry has been used for each agent this day
    advisory_attempt: dict[str, bool] = {"SENTINEL": False, "CONDUIT": False}
    hold_reason: str | None = None

    for attempt in range(1, MAX_RETRIES + 2):
        # Step 2: FORGE
        forge_hold = hold_reason
        if is_clearance_day and open_backlog and attempt == 1:
            backlog_text = format_backlog_for_forge(open_backlog)
            forge_hold = (
                (forge_hold + "\n\n" if forge_hold else "")
                + f"Advisory Backlog to clear (Day {day} is a clearance day):\n{backlog_text}"
            )

        print(f"[PACE] Day {day}: Invoking FORGE (attempt {attempt}/{MAX_RETRIES + 1})...")
        try:
            handoff = run_forge(day, story_card, forge_hold)
        except Exception as exc:
            print(f"[PACE] FORGE failed with exception: {exc}")
            if attempt > MAX_RETRIES:
                return False
            hold_reason = str(exc)
            continue

        handoff_file = day_dir / "handoff.md"
        handoff_file.write_text(yaml.dump(handoff, default_flow_style=False, allow_unicode=True))
        commit_artifact(handoff_file, f"Day {day}: FORGE handoff note (attempt {attempt})")

        # Step 2b: Wait for CI
        commit_sha = handoff.get("commit", "")
        ci_result: dict | None = None
        if commit_sha:
            print(f"[PACE] Day {day}: Waiting for CI on commit {commit_sha}...")
            ci_result = platform.wait_for_commit_ci(commit_sha)
            print(f"[PACE] CI result: {ci_result['conclusion']}")

        # Step 3: GATE
        print(f"[PACE] Day {day}: Invoking GATE...")
        try:
            gate_report = run_gate(day, story_card, handoff, ci_result=ci_result)
        except Exception as exc:
            print(f"[PACE] GATE failed with exception: {exc}")
            gate_report = {
                "day": day, "agent": "GATE", "criteria_results": [],
                "blockers": [str(exc)], "deferred": [],
                "gate_decision": "HOLD", "hold_reason": f"GATE agent error: {exc}",
            }

        gate_file = day_dir / "gate.md"
        gate_file.write_text(yaml.dump(gate_report, default_flow_style=False, allow_unicode=True))

        if gate_report.get("gate_decision") == "HOLD":
            hold_reason = gate_report.get("hold_reason", "")
            print(f"[PACE] Day {day}: GATE HOLD (attempt {attempt}): {hold_reason}")
            commit_artifact(gate_file, f"Day {day}: GATE report — HOLD attempt {attempt}")
            if attempt > MAX_RETRIES:
                return False
            continue

        commit_artifact(gate_file, f"Day {day}: GATE report — PASS attempt {attempt}")

        # Step 4: SENTINEL
        print(f"[PACE] Day {day}: Invoking SENTINEL...")
        sentinel_backlog = [b for b in open_backlog if b["agent"] == "SENTINEL"] if is_clearance_day else None
        try:
            sentinel_report = run_sentinel(day, story_card, handoff, gate_report, advisory_backlog=sentinel_backlog)
        except Exception as exc:
            print(f"[PACE] SENTINEL failed with exception: {exc}")
            sentinel_report = {
                "day": day, "agent": "SENTINEL", "findings": [],
                "advisories": [], "blockers": [str(exc)],
                "sentinel_decision": "HOLD", "hold_reason": f"SENTINEL agent error: {exc}",
            }

        sentinel_file = day_dir / "sentinel.md"
        sentinel_file.write_text(yaml.dump(sentinel_report, default_flow_style=False, allow_unicode=True))
        sentinel_decision = sentinel_report.get("sentinel_decision")

        if sentinel_decision == "HOLD":
            hold_reason = sentinel_report.get("hold_reason", "")
            print(f"[PACE] Day {day}: SENTINEL HOLD (attempt {attempt}): {hold_reason}")
            commit_artifact(sentinel_file, f"Day {day}: SENTINEL report — HOLD attempt {attempt}")
            if attempt > MAX_RETRIES:
                return False
            continue

        if sentinel_decision == "ADVISORY":
            if not advisory_attempt["SENTINEL"] and attempt <= MAX_RETRIES:
                advisory_attempt["SENTINEL"] = True
                hold_reason = "SENTINEL ADVISORY (one retry): " + "; ".join(sentinel_report.get("advisories", []))
                print(f"[PACE] Day {day}: SENTINEL ADVISORY — giving FORGE one retry.")
                commit_artifact(sentinel_file, f"Day {day}: SENTINEL report — ADVISORY attempt {attempt}")
                continue
            else:
                new_advisories = sentinel_report.get("advisories", [])
                add_advisory_items(day, new_advisories, "SENTINEL")
                print(f"[PACE] Day {day}: SENTINEL ADVISORY backlogged — continuing to CONDUIT.")
                cfg = load_config()
                if cfg.advisory_push_to_issues and new_advisories:
                    from advisory import load_open_backlog as _lob
                    all_items = _lob()
                    new_items = [i for i in all_items if i.get("day_raised") == day and i.get("agent") == "SENTINEL"]
                    platform.push_advisory_items(day, new_items, "SENTINEL")

        if sentinel_decision == "SHIP" and is_clearance_day and sentinel_backlog:
            clear_advisory_items("SENTINEL")
            print(f"[PACE] Day {day}: SENTINEL cleared advisory backlog.")

        commit_artifact(sentinel_file, f"Day {day}: SENTINEL report — {sentinel_decision} attempt {attempt}")

        # Step 5: CONDUIT
        print(f"[PACE] Day {day}: Invoking CONDUIT...")
        conduit_backlog = [b for b in open_backlog if b["agent"] == "CONDUIT"] if is_clearance_day else None
        try:
            conduit_report = run_conduit(day, story_card, handoff, sentinel_report, advisory_backlog=conduit_backlog)
        except Exception as exc:
            print(f"[PACE] CONDUIT failed with exception: {exc}")
            conduit_report = {
                "day": day, "agent": "CONDUIT", "findings": [],
                "advisories": [], "blockers": [str(exc)],
                "conduit_decision": "HOLD", "hold_reason": f"CONDUIT agent error: {exc}",
            }

        conduit_file = day_dir / "conduit.md"
        conduit_file.write_text(yaml.dump(conduit_report, default_flow_style=False, allow_unicode=True))
        conduit_decision = conduit_report.get("conduit_decision")

        if conduit_decision == "HOLD":
            hold_reason = conduit_report.get("hold_reason", "")
            print(f"[PACE] Day {day}: CONDUIT HOLD (attempt {attempt}): {hold_reason}")
            commit_artifact(conduit_file, f"Day {day}: CONDUIT report — HOLD attempt {attempt}")
            if attempt > MAX_RETRIES:
                return False
            continue

        if conduit_decision == "ADVISORY":
            if not advisory_attempt["CONDUIT"] and attempt <= MAX_RETRIES:
                advisory_attempt["CONDUIT"] = True
                hold_reason = "CONDUIT ADVISORY (one retry): " + "; ".join(conduit_report.get("advisories", []))
                print(f"[PACE] Day {day}: CONDUIT ADVISORY — giving FORGE one retry.")
                commit_artifact(conduit_file, f"Day {day}: CONDUIT report — ADVISORY attempt {attempt}")
                continue
            else:
                new_advisories = conduit_report.get("advisories", [])
                add_advisory_items(day, new_advisories, "CONDUIT")
                print(f"[PACE] Day {day}: CONDUIT ADVISORY backlogged — proceeding to SHIP.")
                cfg = load_config()
                if cfg.advisory_push_to_issues and new_advisories:
                    from advisory import load_open_backlog as _lob
                    all_items = _lob()
                    new_items = [i for i in all_items if i.get("day_raised") == day and i.get("agent") == "CONDUIT"]
                    platform.push_advisory_items(day, new_items, "CONDUIT")

        if conduit_decision == "SHIP" and is_clearance_day and conduit_backlog:
            clear_advisory_items("CONDUIT")
            print(f"[PACE] Day {day}: CONDUIT cleared advisory backlog.")

        commit_artifact(conduit_file, f"Day {day}: CONDUIT report — {conduit_decision} attempt {attempt}")

        # Clearance day: verify all open items were resolved
        if is_clearance_day and open_backlog:
            remaining = load_open_backlog()
            if remaining:
                print(f"[PACE] Day {day}: Clearance day FAILED — {len(remaining)} advisory item(s) still open.")
                return False

        # All checks passed — SHIP
        platform.post_daily_summary(day, gate_report)
        print(f"[PACE] Day {day}: GATE + SENTINEL + CONDUIT — SHIP")
        return True

    return False


def main() -> None:
    if os.environ.get("PACE_PAUSED", "").lower() == "true":
        print("[PACE] Loop is paused (PACE_PAUSED=true). Resolve the open escalation issue to resume.")
        sys.exit(0)

    day = get_current_day()
    plan = load_plan()

    try:
        day_plan = get_day_plan(plan, day)
    except ValueError as e:
        print(f"[PACE] ERROR: {e}")
        sys.exit(1)

    platform = get_platform_adapter()

    print(f"[PACE] === Day {day} — {day_plan['target']} ===")

    # Preflight: ensure context documents exist (runs SCRIBE if missing)
    try:
        run_preflight(day)
    except RuntimeError as exc:
        write_job_summary(day, "ABORT", None, None, None, None, abort_reason=str(exc), platform=platform)
        print(f"[PACE] Day {day}: Preflight failed — {exc}")
        sys.exit(1)

    # Human gate day: open PR/MR and stop
    if day_plan.get("human_gate"):
        print(f"[PACE] Day {day}: Human review gate. Opening PR/MR...")
        platform.open_review_pr(day, PACE_DIR)
        print("[PACE] Review gate opened. Loop will pause until human approval.")
        sys.exit(0)

    recent_gates = get_recent_gate_reports(day)
    try:
        shipped = run_cycle(day, day_plan, recent_gates, platform)
    except CycleAbortError as exc:
        write_job_summary(day, "ABORT", None, None, None, None, abort_reason=str(exc), platform=platform)
        print(f"[PACE] Day {day}: Cycle aborted — {exc}")
        print("[PACE] Fix the issue above and re-run this day. No escalation issue opened.")
        sys.exit(1)

    day_dir = PACE_DIR / f"day-{day}"
    _, _, gate_report, sentinel_report, conduit_report = _load_artifacts_for_summary(day_dir)

    if not shipped:
        print(f"[PACE] Day {day}: Pipeline exhausted retries — opening escalation issue...")
        (day_dir / "escalated").touch()
        platform.open_escalation_issue(day, day_dir)
        write_job_summary(day, "HOLD", _load_story(day_dir), gate_report, sentinel_report, conduit_report, platform=platform)
        update_progress_md(day)
        commit_artifact(PROGRESS_FILE, f"Day {day}: PROGRESS.md update — HOLD/escalated")
        print("[PACE] Escalation issue opened. Set PACE_PAUSED=true or fix and re-run.")
        sys.exit(1)

    story_card = _load_story(day_dir)
    write_job_summary(day, "SHIP", story_card, gate_report, sentinel_report, conduit_report, platform=platform)
    update_progress_md(day)
    commit_artifact(PROGRESS_FILE, f"Day {day}: PROGRESS.md update — SHIP")
    print(f"[PACE] === Day {day} complete — SHIPPED ===")
    sys.exit(0)


def _load_story(day_dir: Path) -> dict | None:
    f = day_dir / "story.md"
    return yaml.safe_load(f.read_text()) if f.exists() else None


def _load_artifacts_for_summary(day_dir: Path) -> tuple:
    def _load(name):
        f = day_dir / name
        return yaml.safe_load(f.read_text()) if f.exists() else None

    return (
        _load("story.md"),
        _load("handoff.md"),
        _load("gate.md"),
        _load("sentinel.md"),
        _load("conduit.md"),
    )


if __name__ == "__main__":
    main()
