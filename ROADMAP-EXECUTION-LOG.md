# PACE Framework — ROADMAP Execution Log

**Author:** Vivek Meehnia
**Started:** 2026-03-13 (IST — Asia/Kolkata)
**Log Version:** 1.0
**Aligned With:** ROADMAP v1.1

---

## Overview

This log records every code change, architectural decision, and trade-off made while executing the PACE Framework v2.0 ROADMAP. Each entry is tied to a roadmap item, a branch, and a PR.

---

## Phase 1 — Foundation (v2.0-alpha)

### Item 9 — Configuration Tester

**Branch:** `phase1/item-9-config-tester`
**PR:** #1
**Status:** Open (pending review)

#### Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `pace/config_tester.py` | New | Full config validation CLI |
| `.github/workflows/pace.yml` | Modified | Added `Validate PACE configuration` step before budget check |

#### Implementation Details

`config_tester.py` uses a `ConfigTestResult` dataclass with three severity levels:

- **error** (exit code 2) — validation failures that will cause runtime crashes (e.g., missing product name, empty source dirs, unknown provider)
- **warning** (exit code 1) — likely misconfiguration that won't crash but will degrade behavior (e.g., `forge_input_tokens < 32000`, sprint_days > release_days)
- **suggestion** (exit code 0) — optional improvements (e.g., haiku for analysis_model saves cost)

`--json` flag emits machine-readable output for CI integrations that parse the result. `--config PATH` allows overriding the config file location.

The step in `pace.yml` runs before the budget check — a config error stops the run before any API spend is incurred.

#### Key Validators

| Validator | What it checks |
|-----------|---------------|
| `_validate_product` | name/description not placeholder, github_org set |
| `_validate_sprint` | `duration_days` in 1–365 |
| `_validate_release` | `sprint_days` ≤ `release_days`, both > 0 |
| `_validate_source` | dirs not empty, each entry has name/path |
| `_validate_llm` | model in known Anthropic IDs, warns on opus `analysis_model` (cost) |
| `_validate_llm_limits` | `forge_input_tokens` ≥ 32000 (32k flagged as dangerously low for multi-iteration FORGE loops) |
| `_validate_forge` | `max_iterations` in 1–200 |
| `_validate_cron` | 5-field cron regex, warns on sub-minute intervals |
| `_validate_reporter` | IANA timezone check via `zoneinfo` |

#### Architectural Decisions

**AD-9-1: Three-level severity instead of pass/fail**
Rationale: A hard pass/fail check would block legitimate runs where config is valid but suboptimal. Warnings surface cost/performance concerns at validation time without blocking. Errors catch crashes before any API spend occurs.

**AD-9-2: `--json` flag for CI integration**
Rationale: Teams using PACE in CI pipelines (Jenkins, GitLab) may want to parse validation results programmatically. JSON output enables this without screen-scraping.

**AD-9-3: Run before budget check in pace.yml**
Rationale: A config error discovered after an API call wastes money. Config validation is a purely local operation that costs nothing — it runs first.

---

### Item 1 — Sprint/Release Branching Model

**Branch:** `phase1/item-1-branching-model`
**PR:** #2
**Status:** Open (pending review)

#### Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `pace/config.py` | Modified | `ReleaseConfig` dataclass; `release` field on `PaceConfig`; `load_config()` parsing |
| `pace/branching.py` | New | `BranchingAdapter` ABC, helpers, `LocalBranchingAdapter`, factory |
| `pace/platforms/github.py` | Modified | `GitHubBranchingAdapter` class |
| `pace/orchestrator.py` | Modified | `ensure_hierarchy()` call before `run_cycle()` |
| `pace/pace.config.yaml` | Modified | Commented-out `release:` section with inline docs |

#### Branch Hierarchy

```
main
  └── staging          (created when release is first configured)
        └── release/<name>   (e.g. release/v2.0)
              └── rel/sprint/pace-N  (e.g. rel/sprint/pace-1)
```

Every level is created idempotently — `ensure_hierarchy()` calls `get_branch_sha()` before attempting `create_branch()`. A branch that already exists is skipped silently.

#### ReleaseConfig Schema

```yaml
release:
  name: "v2.0"          # Used in branch name release/v2.0
  release_days: 90      # Total calendar days in the release
  sprint_days: 7        # Days per sprint (e.g. 7 = weekly sprints)
```

Sprint number is derived from: `sprint_num = ceil(day / sprint_days)`.

#### PR Creation at Sprint End

`GitHubBranchingAdapter.create_pull_request()` is called by `ensure_hierarchy()` at the end of each sprint (day % sprint_days == 0) to open:

- `rel/sprint/pace-N → release/<name>` (sprint close PR)

At release end (day == release_days):
- `release/<name> → staging` (release close PR)
- `staging → main` (final promotion PR, opened by CONDUIT after staging CI passes)

#### Architectural Decisions

**AD-1-1: Idempotent hierarchy creation**
Rationale: The orchestrator calls `ensure_hierarchy()` every day. Any level may already exist from a previous run. A 422 "ref already exists" from the GitHub API is treated as a no-op, not an error.

**AD-1-2: `LocalBranchingAdapter` as a no-op**
Rationale: Projects using `platform.ci: local` have no remote Git hosting. The adapter must exist to satisfy the interface but has nothing meaningful to do. A no-op is the correct behavior rather than a crash.

**AD-1-3: Optional `release:` block — fully backward compatible**
Rationale: Existing PACE v1.x projects have no `release:` key. When the key is absent, `cfg.release` is `None` and the branching call in `orchestrator.py` is skipped entirely. Zero behavior change for existing users.

**AD-1-4: Separate `BranchingAdapter` from `CIAdapter`**
Rationale: CI operations (PR reviews, CI polling, variable setting) and branching operations (creating refs) have different lifecycles and failure modes. Keeping them separate follows the single-responsibility principle and makes each adapter easier to test.

---

### Item 2 — PACE Planner Pipeline

**Branch:** `phase1/item-2-pace-planner`
**PR:** #3
**Status:** Open (pending review)

#### Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `pace/planner.py` | Modified | `--pipeline` mode, `_collect_shipped_days()`, `_write_shipped_manifest()`, `run_pipeline()`, `__main__` CLI |
| `.github/workflows/pace-planner.yml` | New | Standalone planner workflow |

#### Pipeline Flow

```
workflow_dispatch (or schedule)
  ↓
Validate config (config_tester.py)
  ↓
python pace/planner.py --pipeline
  ├── _collect_shipped_days()   → reads .pace/*/gate.md
  ├── _write_shipped_manifest() → writes .pace/shipped.yaml
  ├── run_planner(replan=True)  → re-estimates remaining days
  └── ci.set_variable("PACE_PAUSED", "true")
  ↓
git commit .pace/day-0/planner.md + .pace/shipped.yaml
git push --force-with-lease origin pace/plan-approval
  ↓
gh pr create (idempotent — skips if PR already open)
  ↓
[Human reviews and merges PR]
  ↓
Team sets PACE_PAUSED=false → daily cycle resumes
```

#### Shipped-Days Protection

When `--pipeline` runs, it scans `.pace/day-*/gate.md` for `gate_decision: SHIP`. Shipped days are:
1. Recorded in `.pace/shipped.yaml`
2. Preserved with their actual costs in `planner.md`
3. Never re-estimated (actuals override predictions)

This ensures a mid-sprint re-plan cannot revise or overwrite work already completed.

#### Architectural Decisions

**AD-2-1: Pipeline mode vs Day 0 mode are separate code paths**
Rationale: Day 0 mode (`PACE_DAY=0`) is called by the orchestrator synchronously as part of the main PACE cycle. Pipeline mode is an async, standalone workflow with different responsibilities (PR gate, PACE_PAUSED). Merging them would create a complex conditional that obscures both flows.

**AD-2-2: Git operations in the workflow YAML, not in Python**
Rationale: Python running git subprocesses in CI is fragile (credential setup, branch management). GitHub Actions workflows have native git context, token auth, and `gh` CLI. Each layer does what it's best at: Python generates the artifacts, the workflow manages git/PR operations.

**AD-2-3: Force-push to `pace/plan-approval`**
Rationale: The plan-approval branch is ephemeral and PACE-owned. It is never used for human development work. Force-pushing ensures the PR always reflects the latest estimates without accumulating stale commits.

**AD-2-4: `--replan` flag for forced re-estimation**
Rationale: A team may want to force all-day re-estimation even before any days ship (e.g., after a scope change). `--replan` makes this an explicit, auditable action rather than relying on the presence of shipped days.

---

## Cross-Cutting Decisions

### CC-1: Phase 1 branches target `main`

All Phase 1 feature branches (`phase1/item-*`) are branched from and PR'd back to `main`. This is intentional for the starter template where `main` is the canonical branch. In a live project using Item 1's branching model, these would target `staging` or `release/<name>`.

### CC-2: No breaking changes in Phase 1

Every Phase 1 change is backward-compatible with v1.x configurations:
- `config_tester.py` is a new optional tool — not required to run
- `release:` in `pace.config.yaml` is optional — absent = no branching
- `planner.py --pipeline` is a new mode — existing Day 0 behavior unchanged
- `pace-planner.yml` is a new workflow that must be triggered manually

### CC-3: 422 "already exists" handling throughout

The GitHub REST API returns 422 when a branch ref or PR already exists. All three items with GitHub API calls (`GitHubBranchingAdapter.create_branch`, `create_pull_request`, and the workflow's `gh pr create`) treat 422 as a successful no-op. This makes every operation idempotent under retries and race conditions.

---

## Pending Phase 1 Work

| Item | Status | Next Action |
|------|--------|-------------|
| Item 9 (Config Tester) | PR #1 open | Review and merge |
| Item 1 (Branching Model) | PR #2 open | Review and merge |
| Item 2 (PACE Planner) | PR #3 open | Review and merge |

---

## Phase 2 — Intelligence & Efficiency (v2.0-beta)

### Item 3 — Context Versioning & Token Management

**Branch:** `phase2/item-3-context-versioning`
**PR:** #4
**Status:** Open (pending review)

#### Item 3: Files Changed

| File | Change Type | Description |
| ------ | ----------- | ----------- |
| `pace/config.py` | Modified | `LLMLimitsConfig` dataclass; `limits` field on `LLMConfig`; parse `llm.limits` |
| `pace/pace.config.yaml` | Modified | Document `llm.limits` section with safe defaults and 32k WARNING |
| `pace/spend_tracker.py` | Modified | `session_total()` and `call_exceeds_limit()` helpers |
| `pace/orchestrator.py` | Modified | `build_shipped_summary()` + write to `.pace/context/shipped_summary.md` |
| `pace/planner.py` | Modified | `context_version` semver patch bump on every planner write |

#### Item 3: Implementation Details

**LLMLimitsConfig** splits token limits by agent class rather than globally because FORGE needs up to 160k input tokens (system prompt + tool definitions + file contents + multi-iteration history) while analysis agents (PRIME, GATE, SENTINEL, CONDUIT) only receive summarized story context. A single global limit would force a choice between under-serving FORGE or over-serving analysis agents.

**Context compaction** in `build_shipped_summary()`: for each past day, read `gate.md`; if `gate_decision == SHIP`, extract target + coverage/test metadata from `handoff.md` and emit a single compact bullet. The result is written to `.pace/context/shipped_summary.md` before preflight runs. Any agent that reads from the context directory will see the compact summary instead of full story files.

**Context version** in `planner.py`: each planner run bumps `context_version` semver patch (e.g., `1.0.0` → `1.0.1`). The version is stored in `planner.md`. Agents can compare the version they see at execution time against the version at story generation time; a mismatch indicates the plan drifted.

#### Item 3: Architectural Decisions

**AD-3-1: Per-agent-class limits, not global**
Rationale: FORGE on a codebase with 10+ files and 20 iterations of history easily exceeds 100k input tokens. A global 80k limit would truncate FORGE while being more than enough for analysis agents. Splitting by class gives each agent the window it actually needs.

**AD-3-2: Shipped summary as markdown file, not in-memory**
Rationale: Writing to `.pace/context/shipped_summary.md` makes the summary visible, auditable, and available to agents that read from the context directory without any code change to those agents. It also persists across runs.

**AD-3-3: Semver patch bump (not calendar date) for context_version**
Rationale: A calendar date gives no ordering information between multiple re-plans on the same day. Semver patch increments are deterministic and comparable.

---

### Item 4 — Auto-Update Mechanism

**Branch:** `phase2/item-4-auto-update`
**PR:** #5
**Status:** Open (pending review)

#### Item 4: Files Changed

| File | Change Type | Description |
| ------ | ----------- | ----------- |
| `pace/updater.py` | New | `check_for_update()`, `detect_customizations()`, `apply_update()`, `check_and_warn()` |
| `pace/config.py` | Modified | `UpdatesConfig` dataclass; `updates` field on `PaceConfig`; parse `updates:` |
| `pace/preflight.py` | Modified | `_run_update_check()` calling `check_and_warn()` at pipeline start |
| `pace/pace.config.yaml` | Modified | Document `updates:` section |

#### Update Decision Tree

```
check_for_update()
    ↓ update_available?
    NO  → silent (no-op)
    YES → detect_customizations()
              ↓ empty list?
              YES + auto_update=true  → apply_update() → continue pipeline
              NO  + suppress_warning=false → emit WARNING with file list + tutorial URL
              NO  + suppress_warning=true  → silent skip
```

#### Cache Strategy

`check_for_update()` writes results to `.pace/update_check.json` with a `cached_at` timestamp. Any subsequent call within 23 hours reads from cache without hitting the GitHub API. This prevents version-check API calls from adding latency to every pipeline run.

#### Item 4: Architectural Decisions

**AD-4-1: `detect_customizations()` uses git diff, not file hashing**
Rationale: `git diff <tag>` is authoritative — it uses the same mechanism git uses for everything else and correctly handles file renames, deletions, and binary files. File hashing would require maintaining a manifest of expected checksums.

**AD-4-2: Non-fatal update check**
Rationale: A failed version check (network error, API rate limit, malformed response) must never block a pipeline run. The check is wrapped in try/except and failures are logged at WARNING level then ignored.

**AD-4-3: `apply_update()` checks for pipeline.lock**
Rationale: If `apply_update()` ran while another pipeline was active, the second pipeline would see partially-updated PACE files mid-run. The lock check prevents this race condition.

---

### Item 8 — Cron Configuration

**Branch:** `phase2/item-8-cron-config`
**PR:** #6
**Status:** Open (pending review)

#### Item 8: Files Changed

| File | Change Type | Description |
| ------ | ----------- | ----------- |
| `pace/ci_generator.py` | New | Cron regeneration CLI; `_update_gha_cron()`, `generate()` |
| `pace/config.py` | Modified | `CronConfig` dataclass; `cron` field on `PaceConfig`; parse `cron:` |
| `pace/pace.config.yaml` | Modified | Document `cron:` section with default schedules |
| `pace/preflight.py` | Modified | `acquire_pipeline_lock()` / `release_pipeline_lock()` |
| `pace/orchestrator.py` | Modified | `atexit.register(release_pipeline_lock)` |

#### Pipeline Lock

The pipeline lock (`.pace/pipeline.lock`) is a simple text file containing PID and timestamp. Acquisition:

- If no lock → write lock, continue
- If lock exists and age < 4h → raise `RuntimeError` (abort run)
- If lock exists and age ≥ 4h → stale lock: remove and replace, continue

Release is registered with `atexit` in `orchestrator.py` so it fires regardless of whether the run exits via SHIP, HOLD, ABORT, or unhandled exception. `preflight.py` acquires but does not release — separation of concerns: acquire at start, release at very end.

#### CI Generator Regex Strategy

`_update_gha_cron()` uses a targeted regex to find and replace only the `schedule.cron` value in GitHub Actions YAML. It does not parse or rewrite the entire YAML file, which would destroy comments and formatting. The regex captures only the cron string inside the `"` delimiters.

#### Item 8: Architectural Decisions

**AD-8-1: `atexit` for lock release, not `try/finally` in `main()`**
Rationale: `main()` calls `sys.exit()` from multiple paths (SHIP, HOLD, ABORT, preflight failure). A `try/finally` wrapping the entire `main()` body would be deeply nested. `atexit` handlers fire on all `sys.exit()` calls and normal returns, making it the cleaner hook.

**AD-8-2: Regex-based cron patching, not YAML re-serialization**
Rationale: Python YAML serializers (PyYAML, ruamel.yaml) do not preserve comments. The workflow YAML files have extensive inline comments that would be destroyed by a parse-and-reserialize approach. A targeted regex replaces only the cron string, leaving everything else unchanged.

**AD-8-3: Stale lock threshold of 4 hours**
Rationale: The `pace.yml` workflow has a `timeout-minutes: 90` limit. A lock older than 4 hours is definitely from a crashed run. 4h gives comfortable headroom above 90 minutes while being short enough to recover within a business day if the previous run crashed.

---

## Cross-Cutting Decisions (Phase 2)

### CC-4: Phase 2 branches also target `main`

Same rationale as Phase 1 (CC-1). All phase2 feature branches PR to `main`.

### CC-5: `__post_init__` pattern for optional config fields with defaults

Items 3, 4, and 8 all add new optional fields (`llm.limits`, `updates`, `cron`) to `PaceConfig` with rich dataclass defaults. Using `field(default_factory=...)` requires the field to be non-positional, which breaks the existing constructor call order. The `__post_init__` pattern (`= None` + post-init assignment) allows the field to stay at the end without changing existing call sites.

### CC-6: All new config sections are backward-compatible with existing configs

Any `pace.config.yaml` without `llm.limits`, `updates:`, or `cron:` sections parses cleanly with all defaults applied. No existing project needs to update their config to use v2.0.

---

## Pending Work

| Item | Status | Next Action |
| ---- | ------ | ----------- |
| Item 9 (Config Tester) | PR #1 open | Review and merge |
| Item 1 (Branching Model) | PR #2 open | Review and merge |
| Item 2 (PACE Planner) | PR #3 open | Review and merge |
| Item 3 (Context Versioning) | PR #4 open | Review and merge |
| Item 4 (Auto-Update) | PR #5 open | Review and merge |
| Item 8 (Cron Config) | PR #6 open | Review and merge |
| Items 5, 6, 7 (Phase 3) | Not started | See ROADMAP Phase 3 |
| Item 10 (Phase 4) | Not started | See ROADMAP Phase 4 |

---

*ROADMAP Execution Log v1.1 — 2026-03-13 IST (Phase 2 added)*
*Author: Vivek Meehnia*
