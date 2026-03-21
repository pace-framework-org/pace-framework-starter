"""FORGE agent — implements Story Cards via an agentic tool-use loop."""

import json
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
PACE_DIR = REPO_ROOT / ".pace"

# ---------------------------------------------------------------------------
# System prompt building blocks — included/excluded based on forge config
# ---------------------------------------------------------------------------

_TDD_PHASES = """
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
- Do not modify files outside the source directories listed above."""

_BASIC_WORKFLOW = """
Your job is to implement the Story Card exactly as specified. No more, no less.

Workflow:
  1. Read existing source files to understand structure and conventions.
  2. Implement the acceptance criteria.
  3. Run the test suite to verify your changes.
  4. Run git_commit with a message that names the story.
  5. Run git rev-parse HEAD to get the SHA.
  6. Call complete_handoff as your final action.

Rules:
- Do not add features, abstractions, or error handling for scenarios outside the story.
- Keep commits focused: one logical change per commit.
- Do not modify files outside the source directories listed above."""

_COVERAGE_RULE = """
COVERAGE RULE — mandatory for every story:
- Every production code file you create or modify must have corresponding tests.
- Do not add a function, type, or module without a test case that exercises it.
- Do not reduce the number of existing test cases — only add or extend them.
- After implementing, run the full test suite and confirm it exits 0. If the
  story card includes a CI-verified acceptance criterion, your implementation is
  incomplete until that criterion passes locally.
- When in doubt, write the test first (TDD Red phase), then implement to make it pass.
  This is not optional — untested production code will cause CI to fail and GATE to HOLD."""

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
    if target.is_dir():
        files = sorted(str(p.relative_to(REPO_ROOT)) for p in target.iterdir() if p.is_file())
        return f"ERROR: '{path}' is a directory. Files inside: {files}"
    return target.read_text(encoding="utf-8")


def _tool_write_file(path: str, content: str) -> str:
    target = REPO_ROOT / path
    if target.is_dir():
        return (
            f"ERROR: '{path}' is a directory, not a file. "
            f"Specify the full file path (e.g. '{path}/action.yml')."
        )
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
        f'git add -A && git commit -m {shlex.quote(message)} && (git stash -u || true) && git pull --rebase && (git stash pop || true) && git push origin HEAD',
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return f"ERROR: git commit/push failed: {result.stderr}"
    return f"OK: committed and pushed — {result.stdout.strip()}"


_BASE_TOOLS = [
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

_CONFIRM_RED_PHASE_TOOL = {
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
}


_COMMIT_PLAN_TOOL = {
    "name": "commit_plan",
    "description": (
        "Call this after the exploration phase (reading files, understanding structure) and "
        "BEFORE writing any files. Provide a brief implementation plan. "
        "Your context will be forked: a fresh implementation context starts after this call, "
        "carrying only the plan summary and story card."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "Brief implementation plan: what files to create/modify and why.",
            },
            "files_to_modify": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to create or modify.",
            },
        },
        "required": ["plan"],
    },
}


def _build_tools(tdd_enforcement: bool, fork_enabled: bool = False) -> list:
    """Return the tool list based on enforcement flags."""
    tools = list(_BASE_TOOLS)
    if tdd_enforcement:
        # Insert confirm_red_phase just before complete_handoff (last entry)
        tools = tools[:-1] + [_CONFIRM_RED_PHASE_TOOL, tools[-1]]
    if fork_enabled:
        # Insert commit_plan before complete_handoff (and before confirm_red_phase if present)
        tools = [t for t in tools if t["name"] != "complete_handoff"]
        tools = [t for t in tools if t["name"] != "confirm_red_phase"]
        base = list(_BASE_TOOLS)[:-1]  # all except complete_handoff
        extras = [_COMMIT_PLAN_TOOL]
        if tdd_enforcement:
            extras = [_CONFIRM_RED_PHASE_TOOL] + extras
        tools = base + extras + [_BASE_TOOLS[-1]]
    return tools


def _dispatch_tool(name: str, inputs: dict) -> str:
    if name == "read_file":
        path = inputs.get("path")
        if not path:
            return "ERROR: read_file requires a 'path' argument."
        return _tool_read_file(path)
    if name == "write_file":
        path = inputs.get("path")
        content = inputs.get("content")
        if not path:
            return "ERROR: write_file requires a 'path' argument."
        if content is None:
            return "ERROR: write_file requires a 'content' argument."
        return _tool_write_file(path, content)
    if name == "run_bash":
        command = inputs.get("command")
        if not command:
            return "ERROR: run_bash requires a 'command' argument."
        return _tool_run_bash(command)
    if name == "git_commit":
        message = inputs.get("message")
        if not message:
            return "ERROR: git_commit requires a 'message' argument."
        return _tool_git_commit(message)
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


# ---------------------------------------------------------------------------
# Conversation checkpointing
# ---------------------------------------------------------------------------

def _checkpoint_path(day: int) -> Path:
    return PACE_DIR / f"day-{day}" / "forge_checkpoint.json"


def _save_checkpoint(day: int, messages: list, red_phase_confirmed: bool, iteration: int) -> None:
    path = _checkpoint_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(
            json.dumps({
                "messages": messages,
                "red_phase_confirmed": red_phase_confirmed,
                "iteration": iteration,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[FORGE] Warning: checkpoint save failed: {e}")


def _load_checkpoint(day: int) -> dict | None:
    path = _checkpoint_path(day)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[FORGE] Warning: checkpoint load failed: {e}")
        return None


def _trace_path(day: int) -> Path:
    return PACE_DIR / f"day-{day}" / "forge_trace.json"


def _clear_checkpoint(day: int) -> None:
    try:
        _checkpoint_path(day).unlink(missing_ok=True)
    except Exception:
        pass


def _save_trace(day: int, messages: list, system_prompt: str, red_phase_confirmed: bool, iterations_used: int) -> None:
    """Persist the FORGE conversation trace as a permanent training artifact.

    Written immediately before the checkpoint is cleared on a successful
    complete_handoff so that the DataExportHook (and any external tooling)
    can read the full Anthropic-format message history after the sprint day
    is marked SHIP.  The checkpoint itself is still cleared so that the next
    retry starts from scratch.

    Schema written to forge_trace.json:
        {
            "system": "<FORGE system prompt>",
            "messages": [<Anthropic-format turns>],
            "red_phase_confirmed": true | false,
            "iterations_used": N,
        }
    """
    path = _trace_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(
            json.dumps(
                {
                    "system": system_prompt,
                    "messages": messages,
                    "red_phase_confirmed": red_phase_confirmed,
                    "iterations_used": iterations_used,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[FORGE] Warning: trace save failed: {e}")


# ---------------------------------------------------------------------------
# Sprint 7.2 — Stage 1: FORGE context growth mitigations
# ---------------------------------------------------------------------------

def _rebuild_written_paths(messages: list) -> set:
    """Reconstruct written_paths from message history (used when resuming a checkpoint)."""
    written: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "write_file"):
                path = block.get("input", {}).get("path", "")
                if path:
                    written.add(path)
    return written


def _evict_stale_reads(messages: list, written_paths: set) -> None:
    """Item 21: Replace content of read_file tool results for paths that were subsequently written.

    Mutates messages in-place. Called before each adapter.chat() to trim context.
    """
    if not written_paths:
        return
    # Map tool_use_id → path for every read_file tool call in history
    read_ids: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "read_file"):
                path = block.get("input", {}).get("path", "")
                if path:
                    read_ids[block["id"]] = path
    # Replace stale tool_results
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                continue
            path = read_ids.get(block.get("tool_use_id", ""), "")
            if path and path in written_paths:
                block["content"] = (
                    f"[evicted: {path} was written this session — re-read if needed]"
                )


def _dedup_bash_results(messages: list) -> None:
    """Item 22: Keep only the latest run_bash result per command signature.

    Mutates messages in-place. Called before each adapter.chat() to trim context.
    """
    # Map tool_use_id → command for every run_bash call
    bash_cmds: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "run_bash"):
                cmd = block.get("input", {}).get("command", "")
                if cmd:
                    bash_cmds[block["id"]] = cmd
    if not bash_cmds:
        return
    # Collect result blocks in message order: (msg_idx, block_idx, tool_use_id, cmd)
    occurrences: list[tuple[int, int, str, str]] = []
    for msg_idx, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block_idx, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tid = block.get("tool_use_id", "")
                if tid in bash_cmds:
                    occurrences.append((msg_idx, block_idx, tid, bash_cmds[tid]))
    # Group by command; replace all but the last occurrence with compact placeholder
    from collections import defaultdict
    by_cmd: dict[str, list] = defaultdict(list)
    for entry in occurrences:
        by_cmd[entry[3]].append(entry)
    for cmd, entries in by_cmd.items():
        if len(entries) <= 1:
            continue
        for msg_idx, block_idx, _tid, _cmd in entries[:-1]:
            messages[msg_idx]["content"][block_idx]["content"] = (
                f"[dedup: earlier run of `{cmd[:80]}` — see latest result]"
            )


def _compress_history(
    messages: list,
    compression_model: str,
    written_paths: set,
    story_card: dict,
) -> list:
    """Item 24: Compress message history to a YAML summary via a Haiku model call.

    Fires once after the RED phase is confirmed. Replaces the full message history
    with a compact structured summary so the GREEN phase starts with a clean context.

    On any failure (API error, parse error, missing fields) the original messages
    are returned unchanged (fallback).
    """
    # Collect ground-truth read paths and last bash output for anti-hallucination override
    read_paths: list[str] = []
    last_bash_output: str = ""
    # Build tool_use_id → name map to resolve results back to their calls
    id_to_name: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                id_to_name[block["id"]] = block.get("name", "")
                if block.get("name") == "read_file":
                    path = block.get("input", {}).get("path", "")
                    if path and path not in read_paths:
                        read_paths.append(path)
    for msg in messages:
        if msg.get("role") != "user":
            continue
        for block in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
            if (isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and id_to_name.get(block.get("tool_use_id", "")) == "run_bash"):
                last_bash_output = str(block.get("content", ""))

    # Format history compactly for the Haiku prompt (cap at 200 lines to stay cheap)
    history_lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", [])
        if isinstance(content, str):
            history_lines.append(f"{role.upper()}: {content[:300]}")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    inp = json.dumps(block.get("input", {}))[:200]
                    history_lines.append(f"FORGE CALLED {block['name']}({inp})")
                elif block.get("type") == "tool_result":
                    snippet = str(block.get("content", ""))[:300]
                    history_lines.append(f"RESULT: {snippet}")
                elif block.get("type") == "text":
                    history_lines.append(f"{role.upper()}: {block.get('text', '')[:200]}")
    history_text = "\n".join(history_lines[-200:])

    try:
        compression_adapter = get_llm_adapter(model=compression_model)
        system = (
            "You are compressing an AI agent session into a structured YAML summary. "
            "Be precise and factual. Only report what appears in the history. "
            "Do NOT invent or guess file contents, outcomes, or decisions."
        )
        prompt = (
            f"Compress this FORGE agent session. Story: {story_card.get('title', 'unknown')}\n\n"
            f"History:\n{history_text}\n\n"
            "Respond ONLY with this YAML (no other text):\n"
            "```yaml\n"
            "files_read: []\n"
            "files_written: []\n"
            "plan_committed: false\n"
            "key_decisions: []\n"
            "last_test_output: \"\"\n"
            "red_phase_confirmed: true\n"
            "```"
        )
        resp = compression_adapter.complete(system, prompt, max_tokens=1024)
        yaml_text = resp
        if "```yaml" in yaml_text:
            yaml_text = yaml_text.split("```yaml")[1].split("```")[0].strip()
        summary = yaml.safe_load(yaml_text) or {}

        # Verification: required fields must be present
        required = {"files_read", "files_written", "key_decisions", "red_phase_confirmed"}
        missing = required - summary.keys()
        if missing:
            raise ValueError(f"Compressed summary missing fields: {missing}")

        # Anti-hallucination: override with ground-truth data
        summary["files_written"] = sorted(written_paths)
        summary["last_test_output"] = last_bash_output[:500]

        initial_message = messages[0]
        compressed_context = (
            "## Session Context (compressed)\n\n"
            f"```yaml\n{yaml.dump(summary, default_flow_style=False, allow_unicode=True)}```\n\n"
            "The RED phase is confirmed (failing tests witnessed). "
            "Proceed to PHASE 2 — GREEN: write minimum implementation to make the tests pass."
        )
        print(f"[FORGE] Context compressed: {len(messages)} messages → 2 messages")
        return [
            initial_message,
            {"role": "user", "content": [{"type": "text", "text": compressed_context}]},
        ]
    except Exception as exc:
        print(f"[FORGE] Warning: context compression failed: {exc} — keeping original history")
        return messages


def _fork_context(
    messages: list,
    plan: str,
    files_to_modify: list,
    story_card: dict,
    compression_model: str | None,
    written_paths: set,
) -> list:
    """Item 26 Phase A: Fork exploration context into a clean implementation context.

    Compresses the exploration phase (reads, understanding) into a YAML summary and
    returns a 2-message history: [original story card, implementation briefing].
    Falls back to original messages on any error.
    """
    # Reuse _compress_history infrastructure for the exploration phase summary
    if compression_model:
        compressed = _compress_history(messages, compression_model, written_paths, story_card)
    else:
        compressed = messages  # no compression model — use original as base

    plan_section = f"## Implementation Plan\n\n{plan}\n"
    if files_to_modify:
        plan_section += "\nFiles to modify:\n" + "\n".join(f"- `{f}`" for f in files_to_modify)

    implementation_brief = (
        f"{plan_section}\n\n"
        "You have committed your exploration plan. Now proceed to PHASE 2 — GREEN: "
        "implement the code as planned. Write the minimum code to make the tests pass."
    )

    # Append the plan as the new continuation message
    forked = list(compressed)
    forked.append({"role": "user", "content": [{"type": "text", "text": implementation_brief}]})
    print(f"[FORGE] Context forked: {len(messages)} exploration messages → {len(forked)} implementation context messages")
    return forked


def _build_file_hints(story_card: dict, cfg) -> str:
    """Item 25: Haiku pre-pass over engineering.md to identify likely relevant files.

    Returns a '## File Hints' markdown section for the initial FORGE message,
    or empty string if hints should be skipped (disabled, stale docs, API error).
    Hints are suggestions only — FORGE uses its own judgement.
    """
    if not cfg.forge.file_hints_enabled:
        return ""
    if story_card.get("disable_file_hints"):
        return ""

    engineering_path = REPO_ROOT / ".pace" / "context" / "engineering.md"
    if not engineering_path.exists():
        return ""

    # Freshness check: engineering.md must be tracked in context.manifest.yaml
    manifest_path = REPO_ROOT / ".pace" / "context" / "context.manifest.yaml"
    if not manifest_path.exists():
        return ""
    try:
        manifest = yaml.safe_load(manifest_path.read_text()) or {}
        if "engineering.md" not in manifest.get("files", []):
            return ""
    except Exception:
        return ""

    try:
        hint_model = cfg.forge.compression_model or cfg.llm.analysis_model
        adapter = get_llm_adapter(model=hint_model)
        story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)
        engineering_content = engineering_path.read_text(encoding="utf-8")[:3000]
        system = (
            "You are identifying which files in a codebase are most relevant to a software story. "
            "Return ONLY YAML, no other text."
        )
        prompt = (
            f"Story:\n{story_yaml}\n\n"
            f"Engineering context:\n{engineering_content}\n\n"
            "List files likely needed for this story with confidence scores (0.0-1.0).\n"
            "Respond ONLY with:\n"
            "```yaml\n"
            "file_hints:\n"
            "  - path: src/example.py\n"
            "    confidence: 0.9\n"
            "    reason: \"contains relevant logic\"\n"
            "```"
        )
        resp = adapter.complete(system, prompt, max_tokens=512)
        yaml_text = resp
        if "```yaml" in yaml_text:
            yaml_text = yaml_text.split("```yaml")[1].split("```")[0].strip()
        hints_data = yaml.safe_load(yaml_text) or {}
        hints = hints_data.get("file_hints", [])

        threshold = cfg.forge.file_hints_confidence_threshold
        filtered = [
            h for h in hints
            if isinstance(h, dict) and float(h.get("confidence", 0)) >= threshold
        ]
        if not filtered:
            return ""

        lines = [
            "## File Hints",
            "",
            "These files are likely relevant (not constraints — use your own judgement):",
        ]
        for h in filtered:
            reason = h.get("reason", "")
            conf = h.get("confidence", "")
            suffix = f" — {reason}" if reason else ""
            lines.append(f"- `{h['path']}` (confidence: {conf}){suffix}")
        lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        print(f"[FORGE] Warning: file hints failed: {exc} — proceeding without hints")
        return ""


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

    tdd_on = cfg.forge.tdd_enforcement
    workflow_section = _TDD_PHASES if tdd_on else _BASIC_WORKFLOW
    coverage_section = _COVERAGE_RULE if cfg.forge.coverage_rule else ""
    tools_list = "read_file, write_file, run_bash, git_commit" + (", confirm_red_phase" if tdd_on else "") + ", complete_handoff"

    system_prompt = f"""You are the Engineering Agent (FORGE) for {cfg.product_name}.

{cfg.product_description}

Source directories — write code ONLY into these paths:
{dirs_section}

Do NOT write into pace/, .pace/, or the repo root.

Tech stack: {cfg.tech.primary_language}{f', {cfg.tech.secondary_language}' if cfg.tech.secondary_language else ''}. CI: {cfg.tech.ci_system}.
{build_cmd_note}
{test_cmd_note}
{workflow_section}
{coverage_section}
You have access to tools: {tools_list}."""

    story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)
    engineering_ctx = _load_context("engineering.md")
    engineering_section = f"\nEngineering Context:\n{engineering_ctx}\n" if engineering_ctx else ""

    user_content = f"Story Card for Day {day}:\n\n{story_yaml}{engineering_section}"

    # Item 25: prepend file hints from engineering.md (skipped on retry — checkpoint already has them)
    if not hold_reason:
        file_hints_section = _build_file_hints(story_card, cfg)
        if file_hints_section:
            user_content = user_content + "\n\n" + file_hints_section

    handoff_data: dict | None = None
    # red_phase_confirmed starts True when TDD is off or on a retry (code already committed).
    red_phase_confirmed: bool = (not tdd_on) or bool(hold_reason)
    fork_on = cfg.forge.fork_enabled
    tools = _build_tools(tdd_on, fork_enabled=fork_on)
    max_iterations = cfg.forge.max_iterations
    # Item 24: resolve compression model; None disables compression
    compression_model: str | None = cfg.forge.compression_model or cfg.llm.analysis_model or None
    _compressed: bool = bool(hold_reason)  # skip on retry — history already compacted
    _forked: bool = bool(hold_reason)     # Item 26: skip fork on retry
    start_iteration = 0

    # On retry: try to resume from the previous run's checkpoint. A checkpoint
    # exists only when the previous run exhausted max_iterations without calling
    # complete_handoff. If FORGE called complete_handoff (GATE/SENTINEL HOLD),
    # the checkpoint was cleared and we start fresh with just the hold_reason.
    if hold_reason:
        checkpoint = _load_checkpoint(day)
        if checkpoint:
            messages = checkpoint["messages"]
            red_phase_confirmed = checkpoint.get("red_phase_confirmed", red_phase_confirmed)
            start_iteration = checkpoint.get("iteration", 0)
            print(f"[FORGE] Resuming from checkpoint: iteration {start_iteration}, {len(messages)} messages in history")
            # Append the hold reason as a fresh user message so FORGE knows what to fix.
            messages.append({"role": "user", "content": [
                {"type": "text", "text": f"Previous attempt feedback — focus your fix on this:\n{hold_reason}"}
            ]})
        else:
            user_content += f"\n\nPrevious attempt feedback — focus your fix on this:\n{hold_reason}"
            messages = [{"role": "user", "content": user_content}]
    else:
        # Fresh start — clear any stale checkpoint from a previous sprint day.
        _clear_checkpoint(day)
        messages = [{"role": "user", "content": user_content}]

    # Stage 1 (Item 21): track paths written this session; rebuild from checkpoint on retry
    _written_paths: set[str] = _rebuild_written_paths(messages)

    for iteration in range(start_iteration, max_iterations):
        # Stage 1 (Items 21+22): evict stale reads and dedup bash output before each API call
        _evict_stale_reads(messages, _written_paths)
        _dedup_bash_results(messages)

        response = adapter.chat(
            system=system_prompt,
            messages=messages,
            tools=tools,
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
                    # Item 24: compress history on first RED confirmation (single-trigger guard)
                    if not _compressed and compression_model:
                        messages.append({"role": "user", "content": tool_results})
                        messages = _compress_history(
                            messages, compression_model, _written_paths, story_card
                        )
                        tool_results = []
                        _compressed = True
                continue

            # Item 26 Phase A: fork exploration context when commit_plan is called
            if call.name == "commit_plan" and fork_on and not _forked:
                plan_text = call.input.get("plan", "")
                files_to_modify = call.input.get("files_to_modify", [])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": "Plan committed. Context forking — implementation phase starting.",
                })
                messages.append({"role": "user", "content": tool_results})
                messages = _fork_context(
                    messages, plan_text, files_to_modify, story_card, compression_model, _written_paths
                )
                tool_results = []
                _forked = True
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
                handoff_data["iterations_used"] = iteration + 1
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": "Handoff recorded. Implementation complete.",
                })
                break

            result = _dispatch_tool(call.name, call.input)
            # Item 21+23: track written paths; replace write receipt with compact summary
            if call.name == "write_file":
                path = call.input.get("path", "")
                if path and not result.startswith("ERROR:"):
                    _written_paths.add(path)
                    result = (
                        f"OK: wrote {len(str(call.input.get('content', '')))} bytes"
                        f" to {path} (iter {iteration + 1})"
                    )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result,
            })

        if handoff_data:
            # Successful handoff — persist trace for training data pipeline,
            # then remove checkpoint so next retry starts fresh.
            _save_trace(
                day,
                messages,
                system_prompt,
                red_phase_confirmed,
                handoff_data.get("iterations_used", iteration + 1),
            )
            _clear_checkpoint(day)
            break

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        # Persist conversation state after each iteration. If this run exhausts
        # max_iterations, the next retry can resume from here rather than restart.
        _save_checkpoint(day, messages, red_phase_confirmed, iteration + 1)

    if not handoff_data:
        raise RuntimeError(f"FORGE did not call complete_handoff after {max_iterations} iterations")

    # Coerce string list fields — FORGE sometimes writes a markdown bullet string
    # instead of a YAML array for known_gaps / edge_cases_tested.
    for field in ("known_gaps", "edge_cases_tested"):
        val = handoff_data.get(field)
        if isinstance(val, str):
            handoff_data[field] = [
                line.lstrip("- ").strip()
                for line in val.splitlines()
                if line.strip() and line.strip() != "-"
            ]

    jsonschema.validate(handoff_data, HANDOFF_SCHEMA)
    return handoff_data
