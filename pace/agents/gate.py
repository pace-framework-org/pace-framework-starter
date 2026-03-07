"""GATE agent — validates implementations against Story Card acceptance criteria."""

import re
import subprocess
import yaml
import jsonschema
from pathlib import Path
from schemas import GATE_REPORT_SCHEMA
from config import load_config
from llm import get_llm_adapter

REPO_ROOT = Path(__file__).parent.parent.parent


def _run_tests(test_command: str) -> str:
    """Run the configured test suite and return combined stdout/stderr (capped at 6000 chars)."""
    result = subprocess.run(
        test_command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    output = result.stdout + result.stderr
    return output[:6000] if len(output) > 6000 else output


def _run_integration_checks() -> str:
    """Run basic integration smoke tests if a Makefile target exists."""
    result = subprocess.run(
        "make test-integration 2>&1 | head -100",
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    if result.returncode == 2:  # make target not found
        return "No integration test target found (make test-integration not defined yet)."
    return (result.stdout + result.stderr)[:3000]


def _load_context(doc: str) -> str:
    path = REPO_ROOT / ".pace" / "context" / doc
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_gate(day: int, story_card: dict, handoff: dict, ci_result: dict | None = None) -> dict:
    cfg = load_config()
    adapter = get_llm_adapter()

    test_output = _run_tests(cfg.tech.test_command)
    integration_output = _run_integration_checks()

    system_prompt = f"""You are the Quality Agent (GATE) for {cfg.product_name}.

Your job is to determine whether today's implementation satisfies today's acceptance criteria.
You have access to: the Story Card, the FORGE Handoff Note, the test runner output, and the CI run result.

You MUST respond with ONLY a valid YAML block — no prose before or after. Format:

```yaml
day: <integer>
agent: GATE
criteria_results:
  - criterion: "Criterion text from story card"
    result: PASS
    evidence: "What confirms this"
blockers:
  - "Description of any FAIL"
deferred:
  - "Any PARTIAL mapped to out_of_scope"
gate_decision: SHIP
hold_reason: ""
```

Rules:
- gate_decision must be SHIP only if ALL criteria are PASS or PARTIAL-with-justification.
- A PARTIAL is only valid if it maps exactly to an item in the story card's out_of_scope list.
- gate_decision HOLD requires a specific, actionable hold_reason for FORGE.
- Do not fail on style, docs, or non-functional concerns not in acceptance criteria.
- Evidence must cite actual output — test names, log lines, exit codes, CI conclusion. No assumptions.
- For criteria that require CI to be green: use the CI Run Result section as authoritative evidence.
  A conclusion of "success" is a PASS. A conclusion of "failure" is a FAIL with the run URL as evidence.
  A conclusion of "timeout" or "no_runs" means CI evidence is unavailable — mark as PARTIAL only if
  the story card's out_of_scope list includes a CI deferral; otherwise mark FAIL.
- Respond with ONLY the yaml block. No other text."""

    story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)
    handoff_yaml = yaml.dump(handoff, default_flow_style=False, allow_unicode=True)
    engineering_ctx = _load_context("engineering.md")
    engineering_section = f"\nEngineering Context (module map and conventions):\n{engineering_ctx}\n" if engineering_ctx else ""

    tdd_confirmed = handoff.get("tdd_red_phase_confirmed", False)
    tdd_section = (
        "TDD Red Phase: confirmed (FORGE called confirm_red_phase before writing implementation)\n"
        if tdd_confirmed
        else "TDD Red Phase: NOT confirmed — FORGE did not call confirm_red_phase\n"
    )

    if ci_result:
        ci_section = f"""CI Run Result:
- Conclusion: {ci_result.get('conclusion', 'unknown')}
- Workflow: {ci_result.get('name', 'N/A')}
- Commit SHA: {ci_result.get('sha', 'N/A')}
- URL: {ci_result.get('url') or 'N/A'}
"""
    else:
        ci_section = "CI Run Result: not available (no commit SHA in handoff)\n"

    user_message = f"""Story Card:
{story_yaml}

FORGE Handoff Note:
{handoff_yaml}
{engineering_section}
{tdd_section}
{ci_section}
Test runner output ({cfg.tech.test_command}):
```
{test_output}
```

Integration checks:
```
{integration_output}
```

Evaluate all acceptance criteria and produce the Gate Report YAML for Day {day}."""

    raw = adapter.complete(system_prompt, user_message, max_tokens=4096).strip()
    match = re.search(r"```(?:yaml)?\s*(.*?)```", raw, re.DOTALL)
    yaml_text = match.group(1).strip() if match else raw

    gate_report = yaml.safe_load(yaml_text)
    gate_report["day"] = day
    gate_report["agent"] = "GATE"
    gate_report.setdefault("blockers", [])
    gate_report.setdefault("deferred", [])
    gate_report.setdefault("hold_reason", "")

    jsonschema.validate(gate_report, GATE_REPORT_SCHEMA)
    return gate_report
