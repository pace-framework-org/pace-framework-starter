"""PACE Planner — Day 0 sprint planning and cost estimation.

Runs before Day 1 begins. Estimates FORGE cost for every day in plan.yaml
using the main LLM model (same model as FORGE) for accurate cost prediction,
then writes .pace/day-0/planner.md with the per-day breakdown. The orchestrator
fills in planning_cost_usd after the spend tracker finalises.

Re-planning support: set PACE_REPLAN=true with PACE_DAY=0 to refresh estimates
for remaining days while preserving actuals for completed days.
"""

import re
import yaml
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PACE_DIR = REPO_ROOT / ".pace"


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


def run_planner(plan: dict, model: str, replan: bool = False) -> dict:
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

    days = plan.get("days", [])

    # Load existing actuals when re-planning so completed days are not overwritten
    existing_actuals: dict[int, float] = _load_existing_actuals() if replan else {}

    # Load existing estimates to preserve them for completed days during re-plan
    existing_estimates: dict[int, dict] = {}
    if replan:
        planner_file = day_0_dir / "planner.md"
        if planner_file.exists():
            old_report = yaml.safe_load(planner_file.read_text()) or {}
            for e in old_report.get("estimates", []):
                existing_estimates[e["day"]] = e

    if replan:
        completed_days = set(existing_actuals.keys())
        remaining = [d for d in days if d["day"] not in completed_days]
        print(
            f"[PACE] Day 0 (re-plan): {len(completed_days)} days completed with actuals, "
            f"re-estimating {len(remaining)} remaining days using {model}..."
        )
    else:
        print(f"[PACE] Day 0: Estimating cost for {len(days)} sprint days using {model}...")

    estimates = []

    for entry in days:
        day = entry["day"]
        target = entry.get("target", "")

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
        if replan and day in existing_actuals:
            est = existing_estimates.get(day, {
                "day": day,
                "target": target[:80],
                "predicted_iterations": 0,
                "predicted_cost_usd": 0.0,
                "reasoning": "Estimate not available (completed before re-plan).",
            })
            est["actual_cost_usd"] = existing_actuals[day]
            estimates.append(est)
            print(
                f"[PACE]   Day {day}: COMPLETED — actual ${existing_actuals[day]:.2f} "
                f"(est ${est.get('predicted_cost_usd', 0):.2f})"
            )
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
