# PACE Framework — ROADMAP Execution Log

**Author:** Vipul Meehnia
**Started:** 2026-03-13 (IST — Asia/Kolkata)
**Log Version:** 2.7
**Aligned With:** ROADMAP v1.5

---

## Log Version History

| Version | Date | Changes |
| ------- | ---- | ------- |
| 1.0 | 2026-03-13 | Phase 1 entries: Items 9, 1, 2 |
| 1.1 | 2026-03-13 | Phase 2 entries added: Items 3, 4, 8; Post-PR fixes for Item 4 |
| 1.2 | 2026-03-14 | Variations from Plan sections added to all implemented items; CC-7 branch-rebase entry; log aligned with ROADMAP v1.2 |
| 1.3 | 2026-03-14 | All Phase 1 and Phase 2 PRs confirmed merged to main; Item 9 (PR #1) and Item 8 (PR #6) merged; Phase 3 next |
| 1.4 | 2026-03-14 | Phase 3 implemented: Item 5 (Communications & Alerting) merged; Items 6 (Tracker Artifacts) and 7 (Platform Finalization) PRs open |
| 1.5 | 2026-03-15 | Phase 3 complete: Item 7 (PR #10) merged; Phase 4 (Item 10 Plugin System) started |
| 1.6 | 2026-03-15 | Phase 4 complete: Item 10 (PR #11) merged; all 4 ROADMAP phases delivered |
| 1.7 | 2026-03-15 | Phase 5 implemented: Item 11 (Training Data Pipeline) PR open; ROADMAP extended to v1.3 |
| 1.8 | 2026-03-16 | Item 11 (PR #12) confirmed merged; ROADMAP extended to v1.4 with Phase 6 (Items 12–18, Planned); Item 7 status corrected in ROADMAP; unit test suite added (223 tests, 82.76% coverage) |
| 1.9 | 2026-03-16 | Add missing Phase 4 body section (Item 10 Plugin System); document post-Phase4 stability fixes; remove stale Pending Phase 1 Work section; correct Item 9 PR reference (direct commit, not PR #1) |
| 2.0 | 2026-03-16 | Phase 6 formal execution plan: dependency order, sprint breakdown, branch naming, GitHub issues created (Items 12–18 + deferred steps); ROADMAP aligned to v1.5 |
| 2.1 | 2026-03-17 | Sprint 6.1 complete: Item 12 (Context Versioning) PR #16 merged; `context_manifest.yaml`, `CONTEXT_MANIFEST_SCHEMA`, `_write_context_manifest`, `_validate_context_manifest` delivered |
| 2.2 | 2026-03-17 | Sprint 6.2 start: Item 14 (Config Tester Foundation) PR #22 merged; `ConfigTestResult`, `_validate_releases`, `_validate_cross_fields`, `run_config_test`, full CLI delivered |
| 2.3 | 2026-03-17 | Sprint 6.3 start: Item 13 (Context Auto-Refresh) implementation complete; `_archive_context`, `_check_context_freshness`, `force_refresh_context` in preflight.py; 18 tests added |
| 2.4 | 2026-03-17 | Item 13 PR #27 opened, merged, issue #17 closed |
| 2.5 | 2026-03-17 | Item 15 (plan.yaml Versioning & Story Naming) delivered: `PLAN_SCHEMA`, `_iter_stories`, `_get_replan_boundary`, `_backup_plan`, `v3_plan_naming.py` migration, orchestrator `get_day_plan` update, `_validate_plan` in config_tester; 29 tests; PR #28 merged, issue #18 closed |
| 2.6 | 2026-03-17 | Item 16 (Pre-run Config Validation Extended) delivered: `_validate_plan_files`, `--strict`/`--release` CLI flags, CI file updates (GitHub Actions, GitLab CI, Jenkinsfile, Bitbucket Pipelines); 14 tests; PR #29 opened, issue #19 closed |
| 2.7 | 2026-03-17 | Execution log updated to v2.7; Pending Work table cleared; Sprint 6.3 fully complete |

---

## Overview

This log records every code change, architectural decision, trade-off, and deviation from the plan made while executing the PACE Framework v2.0 ROADMAP. Each entry is tied to a roadmap item, a branch, and a PR. Deviations from the original ROADMAP plan are captured under *Variations from Plan* within each item.

---

## Phase 1 — Foundation (v2.0-alpha)

### Item 9 — Configuration Tester

**Branch:** `phase1/item-9-config-tester`
**PR:** #1
**Status:** Merged

#### Item 9: Changes

| File | Change Type | Description |
| ------ | ----------- | ----------- |
| `pace/config_tester.py` | New | Full config validation CLI |
| `.github/workflows/pace.yml` | Modified | Added `Validate PACE configuration` step before budget check |

#### Implementation Details

`config_tester.py` uses a `ConfigTestResult` dataclass with three severity levels:

- **error** (exit code 2) — validation failures that will cause runtime crashes (e.g., missing product name, empty source dirs, unknown provider)
- **warning** (exit code 1) — likely misconfiguration that won't crash but will degrade behavior (e.g., `forge_input_tokens < 32000`, sprint_days > release_days)
- **suggestion** (exit code 0) — optional improvements (e.g., haiku for analysis_model saves cost)

`--json` flag emits machine-readable output for CI integrations that parse the result. `--config PATH` allows overriding the config file location.

The step in `pace.yml` runs before the budget check — a config error stops the run before any API spend is incurred.

#### Item 9: Key Validators

| Validator | What it checks |
| --------- | -------------- |
| `_validate_product` | name/description not placeholder, github_org set |
| `_validate_sprint` | `duration_days` in 1–365 |
| `_validate_release` | `sprint_days` ≤ `release_days`, both > 0 |
| `_validate_source` | dirs not empty, each entry has name/path |
| `_validate_llm` | model in known Anthropic IDs, warns on opus `analysis_model` (cost) |
| `_validate_llm_limits` | `forge_input_tokens` ≥ 32000 (32k flagged as dangerously low for multi-iteration FORGE loops) |
| `_validate_forge` | `max_iterations` in 1–200 |
| `_validate_cron` | 5-field cron regex, warns on sub-minute intervals |
| `_validate_reporter` | IANA timezone check via `zoneinfo` |

#### Item 9: Architectural Decisions

**AD-9-1: Three-level severity instead of pass/fail**
Rationale: A hard pass/fail check would block legitimate runs where config is valid but suboptimal. Warnings surface cost/performance concerns at validation time without blocking. Errors catch crashes before any API spend occurs.

**AD-9-2: `--json` flag for CI integration**
Rationale: Teams using PACE in CI pipelines (Jenkins, GitLab) may want to parse validation results programmatically. JSON output enables this without screen-scraping.

**AD-9-3: Run before budget check in pace.yml**
Rationale: A config error discovered after an API call wastes money. Config validation is a purely local operation that costs nothing — it runs first.

#### Item 9: Variations from Plan

No scope deviations. All six planned steps were implemented as specified.

The `_validate_cron` validator references the `cron` config section introduced by Item 8. Although Item 8 is a Phase 2 item, the validator was included in Item 9's implementation to future-proof the validation step — it is a no-op when `cron:` is absent from the config.

---

### Item 1 — Sprint/Release Branching Model

**Branch:** `phase1/item-1-branching-model`
**PR:** #2
**Status:** Merged

#### Item 1: Changes

| File | Change Type | Description |
| ------ | ----------- | ----------- |
| `pace/config.py` | Modified | `ReleaseConfig` dataclass; `release` field on `PaceConfig`; `load_config()` parsing |
| `pace/branching.py` | New | `BranchingAdapter` ABC, helpers, `LocalBranchingAdapter`, factory |
| `pace/platforms/github.py` | Modified | `GitHubBranchingAdapter` class |
| `pace/orchestrator.py` | Modified | `ensure_hierarchy()` call before `run_cycle()` |
| `pace/pace.config.yaml` | Modified | Commented-out `release:` section with inline docs |

#### Item 1: Branch Hierarchy

```text
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

#### Item 1: Architectural Decisions

**AD-1-1: Idempotent hierarchy creation**
Rationale: The orchestrator calls `ensure_hierarchy()` every day. Any level may already exist from a previous run. A 422 "ref already exists" from the GitHub API is treated as a no-op, not an error.

**AD-1-2: `LocalBranchingAdapter` as a no-op**
Rationale: Projects using `platform.ci: local` have no remote Git hosting. The adapter must exist to satisfy the interface but has nothing meaningful to do. A no-op is the correct behavior rather than a crash.

**AD-1-3: Optional `release:` block — fully backward compatible**
Rationale: Existing PACE v1.x projects have no `release:` key. When the key is absent, `cfg.release` is `None` and the branching call in `orchestrator.py` is skipped entirely. Zero behavior change for existing users.

**AD-1-4: Separate `BranchingAdapter` from `CIAdapter`**
Rationale: CI operations (PR reviews, CI polling, variable setting) and branching operations (creating refs) have different lifecycles and failure modes. Keeping them separate follows the single-responsibility principle and makes each adapter easier to test.

#### Item 1: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Step 3 | BranchingAdapter for GitHub, GitLab, Bitbucket | GitHub fully implemented; GitLab/Bitbucket fall back to `LocalBranchingAdapter` via factory | Partial — GitLab/Bitbucket deferred to Item 7 |
| Step 5 | CONDUIT: PR from `release/<name>` → `staging` after all sprints merged; monitor CI; open `staging` → `main` on pass; HOLD on fail | Not implemented | Deferred to Phase 3 |
| Step 6 | Branch-protection checks in `preflight.py` | Not implemented | Deferred to Phase 3 |

**Impact:** The branch hierarchy creation (steps 1–2, 4) is complete. The automated promotion chain (`release → staging → main`) requires Phase 3 CONDUIT work. Users can merge the sprint PR to `release/<name>` manually until Phase 3 delivers the automated gate.

---

### Item 2 — PACE Planner Pipeline

**Branch:** `phase1/item-2-pace-planner`
**PR:** #3
**Status:** Merged

#### Item 2: Changes

| File | Change Type | Description |
| ------ | ----------- | ----------- |
| `pace/planner.py` | Modified | `--pipeline` mode, `_collect_shipped_days()`, `_write_shipped_manifest()`, `run_pipeline()`, `__main__` CLI |
| `.github/workflows/pace-planner.yml` | New | Standalone planner workflow |

#### Pipeline Flow

```text
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

#### Item 2: Architectural Decisions

**AD-2-1: Pipeline mode vs Day 0 mode are separate code paths**
Rationale: Day 0 mode (`PACE_DAY=0`) is called by the orchestrator synchronously as part of the main PACE cycle. Pipeline mode is an async, standalone workflow with different responsibilities (PR gate, PACE_PAUSED). Merging them would create a complex conditional that obscures both flows.

**AD-2-2: Git operations in the workflow YAML, not in Python**
Rationale: Python running git subprocesses in CI is fragile (credential setup, branch management). GitHub Actions workflows have native git context, token auth, and `gh` CLI. Each layer does what it's best at: Python generates the artifacts, the workflow manages git/PR operations.

**AD-2-3: Force-push to `pace/plan-approval`**
Rationale: The plan-approval branch is ephemeral and PACE-owned. It is never used for human development work. Force-pushing ensures the PR always reflects the latest estimates without accumulating stale commits.

**AD-2-4: `--replan` flag for forced re-estimation**
Rationale: A team may want to force all-day re-estimation even before any days ship (e.g., after a scope change). `--replan` makes this an explicit, auditable action rather than relying on the presence of shipped days.

#### Item 2: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Step 3 | PRIME agent `plan_mode` flag returning a structured re-plan diff | Not implemented — `planner.py` handles re-estimation directly without invoking PRIME | Deferred to Phase 3 |
| Step 4 | CONDUIT creates plan-approval PR and sets `PACE_PAUSED=true` | `planner.py --pipeline` calls `ci.set_variable("PACE_PAUSED", "true")` directly; CONDUIT not modified | Variation — simpler implementation, same functional outcome |
| Step 5 | SCRIBE generates human-readable planning report with budget impact and scope delta | Not implemented — only `planner.py` generates the `planner.md` YAML report | Deferred to Phase 3 |

**Impact:** The core shipped-days protection, cost re-estimation, and plan-approval PR gate all work as planned. The PRIME re-plan diff and SCRIBE narrative report are value-adds deferred to Phase 3. The PACE_PAUSED mechanism works correctly via the platform CI adapter.

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

## Phase 2 — Intelligence & Efficiency (v2.0-beta)

### Item 3 — Context Versioning & Token Management

**Branch:** `phase2/item-3-context-versioning`
**PR:** #4
**Status:** Merged

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

#### Item 3: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Step 3 | Explicitly pass `shipped_summary.md` to PRIME, GATE, SENTINEL instead of full story files | `shipped_summary.md` written to `.pace/context/`; individual agent call sites not modified to substitute it | Partial — agents that read from the context directory pick it up; explicit wiring deferred |
| Step 6 (new) | Per-call retry with compacted prompt when `call_exceeds_limit()` returns true | Only helpers added (`session_total`, `call_exceeds_limit`); the retry loop was not implemented | Deferred to Phase 3 |

**Branch rebase:** This branch rebased cleanly onto `main` after Phase 1 items (Items 1 and 2) landed — no conflicts.

**Impact:** Context versioning and shipped-summary compaction are functional. The token enforcement retry loop (compacting and re-submitting when a call exceeds limits) requires Phase 3 work in the agent loop.

---

### Item 4 — Auto-Update Mechanism

**Branch:** `phase2/item-4-auto-update`
**PR:** #5
**Status:** Merged

#### Item 4: Files Changed

| File | Change Type | Description |
| ------ | ----------- | ----------- |
| `pace/updater.py` | New | `check_for_update()`, `detect_customizations()`, `apply_update()`, `check_and_warn()` |
| `pace/config.py` | Modified | `UpdatesConfig` dataclass; `updates` field on `PaceConfig`; parse `updates:` |
| `pace/preflight.py` | Modified | `_run_update_check()` calling `check_and_warn()` at pipeline start |
| `pace/pace.config.yaml` | Modified | Document `updates:` section |

#### Update Decision Tree

```text
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

#### Item 4: Post-PR Fixes

Two code quality issues identified after initial PR was raised (commit `6224c6e`):

**Fix 1 — Unreachable `else` branch in `check_and_warn()`**

The original code had:

```python
if not suppress_warning or auto_update:
    customizations = detect_customizations()
else:
    customizations = []
```

The `else` branch was unreachable. The early return `if not auto_update and suppress_warning: return` at the top of the function already handles the only case where `not (not suppress_warning or auto_update)` is true — i.e. `suppress_warning=True and auto_update=False`. Simplified to `customizations = detect_customizations()` with no conditional. Behavior is identical.

**Fix 2 — Empty `except` in `_read_cache()`**

The original `except Exception: pass` silently discarded all cache read/parse errors with no diagnostic output. Replaced with `except Exception as e:` plus a brief `print()` log message so corrupted or unreadable cache files surface as debug output rather than vanishing silently. The function still returns `None` (cache miss) on error — the non-fatal contract is preserved.

#### Item 4: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Step 7 | CONDUIT: include update summary in daily report when update applied; deferred-update warning when blocked by customizations | CONDUIT not modified | Deferred to Phase 3 |
| Step 8 | Reference tutorial at `tutorials/updating-customised-pace` in pace-docs | Tutorial URL is a placeholder (`https://pace-docs.example.com/tutorials/updating-customised-pace`); the tutorial page does not yet exist | Deferred to docs team |

**Post-PR code quality fixes (commit `6224c6e`):**

| Issue | Original | Fixed |
| ----- | -------- | ----- |
| Unreachable `else` in `check_and_warn()` | `if not suppress_warning or auto_update: ... else: customizations = []` — the `else` was dead code given the early return above it | Removed `if/else`; always call `detect_customizations()` directly |
| Silent `except` in `_read_cache()` | `except Exception: pass` — errors silently swallowed | `except Exception as e:` with `print()` diagnostic; still returns `None` on error |

**Branch rebase (2026-03-14):** This branch was created before Phase 1 Items 1 and 2 landed on `main`. After those merges, `config.py` diverged: the branch replaced `ReleaseConfig` (from Item 1) with `UpdatesConfig` (from Item 4). Resolution: rebased onto `main`; `PaceConfig` now contains both fields:

```python
release: ReleaseConfig | None = None   # from Item 1
updates: UpdatesConfig = None          # from Item 4 (post_init default)
```

**Impact:** Auto-update core is functional. CONDUIT report integration deferred. Tutorial URL is a known placeholder that needs a real docs page before v2.0-beta GA.

---

### Item 8 — Cron Configuration

**Branch:** `phase2/item-8-cron-config`
**PR:** #6
**Status:** Merged

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

#### Item 8: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Step 4 | `orchestrator.py` `finally` block releases lock | Lock release registered via `atexit.register()` in `orchestrator.py` — not a `finally` block | Variation — `atexit` is cleaner given `sys.exit()` calls throughout `main()` (see AD-8-1) |
| Step 5 | `config_tester.py` suggestion: run `ci_generator.py` if cron values differ from workflow file | `config_tester.py` not modified; cross-item wiring not done | Deferred to Phase 2 follow-up |

**Default cron schedule changes from ROADMAP spec:**

| Schedule | ROADMAP Spec | Implemented Default | Rationale |
| -------- | ------------ | ------------------- | --------- |
| `pace_pipeline` | `0 6 * * 1-5` (06:00 UTC weekdays) | `0 9 * * 1-5` (09:00 UTC weekdays) | 09:00 UTC avoids overlap with overnight CI jobs and aligns with business hours in IST/AEST |
| `planner_pipeline` | `0 7 * * 0` (07:00 Sunday) | `0 8 * * 1` (08:00 Monday) | Monday morning re-plan fits sprint cadence better; Sunday is typically off-hours for most teams |
| `update_check` | `0 0 * * *` (midnight) | `0 0 * * *` (midnight) | Unchanged |

**Branch rebase (2026-03-14):** This branch was created before Phase 1 Items 1 and 2 landed on `main`. After those merges, `config.py` diverged: the branch replaced `ReleaseConfig` (from Item 1) with `CronConfig` (from Item 8). Resolution: rebased onto `main`; `PaceConfig` now contains both fields:

```python
release: ReleaseConfig | None = None   # from Item 1
cron: CronConfig = None                # from Item 8 (post_init default)
```

**Impact:** Pipeline lock and cron config are fully functional. The `config_tester.py` cross-wire suggestion is a UX improvement deferred to follow-up work.

---

## Phase 3 — Reliability & Reach (v2.0-rc)

### Item 5 — Communications & Alerting

**Branch:** `phase3/item-5-notifications`
**PR:** #7
**Status:** Merged

#### Item 5: Changes

| File | Change Type | Description |
| ---- | ----------- | ----------- |
| `pace/notifications/__init__.py` | New | `get_notification_adapter()` factory |
| `pace/notifications/base.py` | New | `NotificationAdapter` ABC + 5 event constants |
| `pace/notifications/slack.py` | New | `SlackAdapter` — Incoming Webhook via `requests` |
| `pace/notifications/teams.py` | New | `TeamsAdapter` — MessageCard format, color-coded by event |
| `pace/notifications/email.py` | New | `EmailAdapter` — stdlib `smtplib`, STARTTLS, zero new deps |
| `pace/alert_engine.py` | New | `AlertEngine` — evaluates rules, dispatches to channels |
| `pace/config.py` | Modified | `SlackConfig`, `TeamsConfig`, `EmailConfig`, `NotificationsConfig`, `AlertRuleConfig`; `_interpolate_env()`; `_parse_notifications()`, `_parse_alerts()` wired into `load_config()` |
| `pace/pace.config.yaml` | Modified | `notifications:` and `alerts:` sections added (commented examples) |
| `pace/orchestrator.py` | Modified | `AlertEngine` instantiated in `main()`; `fire()` at `hold_opened`, `story_shipped`, `cost_exceeded` |
| `pace/preflight.py` | Modified | `pipeline_lock_timeout` fired before `RuntimeError` in `acquire_pipeline_lock()` |
| `pace/config_tester.py` | Modified | `_validate_notifications()` — channel credential checks, alert rule event validation |

#### Architecture: NotificationAdapter ABC

Follows the same pattern as `CIAdapter` / `TrackerAdapter`:

```python
class NotificationAdapter(ABC):
    @abstractmethod
    def send(self, event: str, payload: dict) -> bool: ...
```

Each adapter (`SlackAdapter`, `TeamsAdapter`, `EmailAdapter`) is self-contained with per-event message templates. `AlertEngine` is the orchestrating layer — it holds the rule list from config, builds adapters once at startup, and routes `fire(event, payload)` calls to the appropriate channels.

#### Alert Events

| Constant | When fired |
| -------- | ---------- |
| `hold_opened` | After `tracker.open_escalation_issue()` in `orchestrator.py` |
| `story_shipped` | After `=== SHIPPED ===` print in `orchestrator.py` |
| `cost_exceeded` | Inside `_update_daily_spend()` atexit callback |
| `pipeline_lock_timeout` | Before `RuntimeError` in `preflight.acquire_pipeline_lock()` |
| `update_available` | Wired in `updater.py` for future use |

#### Threshold Guards

`AlertRuleConfig` supports optional `threshold_usd` and `threshold_minutes`. `AlertEngine._threshold_met()` checks these against the event payload — a `cost_exceeded` rule with `threshold_usd: 5.0` only fires when `payload["cost_usd"] >= 5.0`. Rules without thresholds always fire.

#### Credential Interpolation

`_interpolate_env()` replaces `${VAR_NAME}` patterns in any string-valued config field at load time. Credentials (webhook URLs, SMTP passwords) are never stored in plain text in `pace.config.yaml` — they reference environment variables that CI/CD injects at runtime.

#### Item 5: Architectural Decisions

**AD-5-1: `EmailAdapter` uses stdlib `smtplib` only**
Rationale: Adding a third-party mailer library (`sendgrid`, `boto3/ses`) would require pip changes in every PACE installation. `smtplib` + STARTTLS covers the vast majority of SMTP relays (Gmail App Password, SendGrid SMTP bridge, AWS SES SMTP) with zero new dependencies.

**AD-5-2: Best-effort alerting — channel errors never re-raised**
Rationale: A failed Slack webhook must not abort a PACE pipeline. `AlertEngine` logs errors and continues. If all channels fail, the pipeline still runs to completion.

**AD-5-3: `AlertEngine` instantiated once in `main()`, passed as list ref to closures**
Rationale: `_update_daily_spend()` is registered as an `atexit` callback and cannot take arguments after registration. A one-element list (`_alert_engine_ref`) acts as a mutable cell that the closure captures by reference — avoiding a global variable while still being accessible from the atexit scope.

#### Item 5: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Step 5 (`config_tester.py`) | Validate channel creds exist | Also validates alert rule events against known event constants; cross-references channels in rules against configured channels | Enhancement |
| `update_available` event | Wire into `updater.py` | Constant defined, not yet fired from updater | Deferred |

---

### Item 6 — Tracker Artifact Push

**Branch:** `phase3/item-6-tracker-artifacts`
**PR:** #8
**Status:** Merged (rebased onto main 2026-03-14 after Item 5 conflict resolution)

#### Item 6: Changes

| File | Change Type | Description |
| ---- | ----------- | ----------- |
| `pace/platforms/base.py` | Modified | `push_story()`, `update_story_status()`, `post_handoff_comment()` abstract methods on `TrackerAdapter` |
| `pace/platforms/github.py` | Modified | Implemented `push_story`, `update_story_status`, `post_handoff_comment` |
| `pace/platforms/gitlab.py` | Modified | Implemented `push_story`, `update_story_status`, `post_handoff_comment` |
| `pace/platforms/jira.py` | Modified | Implemented `push_story`, `update_story_status` (transition API), `post_handoff_comment`; `_find_transition_id()` helper |
| `pace/platforms/bitbucket.py` | Modified | Implemented `push_story`, `update_story_status`, `post_handoff_comment` |
| `pace/platforms/local.py` | Modified | No-op stubs for new abstract methods |
| `pace/issue_template.py` | New | `render_story_issue_body()` — Markdown template for story issues |
| `pace/orchestrator.py` | Modified | `push_story` after PRIME generates story; `update_story_status` + `post_handoff_comment` at SHIP (after alert fire) |
| `pace/config_tester.py` | Modified | `_validate_tracker()` — warns when tracker configured but credentials missing |

#### New TrackerAdapter Methods

| Method | Signature | Purpose |
| ------ | --------- | ------- |
| `push_story` | `(day, day_dir) -> str` | Creates/updates a tracker issue from the PRIME story output; returns URL |
| `update_story_status` | `(day, day_dir, status) -> None` | Transitions the tracker issue to a new status (`done`, `in-progress`, etc.) |
| `post_handoff_comment` | `(day, day_dir) -> None` | Posts a comment linking the shipped artifacts (PR URL, gate report, sentinel report) |

#### Jira Transition Lookup

Jira uses numeric transition IDs, not status names. `_find_transition_id(key, target_name)` calls `GET /issue/{key}/transitions` and returns the first transition whose name contains `target_name` (case-insensitive). This handles varied Jira workflow names (`Done`, `Mark as Done`, `Close`) without hardcoding IDs.

#### SHIP Ordering

At SHIP, the orchestrator fires in this order:

1. `AlertEngine.fire("story_shipped", ...)` — alert channels notified first
2. `tracker.update_story_status(day, day_dir, "done")` — issue closed
3. `tracker.post_handoff_comment(day, day_dir)` — handoff comment posted

Both tracker calls are wrapped in a single `try/except` — a tracker failure is logged and never blocks the pipeline exit.

#### Item 6: Architectural Decisions

**AD-6-1: Separate `push_story` from `open_escalation_issue`**
Rationale: Story issues and escalation issues have different lifecycles. Stories are created at sprint start and closed at SHIP. Escalation issues are created on HOLD and may outlive the sprint. Keeping them as separate abstract methods avoids an overloaded method with a `type` flag.

**AD-6-2: `issue_template.py` for story body rendering**
Rationale: The Markdown body is used by all five platform adapters. A shared template module avoids duplication and ensures all trackers render the same structured body (AC list, tech context, links).

**AD-6-3: `_find_transition_id` logs errors instead of silent pass**
Rationale: A bare `except: pass` made Jira API failures invisible. Logging the exception with key and target name lets operators diagnose misconfigured Jira workflows without enabling debug mode.

#### Item 6: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| `TrackerConfig` dataclass | Add to `config.py` | `tracker_type` already existed as a string field; no new dataclass needed | Simplified |
| Tests / fixtures | Add integration test fixtures | Not implemented in this PR | Deferred to Phase 4 |

---

### Item 7 — GitLab, Jenkins, and Bitbucket Pipeline Finalization

**Branch:** `phase3/item-7-platform-finalization`
**PR:** #9
**Status:** Merged

#### Item 7: Changes

| File | Change Type | Description |
| ---- | ----------- | ----------- |
| `pace/platforms/base.py` | Modified | `get_variable(name) -> str \| None` concrete method on `CIAdapter` (reads `os.environ`) |
| `pace/platforms/jenkins.py` | Modified | `set_variable()` persists to `jenkins-variables.json`; `get_variable()` reads env first, then JSON store |
| `pace/platforms/gitlab.py` | Modified | `GitLabBranchingAdapter` — full branches/MR API |
| `pace/platforms/bitbucket.py` | Modified | `BitbucketBranchingAdapter` — full refs/PRs API |
| `pace/branching.py` | Modified | Factory wired for `gitlab` and `bitbucket` ci_type |
| `pace/ci_generator.py` | Modified | Removed `not yet implemented` stubs; added real `_update_gitlab_cron()`, `_update_jenkins_cron()`, `_update_bitbucket_cron()`; generic `_update_cron_in_file()` helper |
| `.gitlab-ci.yml` | New | Full PACE pipeline template (plan/forge/gate/sentinel/conduit stages) |
| `Jenkinsfile` | New | Declarative pipeline with equivalent stages + cron trigger |
| `bitbucket-pipelines.yml` | New | Pipelines YAML with equivalent step structure |

#### `get_variable` on `CIAdapter`

The base implementation reads from `os.environ`, which covers GitHub Actions (`vars.*`), GitLab CI/CD variables, and Bitbucket repository variables — all inject variables as env vars before the job runs. Jenkins overrides to also read `jenkins-variables.json` (the file-based store written by `set_variable()`), because Jenkins has no built-in runtime variable mutation API.

#### GitLab and Bitbucket BranchingAdapters

Both follow the `GitHubBranchingAdapter` pattern:

| Method | GitLab API | Bitbucket API |
| ------ | ---------- | ------------- |
| `get_branch_sha` | `GET /projects/:id/repository/branches/:branch` | `GET /repositories/:ws/:repo/refs/branches/:branch` |
| `create_branch` | `POST /projects/:id/repository/branches` | `POST /repositories/:ws/:repo/refs/branches` |
| `create_pull_request` | `POST /projects/:id/merge_requests` | `POST /repositories/:ws/:repo/pullrequests` |

409/400-already-exists responses are treated as no-ops (idempotent create).

#### CI Template Design

GitLab and Bitbucket schedule their pipelines through the platform UI (not in the YAML file), so `ci_generator.py` emits an advisory message for those platforms rather than patching a file. Jenkins schedules via the `cron()` trigger in the Jenkinsfile, which `ci_generator.py` patches in-place using a regex.

#### Item 7: Architectural Decisions

**AD-7-1: `get_variable` as a concrete base method, not abstract**
Rationale: All five CI platforms inject variables as environment variables. Making the base method concrete with `os.environ.get(name)` means only Jenkins needs to override. Platforms that don't need file-based persistence get correct behavior for free.

**AD-7-2: GitLab/Bitbucket schedule management stays in UI**
Rationale: GitLab CI schedules (`CI/CD → Schedules`) and Bitbucket pipeline schedules (`Repository Settings → Pipelines → Schedules`) are not expressible in the pipeline YAML file — they exist as first-class objects in the platform UI. `ci_generator.py` informs users of the required cron expression rather than pretending it can set the schedule programmatically.

**AD-7-3: Jenkins variables persisted to `jenkins-variables.json`**
Rationale: Jenkins has no REST API for runtime variable mutation that works across all installation types (freestyle, declarative, scripted). File-based persistence in the repo root is the most portable approach — it works in any Jenkins agent where the workspace is writable.

#### Item 7: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Integration test fixtures | Add mock API response fixtures | Not implemented | Deferred to Phase 4 |
| `gitlab-ci-lint` validation | CI acceptance test | Not automated | Manual acceptance only |

---

## Cross-Cutting Decisions (Phase 3)

### CC-8: Phase 3 branches all target `main`

Same rationale as Phases 1 and 2 (CC-1, CC-4). All Phase 3 feature branches PR to `main`.

### CC-9: Conflict resolution order — Item 5 (main) takes precedence over Item 6 orchestrator changes

Item 5 modified `orchestrator.py` to add `AlertEngine.fire("story_shipped", ...)` at SHIP. Item 6 independently modified the same SHIP block to add tracker artifact push calls. When Item 6 rebased onto main (which had Item 5 merged), the correct resolution was to keep both — alert fires first, then tracker updates. Order is intentional: if the tracker call crashes, the alert has already fired and the pipeline still exits cleanly.

### CC-10: Notification/alert config fields use `__post_init__`-compatible defaults

`notifications` and `alerts` are `None`-defaulted optional fields on `PaceConfig`, parsed from YAML sections that may be absent. An absent `notifications:` section returns `None` from `_parse_notifications()` — `AlertEngine` short-circuits when `cfg.notifications is None`. No existing `pace.config.yaml` requires changes.

### CC-11: Item 7 branching adapters reuse `_GitLabBase` / `_BitbucketBase` credential pattern

Both `GitLabBranchingAdapter` and `BitbucketBranchingAdapter` inherit from the existing `_GitLabBase` / `_BitbucketBase` mixin classes, which centralise credential validation and HTTP headers. This avoids duplicating the `_available` guard and `_headers()` logic.

---

## Cross-Cutting Decisions (Phase 2)

### CC-4: Phase 2 branches also target `main`

Same rationale as Phase 1 (CC-1). All phase2 feature branches PR to `main`.

### CC-5: `__post_init__` pattern for optional config fields with defaults

Items 3, 4, and 8 all add new optional fields (`llm.limits`, `updates`, `cron`) to `PaceConfig` with rich dataclass defaults. Using `field(default_factory=...)` requires the field to be non-positional, which breaks the existing constructor call order. The `__post_init__` pattern (`= None` + post-init assignment) allows the field to stay at the end without changing existing call sites.

### CC-6: All new config sections are backward-compatible with existing configs

Any `pace.config.yaml` without `llm.limits`, `updates:`, or `cron:` sections parses cleanly with all defaults applied. No existing project needs to update their config to use v2.0.

### CC-7: Phase 2 branches required rebase after Phase 1 landed (2026-03-14)

All three Phase 2 branches (`phase2/item-3-context-versioning`, `phase2/item-4-auto-update`, `phase2/item-8-cron-config`) were created from `main` before Phase 1 Items 1 and 2 merged. After those merges, `config.py` on each Phase 2 branch was missing `ReleaseConfig` (added by Item 1). Rebasing surfaced merge conflicts in `config.py` for Items 4 and 8; Item 3 rebased cleanly.

**Conflict pattern (Items 4 and 8):** Each Phase 2 branch had replaced the `release: ReleaseConfig` field with its own new field (`updates: UpdatesConfig` or `cron: CronConfig`). The correct resolution in all cases was to keep both fields in `PaceConfig`, both parsers in `load_config()`, and both constructor arguments.

**Final `PaceConfig` optional-field section after resolution (on each respective branch):**

| Branch | Optional fields at tail of `PaceConfig` |
| ------ | --------------------------------------- |
| `phase2/item-3-context-versioning` | `release`, `llm.limits` (via `LLMConfig.__post_init__`) |
| `phase2/item-4-auto-update` | `release`, `updates` (via `PaceConfig.__post_init__`) |
| `phase2/item-8-cron-config` | `release`, `cron` (via `PaceConfig.__post_init__`) |

When all PRs are eventually merged to `main`, the canonical `PaceConfig` will contain all four: `release`, `llm.limits`, `updates`, and `cron`.

---

## Phase 4 — Plugin System (v2.1)

### Item 10 — Plugin System

**Branch:** `phase4/item-10-plugin-system`
**PR:** #11
**Status:** Merged (2026-03-14)

#### Item 10: Changes

| File | Change Type | Description |
| ---- | ----------- | ----------- |
| `pace/plugins/base.py` | New | `PluginManifest`, `PluginBase`, `HookBase`, `WebhookInBase`, `WebhookOutBase` ABCs + `HOOK_EVENTS` constants |
| `pace/plugins/loader.py` | New | `PluginRegistry` + `load_all()` via `importlib.metadata.entry_points()`; `_version_compatible()` guard; webhook-in HTTP server thread |
| `pace/plugins/__init__.py` | New | Public exports for plugin authors |
| `pace/config.py` | Modified | `PluginEntryConfig` dataclass; `plugins` field on `PaceConfig`; `_parse_plugins()`; `PACE_VERSION → "2.0.0"` |
| `pace/pace.config.yaml` | Modified | Documented `plugins:` section with commented examples |
| `pace/orchestrator.py` | Modified | `load_plugins()` at startup; `fire_hook()` at `pipeline_start`, `day_start`, `day_shipped`, `day_held`, `pipeline_end` (atexit) |
| `pace/config_tester.py` | Modified | `_validate_plugins()` — checks entries have names, warns on uninstalled plugins, warns on version range incompatibility for installed plugins |

#### Plugin Types

| Type | Interface | Purpose |
| ---- | --------- | ------- |
| `agent` | `PluginBase` | New PACE agents callable from the pipeline |
| `tool` | `PluginBase` | Tools for FORGE/SCRIBE's tool registry |
| `adapter` | `PluginBase` | LLM/platform/notification adapters |
| `hook` | `HookBase` | Synchronous lifecycle hooks — `on_event(event, payload)` |
| `webhook-in` | `WebhookInBase` | HTTP listener for external triggers (port 9876) |
| `webhook-out` | `WebhookOutBase` | JSON POST to a URL on lifecycle events |

#### Entry Point Discovery

`PluginRegistry.load_all()` uses `importlib.metadata.entry_points(group="pace.plugins")`. Any installed Python package that declares a `pace.plugins` entry point is automatically discovered at startup — no config change required. The `plugins:` config section controls which discovered plugins are enabled and allows version constraints.

#### Lifecycle Events

`fire_hook()` in `orchestrator.py` fires at five points:

| Event | When |
| ----- | ---- |
| `pipeline_start` | After preflight, before Day 0/PRIME |
| `day_start` | Before PRIME generates each story |
| `day_shipped` | After GATE issues SHIP decision |
| `day_held` | After GATE issues HOLD decision |
| `pipeline_end` | atexit — fires on SHIP, HOLD, ABORT, or unhandled exception |

`fire_hook()` wraps each plugin's `on_event()` call in try/except — a plugin crash never blocks the pipeline.

#### Version Compatibility Guard

`_version_compatible(plugin_version, constraint)` parses the constraint string (e.g., `">=2.0,<3.0"`) and checks the installed plugin version against it. An incompatible plugin emits a warning and is skipped — not a hard error.

#### Item 10: Architectural Decisions

**AD-10-1: `importlib.metadata` entry points, not a plugin directory scan**
Rationale: Entry points are the PEP 517/518 standard for Python package extension. Any pip-installed package can register a plugin without modifying the PACE source tree. A directory scan would require plugins to be placed in a PACE-owned path.

**AD-10-2: Synchronous `fire_hook()` with try/except isolation**
Rationale: Async hooks introduce ordering complexity and make it hard to reason about pipeline state. Synchronous hooks fire in registration order and complete before the pipeline proceeds. The try/except around each call ensures a broken plugin never propagates an exception into the core pipeline.

**AD-10-3: Webhook-in runs on a background daemon thread (port 9876)**
Rationale: The HTTP listener must not block the main pipeline thread. A daemon thread terminates automatically when the main process exits — no explicit shutdown required.

**AD-10-4: `PACE_VERSION` bumped to `"2.0.0"` in `config.py`**
Rationale: The plugin system is the final feature completing the v2.0 feature set. The version constant is used by `_version_compatible()` and by plugins that need to check the running PACE version.

#### Post-PR Fix

**fix(config_tester): log exceptions in `_validate_plugins`** (commit `d327a30`, 2026-03-15)

All four empty `except` clauses in `_validate_plugins` (two in the discovery loop, two in the compat-check loop) were silently swallowing exceptions. Fixed to bind the exception and emit `r.warn()` with plugin entry point name, group, and error message. Non-fatal behavior preserved.

#### Item 10: Variations from Plan

| ROADMAP Step | Planned | Actual | Status |
| ------------ | ------- | ------ | ------ |
| Webhook-in port | Not specified in plan | Port 9876 hardcoded | Acceptable default — configurable port deferred |
| Integration test with real entry point | Planned | Not implemented in PR | Deferred to test infrastructure sprint |

---

## Post-Phase4 Stability Fixes (2026-03-15/16)

Six fixes were merged directly to `main` between PR #11 (Plugin System) and PR #12 (Training Data Pipeline), addressing runtime failures found during live pipeline runs.

| Commit | Change | Files |
| ------ | ------ | ----- |
| `879d24f` | `spend_tracker.install()` was called by `orchestrator.py` at import time but never implemented. No-op shim added — correct because `forge.py` routes all calls through the LLM adapter which calls `record()` explicitly | `pace/spend_tracker.py` |
| `f7c5665` | Before creating a review PR, check if one already exists (any state) for the head branch; return existing URL instead of crashing with 422 | `pace/platforms/github.py` |
| `463e305` | Add `git pull --rebase` before `git push` in FORGE and orchestrator — a fix commit pushed mid-run diverged the CI runner's local branch, burning all 100 iterations retrying `git_commit` | `pace/agents/forge.py`, `pace/orchestrator.py` |
| `c6fb459` | Two bugs caused pipeline lock to falsely block: (1) FORGE's `git add -A` committed `.pace/pipeline.lock` to the repo; (2) `acquire_pipeline_lock` used `st_mtime` for age, which equals checkout time after `git checkout`. Fix: add `pipeline.lock` to `.gitignore`; use `started=` timestamp from file content for age | `.gitignore`, `pace/preflight.py` |
| `62ecf98` | `git pull --rebase` aborted with "unstaged changes" because `pipeline.lock` left the working tree dirty. Add `--autostash` to stash before rebase and pop after | `pace/agents/forge.py`, `pace/orchestrator.py` |
| `30b5caf` | `origin HEAD` resolves to `main` (the default branch), causing rebase to replay all sprint commits. Switch to tracking branch. Also `--autostash` only stashes tracked files — replace with `git stash -u` to cover untracked files like `pipeline.lock` | `pace/agents/forge.py`, `pace/orchestrator.py` |

**Root cause:** All six fixes trace to the interaction between FORGE's git operations and the pipeline lock file. The core issue — `pipeline.lock` being committed to the repository — was the root; the autostash/tracking-branch fixes were downstream symptoms.

---

## Phase 5 — Training Data Pipeline (@Since v2.2)

### Item 11 — Training Data Pipeline (PR #12 — branch `phase5/item-11-training-data-pipeline`)

**Goal:** Instrument every shipped sprint day to produce a JSONL training corpus ready for LLM supervised fine-tuning (SFT) and RLHF reward modelling.

**Files created / modified:**

| File | Change |
| ---- | ------ |
| `pace/training/__init__.py` | New — public API for the training module |
| `pace/training/collector.py` | New — `StoryTrace` dataclass + `collect_story_trace()` + `collect_all_traces()` + reward scoring |
| `pace/training/exporter.py` | New — `export_sft_jsonl()` (Anthropic messages format) + `export_reward_jsonl()` (prompt/completion/reward) |
| `pace/training/hook.py` | New — `DataExportHook(HookBase)` subscribed to `day_shipped`; configured from `TrainingConfig` |
| `pace/agents/forge.py` | Added `_trace_path()` + `_save_trace()` helpers; call `_save_trace()` before `_clear_checkpoint()` on successful handoff |
| `pace/config.py` | Added `TrainingConfig` dataclass + `training` field on `PaceConfig` + `_parse_training()` + wired into `load_config()` |
| `pace/pace.config.yaml` | Added documented `training:` section with all four knobs uncommented and ready to use |
| `pace/orchestrator.py` | Register `DataExportHook` when `cfg.training.export_on_ship`; fire all 5 remaining `HOOK_EVENTS` (`story_generated`, `forge_complete`, `gate_pass`, `sentinel_pass`, `conduit_pass`); pass `registry` to `run_cycle()`; add `pace_dir` to `day_shipped` payload |
| `pace/config_tester.py` | Added `_validate_training()` + wired into `run_config_test()` |
| `ROADMAP.md` | Added Phase 5 section (Item 11); sequencing summary updated to v2.2; footer version v1.3 |
| `ROADMAP-EXECUTION-LOG.md` | This entry; log version 1.7 |

**Key design decisions:**

- **Trace preservation strategy**: `forge_checkpoint.json` is cleared on successful handoff (needed for retry idempotency). Rather than change the clear semantics, `_save_trace()` writes `forge_trace.json` immediately before `_clear_checkpoint()` — the trace persists as a permanent day artifact; the checkpoint is still ephemeral.
- **`DataExportHook` as a built-in, not entry-point plugin**: The hook ships with PACE itself and is registered directly by the orchestrator (not via `importlib.metadata`). It still uses the full `HookBase`/`PluginRegistry` infrastructure, so it benefits from `fire_hook()`'s error isolation.
- **Reward score formula**: `score = clamp(gate_pass_rate + 0.10*(iterations≤10) - min(0.20, cost_usd*0.10), 0.0, 1.0)`. This anchors quality to GATE pass rate, rewards efficiency, and penalises expensive runs — all without requiring human labellers.
- **All remaining `HOOK_EVENTS` now fired**: `story_generated`, `forge_complete`, `gate_pass`, `sentinel_pass`, `conduit_pass` were declared in `base.py` (Phase 4) but not yet fired. Phase 5 fires them all, closing the gap between the declared event vocabulary and the actual orchestrator lifecycle.

**Acceptance criteria status:**

| AC | Status |
| -- | ------ |
| `forge_trace.json` written on successful handoff | ✅ |
| `DataExportHook` appends JSONL per shipped day | ✅ |
| `export_sft_jsonl()` Anthropic format | ✅ |
| `export_reward_jsonl()` prompt/completion/reward | ✅ |
| `_validate_training()` covers all knobs | ✅ |
| All 5 remaining `HOOK_EVENTS` fired | ✅ |

---

## ROADMAP v1.4 Update (2026-03-16)

### Phase 6 — Architecture Maturity (@Since v3.0): Planning

**Log entry type:** ROADMAP planning (no code shipped in this update)

All seven Phase 6 items are in `Planned` status. The ROADMAP was extended from v1.3 → v1.4 to capture them before implementation begins.

| Item | Title | Target |
| ---- | ----- | ------ |
| Item 12 | `context.manifest.yaml` — SHA-256 doc hashing + change detection | v3.0 |
| Item 13 | Context auto-refresh on PRD/SRS document changes | v3.0 |
| Item 14 | Multi-release `releases:` list config | v3.0 |
| Item 15 | `plan.yaml` versioning + `story-N` rename | v3.0 |
| Item 16 | Extended pre-run validation (`--strict` mode) | v3.0 |
| Item 17 | `.pacemap/` directory for ROADMAP snapshots | v3.0 |
| Item 18 | `CHANGELOG.md` auto-update by planner + orchestrator | v3.0 |

**Item 7 status correction:** ROADMAP v1.3 incorrectly listed Item 7 as `Planned — not yet started`. Item 7 (Platform Finalization) was implemented in Phase 3, merged via PR #10 on 2026-03-14. Corrected in ROADMAP v1.4.

---

## Unit Test Suite (2026-03-16)

**Not tied to a ROADMAP item.** Added as a cross-cutting quality baseline before Phase 6 development begins.

| File | Tests | Coverage target |
| ---- | ----- | --------------- |
| `tests/test_config.py` | 27 | `pace/config.py` |
| `tests/test_ci_generator.py` | 53 | `pace/ci_generator.py` |
| `tests/test_platforms_factory.py` | 19 | `pace/platforms/` factory + local adapter |
| `tests/test_platforms_local.py` | 51 | GitHub / GitLab / Bitbucket adapters |
| `tests/test_plugins_base.py` | 22 | `pace/plugins/base.py` |
| `tests/test_small_utils.py` | 38 | Branching helpers, spend tracker utils, misc |
| `tests/test_spend_tracker.py` | 28 | `pace/spend_tracker.py` |
| `tests/test_training_collector.py` | 44 | `pace/training/collector.py` |
| `tests/test_training_exporter.py` | 36 | `pace/training/exporter.py` |
| `tests/test_training_hook.py` | 27 | `pace/training/hook.py` |

**Total: 223 tests. Coverage baseline: 82.76% (recorded in `.audit/coverage/baseline.md`).**

`setup.cfg` adds `testpaths = tests` and omits `tests/`, `pace/agents/`, `pace/pace.config.yaml`, and `migrations/` from coverage measurement.

**Architectural decision — AD-TEST-1: No integration tests yet**
Platform adapter integration tests (Items 6, 7 deferred steps in Pending Work) require live GitHub/GitLab/Bitbucket tokens and are left for a dedicated test infrastructure sprint. All 223 tests are unit tests using mocks for HTTP calls.

---

## Phase 6 — Architecture Maturity: Formal Execution Plan (2026-03-16)

**Log entry type:** Execution plan — no code shipped yet
**GitHub issues:** Created for all items (see issue links per item below)

### Dependency Graph

```text
Item 17 (.pacemap Directory)
  └─► Item 18 (CHANGELOG.md)           [pacemap.py required by update_changelog()]

Item 14 (Multi-Release Config)
  ├─► Item 12 (Context Versioning)     [active_release.name used for file archiving]
  │     └─► Item 13 (Context Auto-Refresh) [context.manifest.yaml from Item 12]
  ├─► Item 15 (plan.yaml & Story Naming)  [plan_file paths from releases: list]
  └─► Item 16 (Extended Validation)    [validates Items 14 + 15 schemas]
```

### Sprint Breakdown

| Sprint | Items | Branch Pattern | Key Deliverables |
| ------ | ----- | -------------- | ---------------- |
| 6.1 — Structural Foundation | 17, 18 | `feature/pacemap-directory`, `feature/changelog-md` | `.pacemap/` dir; `pace/pacemap.py`; `CHANGELOG.md` |
| 6.2 — Config Schema | 14 | `feature/multi-release-config` | `ReleaseConfig` dataclass; `releases:` list; migration script |
| 6.3 — Context System | 12, 13 | `feature/context-versioning`, `feature/context-auto-refresh` | `context.manifest.yaml`; SHA-256 hash checks; `--refresh-context` CLI |
| 6.4 — Plan System | 15 | `feature/plan-story-naming` | `story-N` keys; `_backup_plan()`; migration script |
| 6.5 — Validation | 16 | `feature/extended-validation` | `--strict` mode; `_validate_releases()`; CI pipeline updates |

### Items & GitHub Issues

| Item | Title | Sprint | GitHub Issue |
| ---- | ----- | ------ | ------------ |
| 12 | Release-Scoped Context Directory Versioning | 6.3 | #13 |
| 13 | Context Auto-Refresh on Document Updates | 6.3 | #14 |
| 14 | Multi-Release Configuration | 6.2 | #15 |
| 15 | plan.yaml Versioning & Story Naming | 6.4 | #16 |
| 16 | Pre-run Configuration Validation (Extended) | 6.5 | #17 |
| 17 | `.pacemap` Directory | 6.1 | #18 |
| 18 | CHANGELOG.md | 6.1 | #19 |
| — | Deferred Steps Sprint (Items 1–8 carry-overs) | Pre-6.1 | #20 |

### Deferred Steps Tracked in Issue #20

| Source | Step | Description |
| ------ | ---- | ----------- |
| Item 1, step 5 | Phase 3 | CONDUIT: staging CI gate → main PR flow |
| Item 1, step 6 | Phase 3 | `preflight.py` branch-protection checks |
| Item 2, step 3 | Phase 3 | PRIME `plan_mode` flag (structured re-plan diff) |
| Item 2, step 5 | Phase 3 | SCRIBE planning report (budget impact + scope delta) |
| Item 3, step 6 | Phase 3 | Per-call retry with compacted prompt on token limit |
| Item 4, step 7 | Phase 3 | CONDUIT version-update summary in daily report |
| Item 4, tutorial URL | Phase 3 | Replace `pace-docs.example.com` placeholder in `updater.py` |
| Item 8, step 5 | Phase 2 follow-up | `config_tester.py` ↔ `ci_generator.py` cross-wire suggestion |
| Item 5, `update_available` | Phase 3 | Wire event into `updater.py` lifecycle |
| Items 6, 7 integration tests | Phase 3 | Platform adapter test fixtures (requires live tokens) |
| Item 10, webhook-in port | Phase 4 | Configurable webhook-in port (currently hardcoded 8765) |

### Architectural Decisions — Phase 6 Planning

**AD-P6-1: Deliver Items 17+18 first**
`.pacemap/` reorganises the ROADMAP files into a managed directory and creates `pacemap.py`. Since Item 18 (CHANGELOG) uses `pacemap.py`, Item 17 must ship first. These two items are pure file-system changes with no config schema dependency.

**AD-P6-2: Item 14 (Multi-Release) is the critical path blocker**
Items 12, 13, 15, and 16 all consume `cfg.active_release`. Item 14 ships in Sprint 6.2 before any of those begin, to avoid rebasing conflicts on the config schema.

**AD-P6-3: Items 12 and 13 ship in the same sprint but separate PRs**
Item 13 reads `context.manifest.yaml` written by Item 12. They are developed together but merged sequentially (12 first, then 13) to keep each PR reviewable independently.

**AD-P6-4: All Phase 6 items are breaking changes**
`plan.yaml` keys change (`day-N` → `story-N`), config schema changes (`release:` → `releases:`), and context directory layout changes. Migration scripts are mandatory deliverables for all three breaking items (12, 14, 15). A `MIGRATION_GUIDE.md` will be added to `.pacemap/` as part of Sprint 6.1.

**AD-P6-5: Deferred steps sprint is pre-Phase-6**
Deferred steps are isolated fixes to already-delivered items and have no dependency on Phase 6 schema changes. They will be batched into a single `feature/deferred-steps-cleanup` branch and merged before Sprint 6.1 begins.

---

## Merged to Main

| Item | PR | Merged |
| ---- | -- | ------ |
| fix/timestamp-precision (pre-ROADMAP) | #1 | ✅ 2026-03-08 |
| Item 9 (Config Tester) | Direct commit `75f25b0` | ✅ 2026-03-13 |
| Item 1 (Branching Model) | #2 | ✅ 2026-03-14 |
| Item 2 (PACE Planner) | #3 | ✅ 2026-03-14 |
| Item 3 (Context Versioning) | #4 | ✅ 2026-03-14 |
| Item 4 (Auto-Update) | #5 | ✅ 2026-03-14 |
| Item 8 (Cron Config) | #6 | ✅ 2026-03-14 |
| Item 5 (Communications & Alerting) | #7 | ✅ 2026-03-14 |
| Item 6 (Tracker Artifact Push) | #8 | ✅ 2026-03-14 |
| Item 7 (Platform Finalization) | #10 | ✅ 2026-03-15 |
| Item 10 (Plugin System) | #11 | ✅ 2026-03-15 |
| Item 11 (Training Data Pipeline) | #12 | ✅ 2026-03-15 |
| Deferred Steps Cleanup (Items 1–8) | #21 | ✅ 2026-03-16 |
| fix/pace-planner-yaml-syntax | #22 | ✅ 2026-03-17 |
| Item 17 (.pacemap Directory) | #TBD | 🔄 2026-03-17 (PR open) |
| Item 18 (CHANGELOG.md) | #TBD | 🔄 2026-03-17 (PR open, conflicts) |
| Item 14 (Multi-Release Config) | #15 | 🔄 2026-03-17 (PR open) |
| Item 12 (Context Versioning) | #16 | 🔄 2026-03-17 (PR open) |

## Pending Work

| Item | Status | Next Action |
| ---- | ------ | ----------- |
| Sprint 6.3 — Items 13, 15, 16 | Complete | All merged (PRs #27, #28, #29); issues #17, #18, #19 closed |
| Integration tests (Items 6, 7) | Not started | Platform adapter fixtures |

---

### Sprint 6.1 — Item 17: .pacemap Directory (2026-03-17)

**Branch:** `feature/pacemap-directory`
**Issue:** #13
**Tests:** 278 passing, 83% coverage (21 new in `tests/test_pacemap.py`)

| Step | File | Change |
| ---- | ---- | ------ |
| 1 | `.pacemap/ROADMAP.md` | Moved from repo root via `git mv` |
| 1 | `.pacemap/ROADMAP-EXECUTION-LOG.md` | Moved from repo root via `git mv` |
| 2 | `pace/pacemap.py` | New module: `snapshot_roadmap()`, `snapshot_roadmap_if_version_changed()` |
| 3 | `pace/config_tester.py` | Updated cross-references from `ROADMAP.md` → `.pacemap/ROADMAP.md` |
| 4 | `pace/ci_generator.py` | `_maybe_snapshot_roadmap()` called from `generate(apply=True)` |
| 5 | `.gitignore` | Verified `.pacemap/` is not ignored |
| — | `pace/pacemap.py` | Also includes Item 18 CHANGELOG helpers (`update_changelog`, `update_changelog_story_shipped`) |

---

### Deferred Steps Cleanup — Sprint Entry (2026-03-16)

**Branch:** `feature/deferred-steps-cleanup`
**Issue:** #20
**Tests:** 257 passing (34 new in `tests/test_deferred_steps.py`)

All 11 deferred steps across Items 1–8 implemented:

| Step | File | Change |
| ---- | ---- | ------ |
| Item 1 step 5 | `pace/orchestrator.py` | `_try_open_staging_pr()` — open sprint→release PR after CONDUIT SHIP + passing CI |
| Item 1 step 6 | `pace/preflight.py` | `_check_branch_protection()` — non-fatal GitHub API branch protection check |
| Item 2 step 3 | `pace/agents/prime.py` | `plan_diff` param injected into PRIME user message for PACE_REPLAN=true |
| Item 2 step 5 | `pace/agents/scribe.py` | `_write_scribe_report()` — emit `.pace/scribe_report.yaml` after SCRIBE completes |
| Item 3 step 6 | `pace/llm/anthropic_adapter.py` | Token limit retry: catch `BadRequestError`, compact to 60%, retry once |
| Item 4 deferred | `pace/updater.py` | Fix docs URL; `_write_update_status()` / `_clear_update_status()`; `_fire_update_available_event()` |
| Item 5 deferred | `pace/updater.py` | Wire `update_available` AlertEngine event into `check_and_warn()` |
| Item 4 step 7 | `pace/reporter.py` | `_load_update_status()` + "PACE Update Available" section in `write_job_summary()` |
| Item 8 step 5 | `pace/config_tester.py` | Suggest `ci_generator.py --check` in `_validate_cron()` when no cron errors |

---

### fix/pace-planner-yaml-syntax — Fix Entry (2026-03-17)

**Branch:** `fix/pace-planner-yaml-syntax`
**Tests:** 257 passing, 83% coverage (no new tests — pure workflow YAML change)

| File | Change |
| ---- | ------ |
| `.github/workflows/pace-planner.yml` | Replace multi-line `git commit -m "..."` (column-0 body broke YAML block scalar) with single-line `printf` form |
| `.github/workflows/pace-planner.yml` | Replace bash heredoc `<<'PRBODY'` in `run:` block with `PR_BODY` env-var block scalar (column-0 heredoc content terminated YAML block scalar prematurely) |

---

---

### Sprint 6.2 — Item 14: Multi-Release Configuration (2026-03-17)

**Branch:** `feature/multi-release-config`
**Issue:** #15
**Tests:** 302 passing, 83% coverage (24 new in `tests/test_multi_release.py`)

| Step | File | Change |
| ---- | ---- | ------ |
| 1 | `pace/config.py` | `ReleaseConfig`: added `plan_file: str` and `status: str` fields |
| 2 | `pace/config.py` | `PaceConfig`: replaced `release: ReleaseConfig \| None` with `releases: list[ReleaseConfig] \| None` |
| 2 | `pace/config.py` | `PaceConfig.active_release` property: returns active entry respecting `PACE_RELEASE` env-var override; raises on multiple active |
| 2 | `pace/config.py` | `_load_config_from_path()` extracted from `load_config()` for testability; parses both `releases:` list and legacy `release:` key |
| 3 | `pace/config_tester.py` | `_validate_releases()`: validates name uniqueness, `sprint_days ≤ release_days`, exactly one `status: active`, valid status values; legacy `release:` key suggests migration |
| 4 | `pace/orchestrator.py` | `_try_open_staging_pr()`: `cfg.release` → `cfg.active_release` |
| 6 | `pace/migrations/v3_multi_release.py` | New migration script: rewrites legacy `release:` key to `releases:` list; supports `--dry-run` |

---

### Sprint 6.3 — Item 12: Release-Scoped Context Directory Versioning (2026-03-17)

**Branch:** `feature/context-versioning`
**Issue:** #16
**Tests:** 321 passing, 83% coverage (19 new in `tests/test_context_versioning.py`)

| Step | File | Change |
| ---- | ---- | ------ |
| 1 | `pace/schemas.py` | `CONTEXT_MANIFEST_SCHEMA` — JSON schema for `context.manifest.yaml` |
| 2 | `pace/preflight.py` | `_archive_context_for_release_change()` — reads manifest, archives prior-release docs to `<stem>.<release>.md` when release changes; called from `run_preflight()` |
| 3 | `pace/agents/scribe.py` | `_sha256()` helper; `_write_context_manifest()` — writes `.pace/context/context.manifest.yaml` with release, timestamp, source-doc hashes, and files list; called from `run_scribe()` |
| 4 | `pace/migrations/v3_context_versioning.py` | Migration: archives unversioned docs as `*.pre-v3.md`; supports `--dry-run` |
| 5 | `pace/config_tester.py` | `_validate_context_manifest()` — warns if context docs exist with no manifest or have untracked files |

---

### Sprint 6.3 — Item 13: Context Auto-Refresh on Document Updates (2026-03-17)

**Branch:** `feature/context-auto-refresh`
**Issue:** #17
**Tests:** 335 passing, 83% coverage (14 new in `tests/test_context_auto_refresh.py`)

| Step | File | Change |
| ---- | ---- | ------ |
| 1 | `pace/preflight.py` | `_archive_context(release_name, reason)` — moves context docs to `<stem>.<release>.<iso-date>.md`; handles same-day collision with counter; archives manifest |
| 2 | `pace/preflight.py` | `_check_context_freshness()` — reads manifest hashes, computes current SHA-256 of source docs, triggers `_archive_context` + SCRIBE on any change; returns list of changed docs |
| 3 | `pace/preflight.py` | Refactored `_archive_context_for_release_change()` to delegate to `_archive_context()` |
| 4 | `pace/preflight.py` | `force_refresh_context()` — unconditional archive + SCRIBE; exposed via `--refresh-context` CLI flag in `__main__` block |
| 5 | `pace/preflight.py` | `run_preflight()` now calls `_check_context_freshness()` after `_archive_context_for_release_change()` |
| 6 | `pace/planner.py` | `run_planner()` calls `_check_context_freshness()` when `replan=True` |
| 7 | `pace/config_tester.py` | `_KNOWN_SOURCE_DOCS` list + `_validate_source_docs()` — suggests adding README/PRD/SRS when none found in repo root |

---

### Sprint 6.3 — Item 15: plan.yaml Versioning & Story Naming (2026-03-17)

**Branch:** `feature/plan-yaml-versioning`
**Issue:** #18
**Tests:** 364 passing, 83% coverage (29 new in `tests/test_plan_yaml_versioning.py`)

| Step | File | Change |
| ---- | ---- | ------ |
| 1 | `pace/schemas.py` | `PLAN_SCHEMA` — JSON schema for `stories:` format plan.yaml |
| 2 | `pace/planner.py` | `_iter_stories()` — normalises both `stories:` and legacy `days:` to `(day_num, entry)` pairs |
| 2 | `pace/planner.py` | `_get_replan_boundary()` — returns index of last shipped story |
| 2 | `pace/planner.py` | `_backup_plan()` — copies plan.yaml to `.pace/releases/<release>/plan.yaml.bak.<iso-datetime>`; prunes backups older than 30 days |
| 3 | `pace/planner.py` | `run_planner()` — detects `stories:` format; uses `status: shipped` for completion; calls `_backup_plan()` on replan |
| 4 | `pace/orchestrator.py` | `get_day_plan()` — supports `stories:` key with `story-N` id; adds `target` alias for `title`; falls back to legacy `days:` |
| 5 | `pace/config_tester.py` | `_validate_plan()` — warns on missing `release` field and shipped stories without `shipped_at` |
| 6 | `pace/migrations/v3_plan_naming.py` | New migration: renames `day-N` entries to `story-N`; adds `status: shipped` based on `.pace/day-N/handoff.yaml`; supports `--dry-run` |

---

### Sprint 6.3 — Item 16: Pre-run Configuration Validation (Extended) (2026-03-17)

**Branch:** `feature/extended-validation`
**Issue:** #19
**Tests:** 378 passing, 83% coverage (14 new in `tests/test_extended_validation.py`)

| Step | File | Change |
| ---- | ---- | ------ |
| 2 | `pace/config_tester.py` | `_validate_plan_files()` — for each active/completed release with a `plan_file`, checks file exists, parses as valid YAML, and contains `release` + `stories`/`days` keys |
| 4 | `pace/config_tester.py` | `--strict` CLI flag — promotes all warnings to errors (exit code 2); suitable for CI preflight gates |
| 5 | `pace/config_tester.py` | `--release <name>` CLI flag — restricts `_validate_plan_files()` to the named release only |
| 6 | `.github/workflows/pace.yml` | Added `--strict` to `python pace/config_tester.py` step |
| 6 | `.gitlab-ci.yml` | Added `--strict` to `python pace/config_tester.py` step |
| 6 | `Jenkinsfile` | Added `--strict` to `sh 'python pace/config_tester.py'` step |
| 6 | `bitbucket-pipelines.yml` | Added `--strict` to `python pace/config_tester.py` step |

*Note: Step 1 (`_validate_releases`) and Step 3 (`_validate_cross_fields`) were already delivered by Item 14.*

*ROADMAP Execution Log v2.7 — 2026-03-17 IST (Sprint 6.3 Items 12–16 documented)*
*Author: Vipul Meehnia*
