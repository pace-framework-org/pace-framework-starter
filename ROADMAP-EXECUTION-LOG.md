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

*Not yet started. See ROADMAP.md for planned items.*

---

*ROADMAP Execution Log v1.0 — 2026-03-13 IST*
*Author: Vivek Meehnia*
