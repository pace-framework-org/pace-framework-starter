"""PACE Planner — Day 0 sprint planning, cost estimation, and plan-approval pipeline.

Runs before Day 1 begins. Estimates FORGE cost for every day in plan.yaml
using the main LLM model (same model as FORGE) for accurate cost prediction,
then writes .pace/day-0/planner.md with the per-day breakdown. The orchestrator
fills in planning_cost_usd after the spend tracker finalises.

Re-planning support: set PACE_REPLAN=true with PACE_DAY=0 to refresh estimates
for remaining days while preserving actuals for completed days.

Pipeline mode (--pipeline flag):
    Runs as a standalone CI pipeline (pace-planner.yml). Collects shipped days,
    re-estimates remaining work, writes .pace/shipped.yaml, and sets
    PACE_PAUSED=true so the daily cycle waits for human plan approval.
    The calling workflow commits the artifacts and opens the plan-approval PR.

Usage:
    python pace/planner.py                 # Day 0 planning (called by orchestrator)
    python pace/planner.py --pipeline      # Pipeline mode (called by pace-planner.yml)
    python pace/planner.py --pipeline --replan  # Force re-estimation of all days
"""

import argparse
import os
import re
import shutil
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PACE_DIR = REPO_ROOT / ".pace"
PLAN_FILE = REPO_ROOT / "plan.yaml"


def _estimate_day_cost(target: str, day: int, model: str) -> dict:
    """Single model call estimating FORGE cost for one plan target.

    Uses the main FORGE model (e.g. claude-sonnet-4-6) rather than the cheaper
    analysis model so that predicted costs reflect real execution pricing.
    """
    from llm import get_llm_adapter
    adapter = get_llm_adapter(model=model)
    system = (
        "You are a PACE sprint cost estimator. Given a sprint day target, predict how many "
        "agentic loop iterations FORGE (a code-writing agent using the same model as you) will need "
        "and the estimated Anthropic API cost in USD.\n"
        "Calibrated ranges for claude-sonnet-4-6 ($3.00/$15.00 per M tokens):\n"
        "  simple   (1-2 files, 1-3 acceptance criteria) ≈ $0.50–1.20\n"
        "  medium   (2-4 files, 3-5 acceptance criteria) ≈ $1.20–2.50\n"
        "  complex  (4+ files, 5+ AC, CLI/system work)   ≈ $2.50–5.00+\n"
        "Respond ONLY with this YAML — no other text:\n"
        "```yaml\n"
        "predicted_iterations: <integer>\n"
        "predicted_cost_usd: <float>\n"
        "reasoning: \"<one sentence>\"\n"
        "```"
    )
    raw = adapter.complete(system, f"Day {day} target: {target}", max_tokens=256).strip()
    match = re.search(r"```(?:yaml)?\s*(.*?)```", raw, re.DOTALL)
    result = yaml.safe_load(match.group(1).strip() if match else raw) or {}
    return {
        "day": day,
        "predicted_iterations": int(result.get("predicted_iterations", 10)),
        "predicted_cost_usd": round(float(result.get("predicted_cost_usd", 2.00)), 4),
        "reasoning": str(result.get("reasoning", "")),
    }


def _load_existing_actuals() -> dict[int, float]:
    """Return {day: actual_cycle_cost_usd} for completed days.

    Reads cycle.md (total pipeline cost) first; falls back to handoff.md
    forge_cost_usd for backward compatibility.
    """
    actuals: dict[int, float] = {}
    for day_dir in sorted(PACE_DIR.glob("day-[0-9]*")):
        try:
            day_num = int(day_dir.name.split("-")[1])
        except (IndexError, ValueError):
            continue
        if day_num == 0:
            continue
        cycle_file = day_dir / "cycle.md"
        if cycle_file.exists():
            data = yaml.safe_load(cycle_file.read_text()) or {}
            cost = data.get("cycle_cost_usd")
            if cost is not None:
                actuals[day_num] = float(cost)
                continue
        handoff_file = day_dir / "handoff.md"
        if handoff_file.exists():
            data = yaml.safe_load(handoff_file.read_text()) or {}
            cost = data.get("forge_cost_usd")
            if cost is not None:
                actuals[day_num] = float(cost)
    return actuals


def _iter_stories(plan: dict):
    """Yield (day_num, entry) for both stories and legacy days format."""
    if "stories" in plan:
        for s in plan["stories"]:
            sid = s.get("id", "")
            try:
                day_num = int(sid.split("-")[1])
            except (IndexError, ValueError):
                continue
            yield day_num, s
    else:
        for d in plan.get("days", []):
            yield d["day"], d


def _get_replan_boundary(stories: list[dict]) -> int:
    """Return the index of the last shipped story, or -1 if none are shipped."""
    boundary = -1
    for i, s in enumerate(stories):
        if s.get("status") == "shipped":
            boundary = i
    return boundary


def _backup_plan(plan_file: Path, release_name: str, retention_days: int = 30) -> Path | None:
    """Copy plan_file to .pace/releases/<release>/plan.yaml.bak.<iso-datetime>.

    Prunes backups older than retention_days. Returns the backup path, or None
    if plan_file does not exist.
    """
    if not plan_file.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = PACE_DIR / "releases" / release_name
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"plan.yaml.bak.{ts}"
    shutil.copy2(plan_file, backup_path)
    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    for old in backup_dir.glob("plan.yaml.bak.*"):
        if old != backup_path and old.stat().st_mtime < cutoff:
            old.unlink()
    return backup_path


def run_planner(plan: dict, model: str, replan: bool = False, plan_file: Path | None = None) -> dict:
    """Estimate cost for every day in the sprint plan.

    Writes .pace/day-0/planner.md and returns the planner report dict.
    The planning_cost_usd field starts at 0.0 — the orchestrator updates it
    after the spend tracker records the actual cost of this run.

    Args:
        plan: Parsed plan.yaml dict.
        model: The main LLM model ID used for estimation (should match FORGE's model).
        replan: When True, preserve actuals for completed days and only re-estimate
                days that have not yet been completed.
    """
    if replan:
        # Item 13: refresh context if source docs changed before re-planning
        try:
            from preflight import _check_context_freshness
            _check_context_freshness()
        except Exception as exc:
            print(f"[PACE] Warning: context freshness check skipped in planner: {exc}")
    day_0_dir = PACE_DIR / "day-0"
    day_0_dir.mkdir(parents=True, exist_ok=True)

    # Context versioning (v2.0 — Item 3): bump patch version on every planner write so
    # agents can detect drift between plan-time and execution-time context.
    old_version = plan.get("context_version", "1.0.0")
    try:
        major, minor, patch = (int(x) for x in str(old_version).split("."))
        new_version = f"{major}.{minor}.{patch + 1}"
    except (ValueError, AttributeError):
        new_version = "1.0.1"

    # Detect plan format and normalise to (day_num, entry) pairs
    using_stories = "stories" in plan
    story_entries = list(_iter_stories(plan))

    # Backup plan.yaml before any re-plan write (Item 15)
    if replan and plan_file is not None:
        release_name = str(plan.get("release", "unknown"))
        _backup_plan(plan_file, release_name)

    # Determine which day numbers are already completed
    if using_stories:
        # New format: completion is explicit via status: shipped
        completed_days: set[int] = {
            day_num for day_num, s in story_entries
            if s.get("status") == "shipped"
        }
        existing_actuals: dict[int, float] = {}
    else:
        # Legacy format: completion detected from .pace/day-N/ artifacts
        existing_actuals = _load_existing_actuals() if replan else {}
        completed_days = set(existing_actuals.keys()) if replan else set()

    # Load existing estimates to preserve them for completed days during re-plan
    existing_estimates: dict[int, dict] = {}
    if replan:
        planner_file = day_0_dir / "planner.md"
        if planner_file.exists():
            old_report = yaml.safe_load(planner_file.read_text()) or {}
            for e in old_report.get("estimates", []):
                existing_estimates[e["day"]] = e

    if replan:
        remaining_count = sum(1 for day_num, _ in story_entries if day_num not in completed_days)
        print(
            f"[PACE] Day 0 (re-plan): {len(completed_days)} stories completed, "
            f"re-estimating {remaining_count} remaining using {model}..."
        )
    else:
        print(f"[PACE] Day 0: Estimating cost for {len(story_entries)} sprint days using {model}...")

    estimates = []

    for day, entry in story_entries:
        target = entry.get("target") or entry.get("title", "")

        if entry.get("human_gate"):
            estimates.append({
                "day": day,
                "target": target[:80],
                "predicted_iterations": 0,
                "predicted_cost_usd": 0.0,
                "reasoning": "Human gate day — no FORGE execution.",
                "actual_cost_usd": existing_actuals.get(day),
            })
            print(f"[PACE]   Day {day}: $0.00 (human gate)")
            continue

        # For completed days in re-plan mode: preserve existing estimate, attach actual
        if replan and day in completed_days:
            actual_cost = existing_actuals.get(day)
            est = existing_estimates.get(day, {
                "day": day,
                "target": target[:80],
                "predicted_iterations": 0,
                "predicted_cost_usd": 0.0,
                "reasoning": "Estimate not available (completed before re-plan).",
            })
            est["actual_cost_usd"] = actual_cost
            estimates.append(est)
            cost_str = f"${actual_cost:.2f}" if actual_cost is not None else "N/A"
            print(f"[PACE]   Day {day}: COMPLETED — actual {cost_str} (est ${est.get('predicted_cost_usd', 0):.2f})")
            continue

        try:
            est = _estimate_day_cost(target, day, model)
            est["target"] = target[:80]
            estimates.append(est)
            print(f"[PACE]   Day {day}: ~${est['predicted_cost_usd']:.2f} — {est['reasoning']}")
        except Exception as exc:
            print(f"[PACE]   Day {day}: estimation failed ({exc}) — using default $2.00")
            estimates.append({
                "day": day,
                "target": target[:80],
                "predicted_iterations": 10,
                "predicted_cost_usd": 2.00,
                "reasoning": f"Estimation failed: {exc}",
            })

    total_estimated = round(sum(e["predicted_cost_usd"] for e in estimates), 4)

    report = {
        "day": 0,
        "agent": "PLANNER",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "context_version": new_version,   # bumped from plan.yaml on every planner write
        "estimation_model": model,
        "total_estimated_usd": total_estimated,
        "planning_cost_usd": 0.0,  # Filled in by orchestrator after spend tracking
        "replan": replan,
        "estimates": estimates,
    }

    planner_file = day_0_dir / "planner.md"
    planner_file.write_text(yaml.dump(report, default_flow_style=False, allow_unicode=True))

    print(f"[PACE] Day 0: Total estimated sprint cost: ${total_estimated:.2f}")

    return report


# ---------------------------------------------------------------------------
# Shipped-days manifest (pace-planner pipeline)
# ---------------------------------------------------------------------------

def _collect_shipped_days() -> list[int]:
    """Return sorted list of day numbers whose gate decision was SHIP."""
    shipped: list[int] = []
    for gate_file in sorted(PACE_DIR.glob("day-*/gate.md")):
        try:
            day_num = int(gate_file.parent.name.split("-")[1])
            data = yaml.safe_load(gate_file.read_text()) or {}
            if data.get("gate_decision") == "SHIP":
                shipped.append(day_num)
        except (ValueError, IndexError):
            pass
    return shipped


def _write_shipped_manifest(shipped_days: list[int]) -> None:
    """Write .pace/shipped.yaml so re-planner and orchestrator can read it."""
    PACE_DIR.mkdir(parents=True, exist_ok=True)
    content = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shipped_days": shipped_days,
    }
    (PACE_DIR / "shipped.yaml").write_text(
        yaml.dump(content, default_flow_style=False, allow_unicode=True)
    )
    print(f"[PACE] shipped.yaml written ({len(shipped_days)} shipped days: {shipped_days})")


# ---------------------------------------------------------------------------
# Pipeline entrypoint
# ---------------------------------------------------------------------------

def run_pipeline(plan: dict, model: str, force_replan: bool = False) -> None:
    """Pipeline mode: re-estimate remaining work, protect shipped days, pause cycle.

    Called by pace-planner.yml. After this function returns:
      - .pace/day-0/planner.md   — updated cost estimates
      - .pace/shipped.yaml       — protected shipped-day manifest
      - PACE_PAUSED              — set to "true" (Actions variable)

    The workflow YAML then commits these files to pace/plan-approval and opens
    a plan-approval PR. Merging the PR is the human gate before the next sprint
    day runs.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from platforms import get_ci_adapter

    shipped_days = _collect_shipped_days()
    _write_shipped_manifest(shipped_days)

    replan = force_replan or len(shipped_days) > 0
    report = run_planner(plan, model, replan=replan)

    # Pause the daily cycle so it waits for plan-approval PR to be merged
    ci = get_ci_adapter()
    paused = ci.set_variable("PACE_PAUSED", "true")
    if paused:
        print("[PACE] PACE_PAUSED set to true — daily cycle paused pending plan approval.")
    else:
        print("[PACE] Warning: could not set PACE_PAUSED (adapter unavailable). Set it manually.")

    total = report.get("total_estimated_usd", 0.0)
    print(
        f"[PACE] Pipeline complete. "
        f"Total re-estimated cost: ${total:.2f}. "
        f"Commit .pace/day-0/planner.md and .pace/shipped.yaml, then open the plan-approval PR."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PACE Planner")
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Run as a standalone CI pipeline (pace-planner.yml mode)",
    )
    parser.add_argument(
        "--replan",
        action="store_true",
        help="Force re-estimation of all days even if no shipped days exist",
    )
    args = parser.parse_args()

    plan_file = REPO_ROOT / "plan.yaml"
    if not plan_file.exists():
        print("[PACE] ERROR: plan.yaml not found at repo root.")
        sys.exit(1)

    plan_data = yaml.safe_load(plan_file.read_text()) or {}

    sys.path.insert(0, str(Path(__file__).parent))
    from config import load_config
    cfg = load_config()
    llm_model = cfg.llm.model

    if args.pipeline:
        run_pipeline(plan_data, llm_model, force_replan=args.replan)
    else:
        # Original Day 0 mode — called by orchestrator with PACE_REPLAN env var
        do_replan = args.replan or os.environ.get("PACE_REPLAN", "").lower() == "true"
        run_planner(plan_data, llm_model, replan=do_replan)
