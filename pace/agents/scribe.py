"""SCRIBE agent — generates context documents that all PACE agents use throughout the sprint.

Runs once before Day 1 (or whenever a context doc is missing).
Reads both the repository AND the optional external documentation folder,
then writes 4 structured markdown documents to .pace/context/:

  product.md      — product vision, personas, pain points, scope, success metrics
  engineering.md  — module map, tech stack, coding conventions, test patterns
  security.md     — sensitive data inventory, threat model, security requirements
  devops.md       — CI/CD topology, required env vars, deployment process, runbooks

File path prefixes in tool calls:
  repo:path/to/file  — resolves relative to the repository root
  docs:path/to/file  — resolves relative to the configured docs_dir (if set)
  (no prefix)        — same as repo:
"""

from pathlib import Path
from config import load_config
from llm import get_llm_adapter

REPO_ROOT = Path(__file__).parent.parent.parent
CONTEXT_DIR = REPO_ROOT / ".pace" / "context"

ALLOWED_DOCS = {"product.md", "engineering.md", "security.md", "devops.md"}
SKIP_DIRS = {".git", ".venv", "vendor", "__pycache__", ".pace", "node_modules", ".mypy_cache"}

# ---------------------------------------------------------------------------
# Generic document-to-segment mapping
# SCRIBE uses this as a guide for WHAT belongs in each context document.
# Specific file paths are discovered by exploring the repo and docs folder.
# ---------------------------------------------------------------------------
DOC_MAPPING = """
=== CONTEXT DOCUMENT GUIDE ===

Each context document must contain specific, actionable information grounded in source files.
Read ALL relevant source files before writing each document. Do not invent facts.

--- product.md (for PRIME — story card generation) ---
Content to include:
  - Product vision and the problem it solves
  - Target personas: who are the users and what are their pain points
  - MVP scope: what is in scope and explicitly out of scope
  - Success metrics: how Day 30 success is defined
  - Strategic constraints: architectural decisions that are locked

Where to look:
  - repo:pace/plan.yaml                     (sprint plan — authoritative for Day targets)
  - docs: look for files named mvp, vision, persona, roadmap, strategy, product in docs_dir
  - repo: look for README.md, docs/, ARCHITECTURE.md, or similar top-level docs

Required sections in product.md:
  ## Vision
  ## Target Personas
  ## Core Pain Points
  ## MVP Scope (In Scope / Out of Scope)
  ## Success Metrics
  ## Strategic Constraints

--- engineering.md (for FORGE and GATE — implementation and validation) ---
Content to include:
  - Module map: directory → language → purpose
  - Tech stack: languages, frameworks, databases, infrastructure
  - System architecture: how components interact
  - Key interfaces and contracts: APIs, CLI flags, config schemas, file formats
  - Coding conventions: error handling, naming patterns, test patterns
  - Test patterns: how tests are structured and run

Where to look:
  - repo: source directories listed in pace.config.yaml
  - repo: go.mod, package.json, pyproject.toml, Cargo.toml, or equivalent dependency files
  - repo: README.md, docs/architecture.md or similar
  - docs: look for files named architecture, tech_stack, api, contracts, srs, adr in docs_dir

Required sections in engineering.md:
  ## Module Map
  ## Tech Stack
  ## System Architecture
  ## Key Interfaces & Contracts
  ## Coding Conventions
  ## Test Patterns

--- security.md (for SENTINEL — security and SRE review) ---
Content to include:
  - Sensitive data inventory: what data must be protected
  - Trust boundaries: which components can call which
  - Threat model: key threats per component
  - Security requirements: hard constraints FORGE must always satisfy
  - Compliance controls (if applicable)
  - Security checklist: binary checks SENTINEL runs on every implementation

Where to look:
  - docs: look for files named security, threat, stride, compliance, audit in docs_dir
  - repo: look for security-related docs, threat models, or compliance notes
  - repo: .github/workflows/ for existing security scanning steps

Required sections in security.md:
  ## Sensitive Data Inventory
  ## Trust Boundaries
  ## Threat Model
  ## Security Requirements
  ## Security Checklist for SENTINEL

--- devops.md (for CONDUIT — CI/CD and infrastructure review) ---
Content to include:
  - CI/CD pipeline topology: workflows, triggers, jobs
  - Required environment variables and secrets
  - Local development setup: exact commands to build, test, and run
  - Deployment process and variants
  - Runbook: how to diagnose common failures

Where to look:
  - repo: .github/workflows/ (all workflow files)
  - repo: Makefile, Dockerfile, docker-compose.yml, or equivalent
  - repo: README.md setup/development sections
  - docs: look for files named ci, deployment, devops, ops, runbook, onboarding in docs_dir

Required sections in devops.md:
  ## CI/CD Pipeline Topology
  ## Required Environment Variables & Secrets
  ## Local Development Setup
  ## Deployment Process
  ## Runbook
"""


def _build_system_prompt(cfg) -> str:
    docs_info = ""
    if cfg.docs_dir and cfg.docs_dir.exists():
        docs_info = f"""
You have access to TWO file roots:
  repo:path   — files inside the repository root ({REPO_ROOT.name}/)
  docs:path   — files inside the documentation folder ({cfg.docs_dir})
  (no prefix) — same as repo:

Start by listing both roots to understand what is available:
  1. list_dir "." (repo root)
  2. list_dir "docs:" (documentation folder)"""
    else:
        docs_info = f"""
You have access to ONE file root (no external docs folder is configured):
  repo:path   — files inside the repository root ({REPO_ROOT.name}/)
  (no prefix) — same as repo:

Start by listing the repo root: list_dir "." """

    return f"""You are the Context Agent (SCRIBE) for {cfg.product_name}.

{cfg.product_description}

Your job is to produce 4 structured context documents that other PACE agents will read on every day
of the sprint. These documents must be:
  - Grounded in the actual source files (not invented)
  - Specific and actionable — each section gives agents concrete facts they can use
  - Concise — no padding. Every sentence carries information.
{docs_info}

{DOC_MAPPING}

=== PROCEDURE ===
1. Explore the repository structure and documentation folder (if available) using list_dir.
2. For each context document, identify and read relevant source files before writing.
3. Synthesize: combine multiple sources into coherent sections. Do not copy-paste verbatim.
4. Write all 4 documents using write_doc before stopping.
5. If a source file does not exist, note "source not yet available" in that section.
6. Do not invent facts. Every claim must come from a source file you read.
7. Write all 4 documents. Do not stop until all 4 are written."""


TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Read a file. Use prefix 'docs:' for the documentation folder "
            "or 'repo:' / no prefix for the source repo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path with optional prefix. Examples: 'docs:docs/product/mvp.md', 'repo:README.md', 'go.mod'",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": (
            "List immediate contents of a directory (one level deep). "
            "Use 'docs:' prefix for the documentation folder, 'repo:' or no prefix for the repo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path with optional prefix. Examples: 'docs:', 'docs:docs/technical', '.', 'src'",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_doc",
        "description": (
            "Write a context document to .pace/context/. "
            "Allowed names: product.md, engineering.md, security.md, devops.md"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "One of: product.md, engineering.md, security.md, devops.md",
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown content of the document.",
                },
            },
            "required": ["name", "content"],
        },
    },
]


def _resolve_path(path: str, docs_root) -> tuple[Path, str]:
    """Return (base_root, clean_path) for a path with optional docs:/repo: prefix."""
    if path.startswith("docs:"):
        base = docs_root if docs_root else REPO_ROOT
        return base, path[len("docs:"):]
    if path.startswith("repo:"):
        return REPO_ROOT, path[len("repo:"):]
    return REPO_ROOT, path


def _tool_read_file(path: str, docs_root) -> str:
    base, clean = _resolve_path(path, docs_root)
    target = base / clean if clean else base
    if not target.exists():
        return f"ERROR: File not found: {path}"
    if target.is_dir():
        return f"ERROR: {path} is a directory. Use list_dir instead."
    try:
        content = target.read_text(encoding="utf-8")
        return content[:10000] if len(content) > 10000 else content
    except Exception as exc:
        return f"ERROR: Could not read {path}: {exc}"


def _tool_list_dir(path: str, docs_root) -> str:
    base, clean = _resolve_path(path, docs_root)
    target = base / clean if clean else base
    if not target.exists():
        return f"ERROR: Directory not found: {path}"
    if not target.is_dir():
        return f"ERROR: {path} is a file. Use read_file instead."
    lines = []
    for item in sorted(target.iterdir()):
        if item.name in SKIP_DIRS:
            continue
        kind = "dir" if item.is_dir() else "file"
        lines.append(f"{kind}  {item.name}")
    return "\n".join(lines) if lines else "(empty)"


def _tool_write_doc(name: str, content: str) -> str:
    if name not in ALLOWED_DOCS:
        return f"ERROR: Unknown doc '{name}'. Allowed: {', '.join(sorted(ALLOWED_DOCS))}"
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    (CONTEXT_DIR / name).write_text(content, encoding="utf-8")
    return f"OK: wrote {name} ({len(content)} chars)"


def _dispatch(name: str, inputs: dict, docs_root) -> str:
    if name == "read_file":
        return _tool_read_file(inputs["path"], docs_root)
    if name == "list_dir":
        return _tool_list_dir(inputs["path"], docs_root)
    if name == "write_doc":
        return _tool_write_doc(inputs["name"], inputs["content"])
    return f"ERROR: Unknown tool: {name}"


def _sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of *path*, or empty string if unreadable."""
    import hashlib
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def _write_context_manifest(release_name: str, docs_written: set[str]) -> None:
    """Write .pace/context/context.manifest.yaml after SCRIBE generates docs.

    Records the active release, generation timestamp, SHA-256 hashes of known
    source docs, and the list of context files written. Non-fatal on failure.
    """
    import datetime
    import yaml as _yaml

    # Hash well-known source docs if present
    source_candidates = ["PRD.md", "SRS.md", "README.md", "ARCHITECTURE.md"]
    source_hashes: dict[str, str] = {}
    for candidate in source_candidates:
        p = REPO_ROOT / candidate
        if p.exists():
            source_hashes[candidate] = _sha256(p)

    manifest = {
        "release": release_name,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_hashes": source_hashes,
        "files": sorted(docs_written),
    }

    manifest_path = CONTEXT_DIR / "context.manifest.yaml"
    try:
        CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(_yaml.dump(manifest, default_flow_style=False, allow_unicode=True))
        print(f"[SCRIBE] context.manifest.yaml written (release: {release_name}).")
    except Exception as exc:
        print(f"[SCRIBE] Could not write context manifest (non-fatal): {exc}")


def _write_scribe_report(docs_written: set[str], files_read: list[str], iterations: int) -> None:
    """Write .pace/scribe_report.yaml after SCRIBE completes.

    Records context documents generated, source files read, and tool-loop
    iteration count (budget proxy). Non-fatal on write failure.
    """
    import yaml as _yaml
    report = {
        "documents_written": sorted(docs_written),
        "source_files_read": files_read,
        "tool_iterations": iterations,
        "missing_docs": sorted(ALLOWED_DOCS - docs_written),
    }
    report_path = REPO_ROOT / ".pace" / "scribe_report.yaml"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_yaml.dump(report, default_flow_style=False, allow_unicode=True))
        print(f"[SCRIBE] Planning report written ({len(files_read)} source files read, "
              f"{iterations} iterations, {len(docs_written)}/4 docs written).")
    except Exception as exc:
        print(f"[SCRIBE] Could not write planning report (non-fatal): {exc}")


def run_scribe() -> None:
    """Run SCRIBE to generate all 4 context documents. Idempotent — safe to re-run."""
    cfg = load_config()
    docs_root = cfg.docs_dir  # May be None if not configured

    adapter = get_llm_adapter()
    system_prompt = _build_system_prompt(cfg)

    messages = [
        {
            "role": "user",
            "content": (
                "Generate all 4 context documents (product.md, engineering.md, security.md, devops.md). "
                "Start by exploring the repository structure to understand what source files are available, "
                "then read relevant files and write each context document."
            ),
        }
    ]

    docs_written: set[str] = set()
    files_read: list[str] = []
    max_iterations = 30
    iteration_count = 0

    for _ in range(max_iterations):
        iteration_count += 1
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
            result = _dispatch(call.name, call.input, docs_root)
            if call.name == "read_file":
                files_read.append(call.input.get("path", ""))
            if call.name == "write_doc" and result.startswith("OK"):
                docs_written.add(call.input.get("name", ""))
                print(f"[SCRIBE] Written: {call.input.get('name')}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result,
            })

        if not tool_results:
            break

        if docs_written >= ALLOWED_DOCS:
            print("[SCRIBE] All 4 context documents written.")
            break

        messages.append({"role": "user", "content": tool_results})

    _write_scribe_report(docs_written, files_read, iteration_count)

    # Item 12: write context.manifest.yaml with release + source hashes
    release_name = (cfg.active_release.name if cfg.active_release else "")
    _write_context_manifest(release_name, docs_written)

    missing = ALLOWED_DOCS - docs_written
    if missing:
        raise RuntimeError(f"SCRIBE completed but did not write: {missing}")
