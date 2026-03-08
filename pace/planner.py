"""PACE Planner — Day 0 sprint planning and cost estimation.

Runs before Day 1 begins. Estimates FORGE cost for every day in plan.yaml
using single analysis-model calls, then writes .pace/day-0/planner.md with
the per-day breakdown. The orchestrator fills in planning_cost_usd after the
spend tracker finalises.
"""

import re
import yaml
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PACE_DIR = REPO_ROOT / ".pace"


def _estimate_day_cost(target: str, day: int, analysis_model: str) -> dict:
    """Single analysis_model call estimating FORGE cost for one plan target."""
    from llm import get_llm_adapter
    adapter = get_llm_adapter(model=analysis_model)
    system = (
        "You are a PACE sprint cost estimator. Given a sprint day target, predict how many "
        "agentic loop iterations FORGE (a code-writing agent) will need "
        "and the estimated Anthropic API cost in USD.\n"
        "Typical ranges:\n"
        "  simple   (1-2 files, 1-3 acceptance criteria) ≈ $0.20–0.60\n"
        "  medium   (2-4 files, 3-5 acceptance criteria) ≈ $0.60–1.20\n"
        "  complex  (4+ files, 5+ AC, CLI/system work)   ≈ $1.20–3.00+\n"
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
        "predicted_cost_usd": round(float(result.get("predicted_cost_usd", 0.80)), 4),
        "reasoning": str(result.get("reasoning", "")),
    }


def run_planner(plan: dict, analysis_model: str) -> dict:
    """Estimate cost for every day in the sprint plan.

    Writes .pace/day-0/planner.md and returns the planner report dict.
    The planning_cost_usd field starts at 0.0 — the orchestrator updates it
    after the spend tracker records the actual cost of this run.
    """
    day_0_dir = PACE_DIR / "day-0"
    day_0_dir.mkdir(parents=True, exist_ok=True)

    days = plan.get("days", [])
    estimates = []

    print(f"[PACE] Day 0: Estimating cost for {len(days)} sprint days...")

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
            })
            print(f"[PACE]   Day {day}: $0.00 (human gate)")
            continue

        try:
            est = _estimate_day_cost(target, day, analysis_model)
            est["target"] = target[:80]
            estimates.append(est)
            print(f"[PACE]   Day {day}: ~${est['predicted_cost_usd']:.2f} — {est['reasoning']}")
        except Exception as exc:
            print(f"[PACE]   Day {day}: estimation failed ({exc}) — using default $0.80")
            estimates.append({
                "day": day,
                "target": target[:80],
                "predicted_iterations": 10,
                "predicted_cost_usd": 0.80,
                "reasoning": f"Estimation failed: {exc}",
            })

    total_estimated = round(sum(e["predicted_cost_usd"] for e in estimates), 4)

    report = {
        "day": 0,
        "agent": "PLANNER",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_estimated_usd": total_estimated,
        "planning_cost_usd": 0.0,  # Filled in by orchestrator after spend tracking
        "estimates": estimates,
    }

    planner_file = day_0_dir / "planner.md"
    planner_file.write_text(yaml.dump(report, default_flow_style=False, allow_unicode=True))

    print(f"[PACE] Day 0: Total estimated sprint cost: ${total_estimated:.2f}")

    return report
