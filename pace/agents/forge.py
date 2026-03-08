"""FORGE agent — implements Story Cards via an agentic tool-use loop."""

import os
import shlex
import subprocess
import yaml
import jsonschema
from pathlib import Path
from schemas import HANDOFF_SCHEMA
from config import load_config
from llm import get_llm_adapter

REPO_ROOT = Path(__file__).parent.parent.parent

# Allowed bash commands — block anything dangerous
ALLOWED_PREFIXES = (
    "go ", "python ", "python3 ", "pytest", "npm ", "yarn ", "cargo ",
    "make ", "cat ", "ls ", "echo ", "mkdir ", "cp ", "mv ",
    "find ", "grep ", "git add", "git diff", "git log", "git status", "git rev-parse",
)
BLOCKED_PATTERNS = (
    r"rm\s+-rf", r"curl\b", r"wget\b", r"ssh\b", r"sudo\b",
    r">\s*/etc", r"chmod\s+777",
)


def _is_command_allowed(command: str) -> tuple[bool, str]:
    import re as _re
    for pattern in BLOCKED_PATTERNS:
        if _re.search(pattern, command):
            return False, f"Command blocked by security policy: matches '{pattern}'"
    return True, ""


def _tool_read_file(path: str) -> str:
    target = REPO_ROOT / path
    if not target.exists():
        return f"ERROR: File not found: {path}"
    return target.read_text(encoding="utf-8")


def _tool_write_file(path: str, content: str) -> str:
    target = REPO_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} bytes to {path}"


def _tool_run_bash(command: str) -> str:
    allowed, reason = _is_command_allowed(command)
    if not allowed:
        return f"ERROR: {reason}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=120,
        )
        output = result.stdout + result.stderr
        return output[:4000] if len(output) > 4000 else output
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 120 seconds"


def _tool_git_commit(message: str) -> str:
    result = subprocess.run(
        f'git add -A && git commit -m {shlex.quote(message)} && git push origin HEAD',
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return f"ERROR: git commit/push failed: {result.stderr}"
    return f"OK: committed and pushed — {result.stdout.strip()}"


TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Relative path from repo root"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the repository. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_bash",
        "description": "Run a shell command in the repository root. Build, test, and lint commands only.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command to execute"}},
            "required": ["command"],
        },
    },
    {
        "name": "git_commit",
        "description": "Stage all changes, create a git commit, and push to origin. Use git rev-parse HEAD afterward to get the commit SHA for complete_handoff.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Commit message"}},
            "required": ["message"],
        },
    },
    {
        "name": "confirm_red_phase",
        "description": (
            "REQUIRED TDD checkpoint. Call this after running the test suite and confirming "
            "that at least one new test fails. Provide the failing test output as evidence. "
            "You must call this before writing any implementation code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "failing_tests": {
                    "type": "string",
                    "description": "The test runner output showing at least one failing test.",
                },
                "tests_written": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of test file paths written in Phase 1.",
                },
            },
            "required": ["failing_tests", "tests_written"],
        },
    },
    {
        "name": "complete_handoff",
        "description": "Signal implementation complete. Call this as your final action.",
        "input_schema": {
            "type": "object",
            "required": ["commit", "approach", "risk", "dependencies", "built", "edge_cases_tested", "known_gaps"],
            "properties": {
                "commit": {"type": "string", "description": "The git commit SHA of the implementation"},
                "approach": {"type": "string"},
                "risk": {"type": "string"},
                "dependencies": {"type": "string"},
                "built": {"type": "string"},
                "edge_cases_tested": {"type": "array", "items": {"type": "string"}},
                "known_gaps": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
]


def _dispatch_tool(name: str, inputs: dict) -> str:
    if name == "read_file":
        return _tool_read_file(inputs["path"])
    if name == "write_file":
        return _tool_write_file(inputs["path"], inputs["content"])
    if name == "run_bash":
        return _tool_run_bash(inputs["command"])
    if name == "git_commit":
        return _tool_git_commit(inputs["message"])
    return f"ERROR: Unknown tool: {name}"


def _tool_confirm_red_phase(failing_tests: str, tests_written: list[str]) -> str:
    if not failing_tests or not failing_tests.strip():
        return "ERROR: confirm_red_phase requires non-empty failing_tests output. Run the test suite first and provide the output."
    if not tests_written:
        return "ERROR: confirm_red_phase requires at least one test file path in tests_written."
    summary = ", ".join(tests_written)
    return (
        f"Red phase confirmed. Tests written: {summary}. "
        "You may now proceed to Phase 2: write the minimum implementation to make these tests pass."
    )


def _load_context(doc: str) -> str:
    path = REPO_ROOT / ".pace" / "context" / doc
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_forge(day: int, story_card: dict, hold_reason: str | None = None) -> dict:
    cfg = load_config()
    adapter = get_llm_adapter()

    # Build source dirs section for the system prompt
    dirs_lines = []
    for d in cfg.source_dirs:
        dirs_lines.append(f"  {d.path:<30} ({d.language}) — {d.description}")
    dirs_section = "\n".join(dirs_lines) if dirs_lines else "  (see pace.config.yaml for source dirs)"

    build_cmd_note = f"Build: {cfg.tech.build_command}" if cfg.tech.build_command else ""
    test_cmd_note = f"Test: {cfg.tech.test_command}"

    system_prompt = f"""You are the Engineering Agent (FORGE) for {cfg.product_name}.

{cfg.product_description}

Source directories — write code ONLY into these paths:
{dirs_section}

Do NOT write into pace/, .pace/, or the repo root.

Tech stack: {cfg.tech.primary_language}{f', {cfg.tech.secondary_language}' if cfg.tech.secondary_language else ''}. CI: {cfg.tech.ci_system}.
{build_cmd_note}
{test_cmd_note}

Your job is to implement the Story Card exactly as specified. No more, no less.
Follow strict Test-Driven Development. You MUST complete every phase in order:

PHASE 1 — RED (write failing tests)
  a. Read existing source files to understand structure and conventions.
  b. Write ONLY test files that assert the acceptance criteria. No implementation yet.
  c. Run the test suite with run_bash. Confirm at least one new test fails.
  d. Call confirm_red_phase with the failing test output as evidence.
     You CANNOT proceed to Phase 2 without calling confirm_red_phase.

PHASE 2 — GREEN (write minimum implementation)
  a. Write the minimum production code to make the failing tests pass.
  b. Run the test suite. If tests still fail, fix only what is needed — do not rewrite tests.
  c. All acceptance criteria tests must pass before continuing.

PHASE 3 — REFACTOR (clean up)
  a. Remove duplication or dead code introduced during Green. Tests must remain green.
  b. Run the test suite one final time to confirm.

PHASE 4 — COMMIT & HANDOFF
  a. Run git_commit with a message that names the story.
  b. Run git rev-parse HEAD to get the SHA.
  c. Call complete_handoff as your final action.

Rules:
- Do not add features, abstractions, or error handling for scenarios outside the story.
- Never modify a test to make it pass — fix the implementation instead.
- Keep commits focused: one logical change per commit.
- Do not modify files outside the source directories listed above.

You have access to tools: read_file, write_file, run_bash, git_commit, confirm_red_phase, complete_handoff."""

    story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)
    engineering_ctx = _load_context("engineering.md")
    engineering_section = f"\nEngineering Context:\n{engineering_ctx}\n" if engineering_ctx else ""

    user_content = f"Story Card for Day {day}:\n\n{story_yaml}{engineering_section}"

    if hold_reason:
        user_content += f"\n\nPrevious attempt feedback — focus your fix on this:\n{hold_reason}"

    messages = [{"role": "user", "content": user_content}]

    handoff_data: dict | None = None
    red_phase_confirmed: bool = False
    max_iterations = 40

    for iteration in range(max_iterations):
        response = adapter.chat(
            system=system_prompt,
            messages=messages,
            tools=TOOLS,
            max_tokens=8096,
        )

        messages.append(response.to_assistant_message())

        if response.stop_reason == "end_turn":
            break

        tool_results = []
        for call in response.tool_calls:
            if call.name == "confirm_red_phase":
                result = _tool_confirm_red_phase(
                    call.input.get("failing_tests", ""),
                    call.input.get("tests_written", []),
                )
                if result.startswith("ERROR:"):
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": result,
                    })
                else:
                    red_phase_confirmed = True
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": result,
                    })
                continue

            if call.name == "complete_handoff":
                if not red_phase_confirmed:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": (
                            "ERROR: TDD violation — confirm_red_phase was never called. "
                            "You must write tests first, run them to confirm failure, "
                            "and call confirm_red_phase before completing the handoff. "
                            "Go back to Phase 1."
                        ),
                    })
                    continue

                handoff_data = dict(call.input)
                handoff_data["day"] = day
                handoff_data["agent"] = "FORGE"
                handoff_data["tdd_red_phase_confirmed"] = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": "Handoff recorded. Implementation complete.",
                })
                break

            result = _dispatch_tool(call.name, call.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result,
            })

        if handoff_data:
            break

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    if not handoff_data:
        raise RuntimeError(f"FORGE did not call complete_handoff after {max_iterations} iterations")

    jsonschema.validate(handoff_data, HANDOFF_SCHEMA)
    return handoff_data
