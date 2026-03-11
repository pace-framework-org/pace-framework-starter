#!/usr/bin/env python3
"""PACE Orchestrator — drives the daily PRIME -> FORGE -> GATE -> SENTINEL -> CONDUIT cycle.

Usage:
    PACE_DAY=1 ANTHROPIC_API_KEY=... python orchestrator.py

Environment variables:
    PACE_DAY              Current day number (1-N, where N = sprint.duration_days in config)
    ANTHROPIC_API_KEY     Anthropic API key
    PACE_PAUSED           Set to "true" to skip execution (loop is paused)
    PACE_SPEND_TODAY      Accumulated spend today before this run (set by pace.yml)

Platform credentials (set the ones matching your platform.type in pace.config.yaml):
    GitHub:   GITHUB_TOKEN, GITHUB_REPOSITORY
    GitLab:   GITLAB_TOKEN, GITLAB_PROJECT [, GITLAB_URL]
    Jenkins:  JENKINS_URL, JENKINS_USER, JENKINS_TOKEN, JENKINS_JOB_NAME
    Local:    (none required)
"""

import atexit
import os
import shlex
import sys
import yaml
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platforms.base import CIAdapter, TrackerAdapter

# Add the pace directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from agents.prime import run_prime, run_prime_refine
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
from platforms import get_ci_adapter, get_tracker_adapter
from platforms.base import CIAdapter, TrackerAdapter
from reporter import write_job_summary, update_progress_md
import spend_tracker

REPO_ROOT = Path(__file__).parent.parent
PACE_DIR = REPO_ROOT / ".pace"
PLAN_FILE = Path(__file__).parent / "plan.yaml"
PROGRESS_FILE = REPO_ROOT / "PROGRESS.md"
MAX_RETRIES = 1


class CycleAbortError(Exception):
    """Raised when a cycle cannot start due to an infrastructure failure (e.g. PRIME error).
    Unlike a HOLD, this does not trigger a platform escalation issue."""


def _update_daily_spend(run_cost_usd: float, ci: "CIAdapter | None" = None) -> None:
    """Accumulate this run's cost into PACE_DAILY_SPEND via the CI adapter.

    PACE_SPEND_TODAY is injected by pace.yml's budget-check step and holds the
    accumulated spend from earlier runs today (reset to 0 on a new calendar day).
    Delegates to ci.set_variable() — each adapter handles persistence
    appropriately (GitHub writes to Actions variables; others may no-op).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(os.environ.get("PACE_REPORTER_TIMEZONE", "UTC"))
    today = datetime.now(tz).date().isoformat()
    prior = float(os.environ.get("PACE_SPEND_TODAY", "0") or "0")
    new_total = prior + run_cost_usd
    if ci is not None:
        ci.set_variable("PACE_DAILY_SPEND", f"{new_total:.4f}")
        ci.set_variable("PACE_DAILY_SPEND_DATE", today)
    print(f"[PACE] Daily spend updated: ${new_total:.4f} (this run: ${run_cost_usd:.4f})")


def _scope_check(story_card: dict, analysis_model: str) -> dict:
    """Single Haiku call that predicts FORGE iteration count and cost.

    Returns a dict with keys: predicted_iterations, predicted_cost_usd, reasoning.
    Returns an empty dict on any failure — the check is non-fatal.
    """
    try:
        from llm import get_llm_adapter
        adapter = get_llm_adapter(model=analysis_model)
        story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)
        system = (
            "You are a PACE cost estimator. Given a story card, predict how many agentic loop "
            "iterations FORGE (a code-writing agent using claude-sonnet-4-6) will need and the "
            "total Anthropic API cost in USD.\n"
            "Typical ranges: simple (≤3 AC, 1-2 files) ≈ $0.30-0.80 | "
            "medium (4-5 AC, 2-3 files) ≈ $0.80-1.50 | "
            "complex (6+ AC, 3+ files or CLI commands) ≈ $1.50-3.50+\n"
            "Respond ONLY with this YAML — no other text:\n"
            "```yaml\n"
            "predicted_iterations: <integer>\n"
            "predicted_cost_usd: <float>\n"
            "reasoning: \"<one concise sentence>\"\n"
            "```"
        )
        import re
        raw = adapter.complete(system, f"Story card:\n{story_yaml}", max_tokens=256).strip()
        match = re.search(r"```(?:yaml)?\s*(.*?)```", raw, re.DOTALL)
        return yaml.safe_load(match.group(1).strip() if match else raw) or {}
    except Exception as exc:
        print(f"[PACE] SCOPE check failed (non-fatal): {exc}")
        return {}


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


def run_cycle(day: int, day_plan: dict, recent_gates: list[str], ci: CIAdapter, tracker: TrackerAdapter) -> tuple[bool, str]:
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

    # Step 1b: SCOPE — refine story if AC count or predicted cost exceeds thresholds
    cfg = load_config()
    cc = cfg.cost_control
    for _refine_round in range(2):  # max 2 refinement rounds
        ac_count = len(story_card.get("acceptance", []))
        needs_refine = False
        refine_reason = ""

        if cc.max_story_ac > 0 and ac_count > cc.max_story_ac:
            refine_reason = f"Story has {ac_count} acceptance criteria (max {cc.max_story_ac})."
            needs_refine = True

        if not needs_refine and cc.max_story_cost_usd > 0:
            scope = _scope_check(story_card, cfg.llm.analysis_model)
            predicted = float(scope.get("predicted_cost_usd") or 0)
            if predicted > cc.max_story_cost_usd:
                refine_reason = (
                    f"SCOPE predicts ${predicted:.2f} (max ${cc.max_story_cost_usd:.2f}). "
                    f"{scope.get('reasoning', '')}"
                )
                needs_refine = True
            if scope:
                print(
                    f"[PACE] SCOPE: ~{scope.get('predicted_iterations')} iterations, "
                    f"~${predicted:.2f} predicted."
                )

        if not needs_refine:
            break

        print(f"[PACE] Day {day}: Refining story — {refine_reason}")
        try:
            story_card, deferred = run_prime_refine(day, story_card, refine_reason, cc.max_story_ac)
        except Exception as exc:
            print(f"[PACE] PRIME refinement failed (non-fatal, proceeding as-is): {exc}")
            break

        if deferred:
            deferred_file = day_dir / "deferred_scope.yaml"
            deferred_file.write_text(yaml.dump({"deferred": deferred}, allow_unicode=True))
            commit_artifact(
                deferred_file,
                f"Day {day}: deferred scope — {len(deferred)} criteria deferred to next day",
            )
            print(f"[PACE] Day {day}: {len(deferred)} criteria deferred to next day.")

        story_file.write_text(yaml.dump(story_card, default_flow_style=False, allow_unicode=True))
        commit_artifact(
            story_file,
            f"Day {day}: PRIME story card (refined — {len(story_card.get('acceptance', []))} AC)",
        )
        print(f"[PACE] Day {day}: Story refined to {len(story_card.get('acceptance', []))} AC.")

    open_backlog = load_open_backlog() if is_clearance_day else []
    if is_clearance_day and open_backlog:
        print(f"[PACE] Day {day}: Clearance day — {len(open_backlog)} open advisory item(s) to resolve.")

    # Tracks whether the one advisory retry has been used for each agent this day
    advisory_attempt: dict[str, bool] = {"SENTINEL": False, "CONDUIT": False}
    hold_reason: str | None = None

    _cycle_cost_before = spend_tracker.total_usd()  # captures full pipeline cost for this day

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
        _forge_cost_before = spend_tracker.total_usd()
        try:
            handoff = run_forge(day, story_card, forge_hold)
        except Exception as exc:
            print(f"[PACE] FORGE failed with exception: {exc}")
            hold_reason = f"FORGE exception: {exc}"
            if attempt > MAX_RETRIES:
                return False, hold_reason
            continue

        handoff["forge_cost_usd"] = round(spend_tracker.total_usd() - _forge_cost_before, 4)
        handoff_file = day_dir / "handoff.md"
        handoff_file.write_text(yaml.dump(handoff, default_flow_style=False, allow_unicode=True))
        commit_artifact(handoff_file, f"Day {day}: FORGE handoff note (attempt {attempt})")

        # Step 2b: Wait for CI
        commit_sha = handoff.get("commit", "")
        ci_result: dict | None = None
        if commit_sha:
            print(f"[PACE] Day {day}: Waiting for CI on commit {commit_sha}...")
            ci_result = ci.wait_for_commit_ci(commit_sha)
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
                return False, hold_reason
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
                return False, hold_reason
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
                    tracker.push_advisory_items(day, new_items, "SENTINEL")

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
                return False, hold_reason
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
                    tracker.push_advisory_items(day, new_items, "CONDUIT")

        if conduit_decision == "SHIP" and is_clearance_day and conduit_backlog:
            clear_advisory_items("CONDUIT")
            print(f"[PACE] Day {day}: CONDUIT cleared advisory backlog.")

        commit_artifact(conduit_file, f"Day {day}: CONDUIT report — {conduit_decision} attempt {attempt}")

        # Clearance day: verify all open items were resolved
        if is_clearance_day and open_backlog:
            remaining = load_open_backlog()
            if remaining:
                print(f"[PACE] Day {day}: Clearance day FAILED — {len(remaining)} advisory item(s) still open.")
                return False, "Clearance day: advisory items still open after all agents ran"

        # All checks passed — write cycle cost artifact and SHIP
        cycle_cost_usd = round(spend_tracker.total_usd() - _cycle_cost_before, 4)
        cycle_file = day_dir / "cycle.md"
        cycle_file.write_text(yaml.dump({
            "day": day,
            "cycle_cost_usd": cycle_cost_usd,
            "forge_cost_usd": handoff.get("forge_cost_usd", 0.0),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, default_flow_style=False))
        commit_artifact(cycle_file, f"Day {day}: cycle cost record")
        ci.post_daily_summary(day, gate_report)
        print(f"[PACE] Day {day}: GATE + SENTINEL + CONDUIT — SHIP (cycle cost: ${cycle_cost_usd:.4f})")
        return True, ""

    return False, hold_reason or "Unknown — retries exhausted"


def _run_day_zero(plan: dict, replan: bool = False) -> None:
    """Day 0 planning phase — estimate sprint cost and pre-populate PROGRESS.md.

    Args:
        plan: Parsed plan.yaml dict.
        replan: When True (PACE_REPLAN=true), re-estimates only remaining days
                while preserving actuals for completed days.
    """
    from planner import run_planner

    cfg = load_config()
    mode = "Re-planning" if replan else "Sprint Planning & Cost Estimation"
    print(f"[PACE] === Day 0 — {mode} ===")
    if replan:
        print("[PACE] Re-plan mode: completed day actuals will be preserved.")

    _plan_cost_before = spend_tracker.total_usd()
    report = run_planner(plan, cfg.llm.model, replan=replan)
    planning_cost = round(spend_tracker.total_usd() - _plan_cost_before, 4)

    # Write final planning cost back to the report
    planner_file = PACE_DIR / "day-0" / "planner.md"
    report["planning_cost_usd"] = planning_cost
    planner_file.write_text(yaml.dump(report, default_flow_style=False, allow_unicode=True))
    commit_msg = "Day 0: Sprint plan re-estimated with actuals" if replan else "Day 0: Sprint plan with cost estimates"
    commit_artifact(planner_file, commit_msg)

    print(f"[PACE] Day 0 planning cost: ${planning_cost:.4f}")

    update_progress_md(0)
    commit_artifact(PROGRESS_FILE, "Day 0: PROGRESS.md — sprint plan initialized")

    print(f"[PACE] === Day 0 complete — Sprint plan ready, Day 1 begins next run ===")


def main() -> None:
    # Mutable container so the spend flush closure can reference platform after it's created.
    _platform_ref: list["CIAdapter | None"] = [None]

    def _flush_spend() -> None:
        cost = spend_tracker.total_usd()
        if cost > 0:
            print(f"[PACE] API usage this run:\n{spend_tracker.summary()}")
            _update_daily_spend(cost, _platform_ref[0])

    atexit.register(_flush_spend)

    if os.environ.get("PACE_PAUSED", "").lower() == "true":
        print("[PACE] Loop is paused (PACE_PAUSED=true). Resolve the open escalation issue to resume.")
        sys.exit(0)

    day = get_current_day()
    plan = load_plan()

    # Day 0 is the planning phase — run cost estimation for all sprint days.
    # Set PACE_REPLAN=true to refresh estimates for remaining days while preserving actuals.
    if day == 0:
        replan = os.environ.get("PACE_REPLAN", "").lower() == "true"
        _run_day_zero(plan, replan=replan)
        sys.exit(0)

    try:
        day_plan = get_day_plan(plan, day)
    except ValueError as e:
        print(f"[PACE] ERROR: {e}")
        sys.exit(1)

    ci = get_ci_adapter()
    tracker = get_tracker_adapter()
    _platform_ref[0] = ci

    print(f"[PACE] === Day {day} — {day_plan['target']} ===")

    # Preflight: ensure context documents exist (runs SCRIBE if missing)
    try:
        run_preflight(day)
    except RuntimeError as exc:
        write_job_summary(day, "ABORT", None, None, None, None, abort_reason=str(exc), ci=ci)
        print(f"[PACE] Day {day}: Preflight failed — {exc}")
        sys.exit(1)

    # Human gate day: open PR/MR and stop
    if day_plan.get("human_gate"):
        print(f"[PACE] Day {day}: Human review gate. Opening PR/MR...")
        ci.open_review_pr(day, PACE_DIR)
        print("[PACE] Review gate opened. Loop will pause until human approval.")
        sys.exit(0)

    recent_gates = get_recent_gate_reports(day)
    try:
        shipped, _last_hold_reason = run_cycle(day, day_plan, recent_gates, ci, tracker)
    except CycleAbortError as exc:
        write_job_summary(day, "ABORT", None, None, None, None, abort_reason=str(exc), ci=ci)
        print(f"[PACE] Day {day}: Cycle aborted — {exc}")
        print("[PACE] Fix the issue above and re-run this day. No escalation issue opened.")
        sys.exit(1)

    day_dir = PACE_DIR / f"day-{day}"
    _, _, gate_report, sentinel_report, conduit_report = _load_artifacts_for_summary(day_dir)

    if not shipped:
        print(f"[PACE] Day {day}: Pipeline exhausted retries — opening escalation issue...")
        (day_dir / "escalated").touch()
        tracker.open_escalation_issue(day, day_dir, hold_reason=_last_hold_reason)
        ci.set_variable("PACE_PAUSED", "true")
        write_job_summary(day, "HOLD", _load_story(day_dir), gate_report, sentinel_report, conduit_report, ci=ci)
        update_progress_md(day)
        commit_artifact(PROGRESS_FILE, f"Day {day}: PROGRESS.md update — HOLD/escalated")
        print("[PACE] Escalation issue opened and PACE_PAUSED set to true. Resolve the issue, then set PACE_PAUSED=false to resume.")
        sys.exit(1)

    story_card = _load_story(day_dir)
    write_job_summary(day, "SHIP", story_card, gate_report, sentinel_report, conduit_report, ci=ci)
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
