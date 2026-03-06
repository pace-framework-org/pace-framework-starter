"""SENTINEL agent — Security and SRE review of FORGE implementations."""

import re
import subprocess
import yaml
import jsonschema
from pathlib import Path
from schemas import SENTINEL_REPORT_SCHEMA
from config import load_config
from llm import get_llm_adapter

REPO_ROOT = Path(__file__).parent.parent.parent


def _scan_for_secrets(repo_root: Path) -> str:
    """Grep source files for common secret patterns."""
    result = subprocess.run(
        (
            r'grep -rn --include="*.go" --include="*.py" --include="*.ts" --include="*.js" '
            r'--include="*.yaml" --include="*.yml" --include="*.json" '
            r'--exclude-dir=".git" --exclude-dir=".venv" --exclude-dir="vendor" '
            r'--exclude-dir="node_modules" --exclude-dir="__pycache__" '
            r'-iE "(password|secret|token|api_key|apikey)\s*[=:]\s*[\"'"'"'][^\"'"'"']{8,}" . 2>&1 | head -50'
        ),
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=30,
    )
    output = (result.stdout + result.stderr).strip()
    return output[:2000] if output else "No hardcoded secret patterns detected."


def _load_context(doc: str) -> str:
    path = REPO_ROOT / ".pace" / "context" / doc
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_sentinel(
    day: int,
    story_card: dict,
    handoff: dict,
    gate_report: dict,
    advisory_backlog: list[dict] | None = None,
) -> dict:
    cfg = load_config()
    adapter = get_llm_adapter()

    system_prompt = f"""You are the Security and SRE Agent (SENTINEL) for {cfg.product_name}.

Your job is to review the implementation for security vulnerabilities and reliability gaps.
You have access to: the Story Card, the FORGE Handoff Note, the Gate Report, a secret pattern scan,
and any open advisory backlog items that must be cleared today.

Security focus:
- Hardcoded secrets, tokens, or credentials in source or config files
- Input validation gaps: command injection, path traversal, shell injection via user-controlled data
- Authentication and authorization boundaries — are they tested?
- Sensitive data written to logs or error messages
- Dependency hygiene: new dependencies introduced without justification

SRE / Reliability focus:
- Missing timeouts on I/O operations (HTTP calls, subprocess, file reads)
- Unhandled error paths that could panic, crash silently, or leave resources open
- Missing structured error context — errors swallowed with no log or return
- Resource leaks: unclosed files, open connections
- Retry logic and idempotency where data is written to external systems

TDD lens:
- Are there tests for invalid or malicious inputs (not just happy-path)?
- Are error paths exercised by tests?
- Are security-boundary conditions (empty input, oversized input, special characters) tested?

You MUST respond with ONLY a valid YAML block — no prose before or after. Format:

```yaml
day: <integer>
agent: SENTINEL
findings:
  - check: "What was checked"
    result: PASS
    evidence: "Specific file/line/test that confirms this"
  - check: "What was checked"
    result: ADVISORY
    evidence: "Non-blocking concern with specific location"
  - check: "What was checked"
    result: FAIL
    evidence: "Blocking vulnerability with specific location"
advisories:
  - "Advisory finding text (must correspond to an ADVISORY result above)"
blockers:
  - "Blocking finding text (must correspond to a FAIL result above)"
sentinel_decision: SHIP
hold_reason: ""
```

Rules:
- sentinel_decision SHIP: no FAIL results.
- sentinel_decision HOLD: at least one FAIL result. hold_reason must be actionable for FORGE.
- sentinel_decision ADVISORY: no FAIL, but at least one ADVISORY result.
- FAIL = exploitable vulnerability, credential exposure, or silent data-loss risk.
- ADVISORY = reduces operational risk but is not immediately exploitable or service-impacting.
- Do not flag style, formatting, test coverage percentages, or concerns outside security/SRE scope.
- If advisory backlog items are provided, evaluate each one explicitly as a check.
- Evidence must cite actual file paths, line numbers, or test names. No assumptions.
- Respond with ONLY the yaml block. No other text."""

    story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)
    handoff_yaml = yaml.dump(handoff, default_flow_style=False, allow_unicode=True)
    gate_yaml = yaml.dump(gate_report, default_flow_style=False, allow_unicode=True)
    secrets_scan = _scan_for_secrets(REPO_ROOT)
    security_ctx = _load_context("security.md")
    security_section = f"\nSecurity Context:\n{security_ctx}\n" if security_ctx else ""

    backlog_section = ""
    if advisory_backlog:
        backlog_yaml = yaml.dump(advisory_backlog, default_flow_style=False, allow_unicode=True)
        backlog_section = (
            f"\nOpen Advisory Backlog (Day {day} is a clearance day — all items below must be resolved):\n"
            f"```\n{backlog_yaml}\n```\n"
        )

    user_message = f"""Story Card:
{story_yaml}
FORGE Handoff Note:
{handoff_yaml}
GATE Report:
{gate_yaml}
{security_section}
Secret pattern scan:
```
{secrets_scan}
```
{backlog_section}
Review the implementation for security vulnerabilities and SRE reliability gaps.
Produce the SENTINEL Report YAML for Day {day}."""

    raw = adapter.complete(system_prompt, user_message, max_tokens=4096).strip()
    match = re.search(r"```(?:yaml)?\s*(.*?)```", raw, re.DOTALL)
    yaml_text = match.group(1).strip() if match else raw

    sentinel_report = yaml.safe_load(yaml_text)
    sentinel_report["day"] = day
    sentinel_report["agent"] = "SENTINEL"
    sentinel_report.setdefault("advisories", [])
    sentinel_report.setdefault("blockers", [])
    sentinel_report.setdefault("hold_reason", "")

    jsonschema.validate(sentinel_report, SENTINEL_REPORT_SCHEMA)
    return sentinel_report
