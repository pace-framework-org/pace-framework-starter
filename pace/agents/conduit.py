"""CONDUIT agent — DevOps review of CI/CD pipelines and infrastructure configuration."""

import re
import yaml
import jsonschema
from pathlib import Path
from schemas import CONDUIT_REPORT_SCHEMA
from config import load_config
from llm import get_analysis_adapter

REPO_ROOT = Path(__file__).parent.parent.parent


def _read_ci_workflows(repo_root: Path) -> str:
    """Read all GitHub Actions workflow files."""
    workflows_dir = repo_root / ".github" / "workflows"
    if not workflows_dir.exists():
        return "No .github/workflows directory found."
    parts = []
    for wf in sorted(workflows_dir.glob("*.yml")):
        content = wf.read_text(encoding="utf-8")
        parts.append(f"=== {wf.name} ===\n{content}")
    combined = "\n\n".join(parts)
    return combined[:5000] if len(combined) > 5000 else combined


def _read_makefile(repo_root: Path) -> str:
    makefile = repo_root / "Makefile"
    if not makefile.exists():
        return "No Makefile found."
    content = makefile.read_text(encoding="utf-8")
    return content[:2000] if len(content) > 2000 else content


def _load_context(doc: str) -> str:
    path = REPO_ROOT / ".pace" / "context" / doc
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_conduit(
    day: int,
    story_card: dict,
    handoff: dict,
    sentinel_report: dict,
    advisory_backlog: list[dict] | None = None,
) -> dict:
    cfg = load_config()
    adapter = get_analysis_adapter()

    system_prompt = f"""You are the DevOps Agent (CONDUIT) for {cfg.product_name}.

Your job is to review CI/CD pipelines, build scripts, and infrastructure configuration.
You have access to: the Story Card, the FORGE Handoff Note, the SENTINEL Report,
CI/CD workflow files, and any open advisory backlog items that must be cleared today.

CI/CD focus:
- Workflow correctness: step ordering, condition expressions, job dependencies
- Action version pinning: flag @master or @latest references (prefer tagged versions or commit SHAs)
- Secret and env var handling: no secrets echoed to logs, proper masking
- Missing workflow triggers or overly broad permissions
- Workflow steps that would prevent a failed test from blocking the merge

Build & Packaging focus:
- Dependency consistency: lock files in sync after changes
- Makefile targets referenced in CI must exist and be correct
- Build reproducibility: pinned dependency versions, no network fetches bypassing the lock file
- Working directory assumptions that break when CI changes context

Deployment & Ops focus:
- Environment variable documentation: new required vars must be noted in handoff or README
- No hardcoded environment-specific values (hostnames, ports, paths) in shared config
- Config changes that lack a rollback path

TDD lens:
- Does CI run lint/vet before tests?
- Does CI run all tests (unit + integration) before any deployment step?
- Would a failing test actually block a merge or just produce a warning?

You MUST respond with ONLY a valid YAML block — no prose before or after. Format:

```yaml
day: <integer>
agent: CONDUIT
findings:
  - check: "What was checked"
    result: PASS
    evidence: "Specific file/step/line that confirms this"
  - check: "What was checked"
    result: ADVISORY
    evidence: "Non-blocking concern with specific location"
  - check: "What was checked"
    result: FAIL
    evidence: "Blocking issue with specific location"
advisories:
  - "Advisory finding text (must correspond to an ADVISORY result above)"
blockers:
  - "Blocking finding text (must correspond to a FAIL result above)"
conduit_decision: SHIP
hold_reason: ""
```

Rules:
- conduit_decision SHIP: no FAIL results.
- conduit_decision HOLD: at least one FAIL result. hold_reason must be actionable for FORGE.
- conduit_decision ADVISORY: no FAIL, but at least one ADVISORY result.
- FAIL = broken CI that prevents deployment, leaked secrets in pipeline, or non-reproducible build.
- ADVISORY = suboptimal configuration that increases operational risk but does not break deployment.
- Do not flag style, formatting, or concerns outside DevOps/CI/CD scope.
- If advisory backlog items are provided, evaluate each one explicitly as a check.
- Evidence must cite actual workflow file names, step names, or job names. No assumptions.
- Respond with ONLY the yaml block. No other text."""

    story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)
    handoff_yaml = yaml.dump(handoff, default_flow_style=False, allow_unicode=True)
    sentinel_yaml = yaml.dump(sentinel_report, default_flow_style=False, allow_unicode=True)
    ci_workflows = _read_ci_workflows(REPO_ROOT)
    makefile = _read_makefile(REPO_ROOT)
    devops_ctx = _load_context("devops.md")
    devops_section = f"\nDevOps Context:\n{devops_ctx}\n" if devops_ctx else ""

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
SENTINEL Report:
{sentinel_yaml}
{devops_section}
CI/CD Workflow files:
```yaml
{ci_workflows}
```
Makefile:
```
{makefile}
```
{backlog_section}
Review the CI/CD pipeline and DevOps configuration.
Produce the CONDUIT Report YAML for Day {day}."""

    raw = adapter.complete(system_prompt, user_message, max_tokens=4096).strip()
    match = re.search(r"```(?:yaml)?\s*(.*?)```", raw, re.DOTALL)
    yaml_text = match.group(1).strip() if match else raw

    conduit_report = yaml.safe_load(yaml_text)
    conduit_report["day"] = day
    conduit_report["agent"] = "CONDUIT"
    conduit_report.setdefault("advisories", [])
    conduit_report.setdefault("blockers", [])
    conduit_report.setdefault("hold_reason", "")

    jsonschema.validate(conduit_report, CONDUIT_REPORT_SCHEMA)
    return conduit_report
