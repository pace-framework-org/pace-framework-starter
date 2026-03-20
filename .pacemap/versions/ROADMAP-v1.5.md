# PACE Framework — Product Roadmap

**Author:** Vipuul Meehniaa
**Date:** 2026-03-13:19:09 (IST — Asia/Kolkata)
**Roadmap Version:** 1.6 (revised 2026-03-20 IST — Phase 7 added: Items 19–26;
DOCS-ROADMAP.md created)
**PACE Framework Baseline:** v3.0.0
**Target Release:** PACE v3.3

> **How to read this document:**
> Each item carries an `@Since <version>` tag indicating the target PACE release.
> Steps marked **[DEFERRED]** were descoped from the initial implementation and are tracked in
> [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md) under the item's *Variations from Plan* section.

---

## Overview

This roadmap covers ten strategic improvements to the PACE framework, each assessed for impact, complexity, and delivery sequencing. Items are grouped into four execution phases based on dependency order and effort. Each item includes an Assessment (current state and problem), a Recommendation (proposed solution), and an Execution Plan (concrete deliverables and acceptance criteria).

---

## Execution Phases at a Glance

| Phase | Theme | Items | Target |
| ----- | ----- | ----- | ------ |
| 1 | Foundation | Branching Model, PACE Planner, Config Tester | v2.0-alpha |
| 2 | Intelligence & Efficiency | Context Versioning, Auto-Update, Cron Management | v2.0-beta |
| 3 | Integration & Ecosystem | Comms & Alerts, Tracker Artifacts, CI/CD Pipelines | v2.0-rc |
| 4 | Extensibility | Plugin System | v2.1 |
| 5 | Training Data Pipeline | Training Collector, Exporter, Hook | v2.2 |
| 6 | Architecture Maturity | Context Versioning, Auto-Refresh, Multi-Release, plan.yaml v3, Validation, Pacemap, CHANGELOG | v3.0 |
| 7 | Context Intelligence & FORGE Efficiency | Planner Context Refresh, Human-Gate Context Refresh, Stale Read Eviction, Test Dedup, Write Suppression, Haiku Compression, Pre-seeded File Map, Forked Subcontext | v3.1–v3.3 |

---

## Phase 1 — Foundation

### Item 1: Sprint/Release Branching Model

> **@Since** `v2.0-alpha` &nbsp;·&nbsp; **PR:** #2 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-1--sprintrelease-branching-model)

#### Assessment

The current model treats the `pace/sprint-N` branch as the primary delivery unit, but this conflates a sprint (a short time-box) with a release (a shippable increment). In real AGILE practice, multiple sprints compose a release. The current flat branch structure prevents PACE from reasoning about long-horizon deliverables and forces every sprint into an implicit full release cycle.

#### Recommendation

Redefine the delivery hierarchy as follows:

```text
main
└── staging
    └── release/<release-name>          # e.g. release/v2.0
        ├── rel/sprint/pace-1
        ├── rel/sprint/pace-2
        └── rel/sprint/pace-N           # last day of sprint → mandatory merge to release/<name>
```

- A **release** encapsulates all work for a named version (e.g. `v2.0`, `q1-2026`).
- A **sprint** is a time-boxed sub-unit of a release: minimum 1 day, maximum `release_days` (configurable).
- PACE creates all branches if they do not exist before beginning work.
- On the last day of each sprint, PACE opens a PR from `rel/sprint/pace-N` → `release/<release-name>` and waits for approval before the next sprint begins.
- When all sprints in a release are merged, PACE opens a PR from `release/<release-name>` → `staging`. After staging validation passes (CI, integration tests, smoke tests), PACE opens the final PR from `staging` → `main`, completing the release.
- The full promotion chain is therefore: `rel/sprint/pace-N` → `release/<name>` → `staging` → `main`, with a PR gate at every level.

#### Execution Plan

1. Add `release` section to `pace.config.yaml`:

   ```yaml
   release:
     name: "v2.0"
     release_days: 90       # total calendar days in the release
     sprint_days: 7         # days per sprint (1–release_days)
   ```

2. Update `orchestrator.py`: detect current sprint number from git branch history; create branch hierarchy if absent.
3. Add `BranchingAdapter` to `platforms/` with implementations for GitHub, GitLab, Bitbucket.
4. Implement end-of-sprint merge PR creation in CONDUIT (`rel/sprint/pace-N` → `release/<name>`).
5. **[DEFERRED → Phase 3]** CONDUIT: after all sprint PRs are merged to `release/<name>`, open a PR to `staging`. Monitor the staging CI run; once it passes, open the final PR from `staging` → `main`. If staging CI fails, open a HOLD issue and set `PACE_PAUSED=true`.
6. **[DEFERRED → Phase 3]** Add branch-protection checks to `preflight.py` — abort if `main` or `staging` protection rules are missing.
7. Acceptance: (a) PACE creates the full `main → staging → release/v2.0 → rel/sprint/pace-1` hierarchy on first run; (b) end-of-sprint PR is opened to `release/v2.0`; (c) after all sprints merge, a PR to `staging` is opened; (d) once staging CI passes, the final PR to `main` is opened automatically.

> **Scope note (v2.0-alpha implementation):** Steps 5–6 were deferred to Phase 3. GitLab and Bitbucket branching adapters in step 3 are interface stubs (fall back to `LocalBranchingAdapter`); only GitHub is fully implemented. See [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-1--sprintrelease-branching-model) → *Variations from Plan*.

---

### Item 2: PACE Planner Pipeline

> **@Since** `v2.0-alpha` &nbsp;·&nbsp; **PR:** #3 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-2--pace-planner-pipeline)

#### Assessment

Day-0 planning is currently baked into the orchestrator as a one-time initialization step. There is no way to re-plan mid-release without manually editing `plan.yaml` and potentially breaking sprint accounting. Re-budgeting after scope changes is entirely manual. The absence of an approval gate means a broken plan can silently propagate into sprint execution.

#### Recommendation

Extract Day-0 into a standalone, re-runnable **pace-planner** pipeline:

- `pace-planner` runs independently of the main PACE cron.
- On first run: produces the initial `plan.yaml` + budget, commits shipped items, opens a plan-approval PR.
- On re-run (triggered manually or by context update): diffs against current `plan.yaml`, identifies already-SHIPPED items, regenerates plan for remaining scope, opens a re-plan PR.
- Execution of PACE sprints is **blocked** (`PACE_PAUSED=true`) until the plan-approval PR is merged.
- Budget and AC counts are re-estimated by PRIME on each planner run.

#### Execution Plan

1. Extract planning logic from `orchestrator.py` into `planner.py` (already exists as a stub — flesh it out).
2. Add `pace-planner.yml` CI workflow alongside `pace.yml`.
3. **[DEFERRED → Phase 3]** PRIME agent: add `plan_mode` flag that returns a structured re-plan diff (new stories, removed stories, scope changes) rather than directly writing `plan.yaml`.
4. CONDUIT: create plan-approval PR; set `PACE_PAUSED=true` as a CI/CD variable; unset after merge.
5. **[DEFERRED → Phase 3]** SCRIBE: generate a human-readable planning report summarising budget impact and scope delta when re-planning.
6. `planner.py`: serialize shipped stories to a `shipped.yaml` manifest; never re-plan shipped items.
7. Acceptance: re-running `pace-planner` after two stories are SHIPPED produces a PR that excludes those stories and shows updated cost projection.

> **Scope note (v2.0-alpha implementation):** Steps 3 and 5 (PRIME plan_mode, SCRIBE report) were deferred. Step 4 variation: CONDUIT was not modified; `planner.py --pipeline` calls `ci.set_variable()` directly. See [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-2--pace-planner-pipeline) → *Variations from Plan*.

---

### Item 9: Configuration Tester

> **@Since** `v2.0-alpha` &nbsp;·&nbsp; **Direct commit** `75f25b0` &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-9--configuration-tester)

#### Assessment

`pace.config.yaml` is the single most critical file in a PACE setup. Misconfiguration (wrong model IDs, missing `github_org`, non-semantic sprint/release day values, cost thresholds that are too low for the model in use) silently degrades or breaks the entire pipeline. Currently there is no validation beyond Python `KeyError`s at runtime.

#### Recommendation

Build a `pace-config-test` CLI command and CI step that validates `pace.config.yaml` before any agent is invoked:

- **Hard errors**: missing required fields, invalid provider/model IDs, unreachable `docs_dir`.
- **Warnings**: `sprint_days > release_days`, `max_story_cost_usd` lower than the cheapest model call (~$0.01), `analysis_model` set to an opus-class model (unnecessarily expensive for analysis tasks).
- **Suggestions**: fields not set that have useful non-default options (e.g. `reporter.timezone`, `forge.max_iterations`).
- Output is human-readable on CLI and JSON-serializable for CI integration.

#### Execution Plan

1. Create `pace/config_tester.py` with a `ConfigTestResult` dataclass (errors, warnings, suggestions).
2. Implement validators for each top-level config section (product, sprint, release, source, tech, platform, llm, forge, cost_control, advisory, reporter, cron).
3. Add known-valid model ID list (sync with Anthropic and LiteLLM release notes quarterly).
4. Expose as `python pace/config_tester.py` CLI; exit code 0 = clean, 1 = warnings, 2 = errors.
5. Add `pace-config-test` as the first step in both `pace.yml` and `pace-planner.yml`.
6. Acceptance: a config with `sprint_days: 200` and `release_days: 90` exits with code 1 and prints a warning; a config with no `llm.model` exits with code 2.

---

## Phase 2 — Intelligence & Efficiency

### Item 3: Context Versioning & Token Management

> **@Since** `v2.0-beta` &nbsp;·&nbsp; **PR:** #4 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-3--context-versioning--token-management)

#### Assessment

PACE currently has no systematic approach to managing the total token context across multi-day sprints. Each agent call starts fresh except for FORGE's new checkpoint (added in v1.2). Story files, handoff YAML, and plan data grow unbounded. There is no versioning of the planning context, so drift between `plan.yaml` and `.pace/day-N/story.md` is invisible.

#### Recommendation

Implement three complementary mechanisms:

1. **Context versioning**: every write to `plan.yaml` or `pace.config.yaml` increments a `context_version` field (semver patch bump). Agents log the context version they operated under. Divergence between the version at plan time and at execution time triggers a re-plan warning.

2. **Context compaction**: before each PRIME/GATE/SENTINEL call, `orchestrator.py` compacts the context by summarizing completed-sprint stories into a brief `shipped_summary.md` rather than passing full story text. Full story text is only passed for the current sprint.

3. **Token budget enforcement**: each agent call records `input_tokens + output_tokens` in `spend_tracker.py`. If a single agent call exceeds a configurable `max_call_tokens` threshold, it is retried with a compacted prompt. Running totals are emitted in SCRIBE's daily report.

#### Execution Plan

1. Add `context_version: "1.0.0"` to `plan.yaml` schema; bump on every planner write.
2. `orchestrator.py`: build `shipped_summary.md` at start of each day from `.pace/day-*/handoff.yaml` files where `status == SHIPPED`.
3. **[PARTIAL]** Pass `shipped_summary.md` content instead of full story files to PRIME, GATE, SENTINEL. (File is written to `.pace/context/`; individual agent call sites not yet modified to substitute it.)
4. Add `llm.limits` to `pace.config.yaml`. Defaults are set per agent class, not globally, because coding agents require far larger context windows than analysis agents:

   ```yaml
   llm:
     limits:
       forge_input_tokens: 160000    # FORGE + SCRIBE: system prompt (~4k) + tool defs (~5k)
                                     # + file contents (up to ~80k) + multi-iteration history
       forge_output_tokens: 16384    # FORGE writes complete files; prevents truncation mid-impl
       analysis_input_tokens: 80000  # PRIME/GATE/SENTINEL/CONDUIT: story context, not codebases
       analysis_output_tokens: 8192  # structured analysis responses are shorter
   ```

   Note: 32k input is dangerously low for FORGE on any non-trivial codebase. A single file read + conversation history routinely exceeds that in iteration 10+.
5. `spend_tracker.py`: expose `session_total()` and `call_exceeds_limit(agent_class, input, output)` helpers (agent class determines which limit applies).
6. **[DEFERRED → Phase 3]** Per-call retry with compacted prompt when `call_exceeds_limit()` returns true.
7. Acceptance: a 30-day sprint with 20 shipped stories passes PRIME a summary of ≤500 tokens for those stories rather than full text.

> **Scope note (v2.0-beta implementation):** Step 3 is partial (file written, no agent call-site changes). Step 6 (retry loop) deferred. See [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-3--context-versioning--token-management) → *Variations from Plan*.

---

### Item 4: Auto-Update Mechanism

> **@Since** `v2.0-beta` &nbsp;·&nbsp; **PR:** #5 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-4--auto-update-mechanism)

#### Assessment

PACE is pinned at whatever version was installed at setup time. Bug fixes, new platform support, and agent improvements are only available after a manual `git pull` or re-installation. There is no mechanism to notify users of new versions or to self-update safely.

#### Recommendation

Add a daily version-check with customization-aware update behaviour:

- Once per calendar day, at the start of any PACE pipeline run, query the `pace-framework-starter` GitHub releases API for the latest tag.
- Compare against the installed `PACE_VERSION` constant in `config.py`.
- Before any update, **detect whether PACE core files have local modifications** (git diff against the installed tag). Projects routinely customize `forge.py`, `orchestrator.py`, and `config.py` for their specific needs. Silently overwriting these customizations would be destructive.
- **If no customizations are detected** and a newer version exists: apply the update automatically (lockfile guard still applies).
- **If customizations are detected**: skip the update entirely and emit a prominent WARNING at every pipeline run until resolved:

  ```text
  ⚠  PACE v{new_version} is available (installed: v{current_version}).
     Auto-update skipped — customized PACE files detected:
       - pace/agents/forge.py
       - pace/orchestrator.py
     Run the manual upgrade tutorial to merge new version features
     while preserving your customizations. See:
     tutorials/updating-customised-pace
  ```

- The warning is suppressed with `updates.suppress_warning: true` in `pace.config.yaml`.
- `updates.auto_update: false` disables version checking entirely.

#### Execution Plan

1. Add `pace/updater.py` with `check_for_update()`, `detect_customizations()`, and `apply_update()`.
2. `check_for_update()`: hits the GitHub releases API; caches result to `.pace/update_check.json` with a TTL of 23 hours.
3. `detect_customizations()`: runs `git diff <installed_tag> -- pace/` and returns a list of modified PACE core files. Any non-empty list blocks auto-update.
4. `apply_update()`: only called when `detect_customizations()` returns empty; git-fetches the new tag; runs `pip install -r requirements.txt -q`; writes the new version to `.pace/update_check.json`.
5. Add pipeline lock: `.pace/pipeline.lock` created at pipeline start, deleted at pipeline end; `apply_update()` aborts if lock exists.
6. `preflight.py`: call `check_for_update()` and `detect_customizations()` at startup; emit WARNING block if newer version available but customizations block update.
7. **[DEFERRED → Phase 3]** CONDUIT: include version-update summary in daily report if an update was applied; include deferred-update warning if customizations block it.
8. Reference the upgrade tutorial (`tutorials/updating-customised-pace` in pace-docs) in all WARNING output.
9. Acceptance: (a) with no customizations, a version bump triggers auto-update; (b) with a modified `forge.py`, update is skipped and WARNING lists the file; (c) `updates.suppress_warning: true` silences the WARNING without disabling version checking.

> **Scope note (v2.0-beta implementation):** Step 7 (CONDUIT report) deferred. Step 8 tutorial URL is a placeholder (`pace-docs.example.com`) — the docs page does not yet exist. Two post-PR code quality fixes applied (unreachable `else`, silent `except`). Branch required rebase onto `main` after Phase 1 landed. See [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-4--auto-update-mechanism) → *Variations from Plan*.

---

### Item 8: Cron Configuration

> **@Since** `v2.0-beta` &nbsp;·&nbsp; **PR:** #6 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-8--cron-configuration)

#### Assessment

Cron schedules for PACE pipelines are currently hardcoded in CI YAML files, requiring manual edits to change frequency. There is no concurrency guard in the framework itself — if a pipeline run takes longer than the cron interval, a second run starts while the first is still in progress, causing race conditions on `.pace/` state files.

#### Recommendation

Centralize cron configuration in `pace.config.yaml` and add a framework-level execution lock:

```yaml
cron:
  pace_pipeline: "0 6 * * 1-5"     # main PACE run (UTC)
  planner_pipeline: "0 7 * * 0"    # weekly re-plan (Sunday)
  update_check: "0 0 * * *"        # daily update check (midnight)
  timezone: "UTC"
```

The CI pipeline generators (GitHub, GitLab, Jenkins) read `cron` from `pace.config.yaml` and regenerate the workflow files when the config changes. A `pipeline.lock` file prevents concurrent runs.

#### Execution Plan

1. Add `cron` section to `pace.config.yaml` schema and `config.py` dataclasses.
2. Add `pace/ci_generator.py`: reads `cron` config and regenerates `.github/workflows/pace.yml` (or `.gitlab-ci.yml`, `Jenkinsfile`) cron triggers.
3. `preflight.py`: acquire `.pace/pipeline.lock` (write PID + timestamp); fail immediately if lock is stale (> 4 hours old, configurable).
4. `orchestrator.py` `finally` block: always release the lock.
5. **[DEFERRED → Phase 2 follow-up]** Add `python pace/ci_generator.py` to `pace-config-test` output as a suggestion if cron fields differ from workflow file.
6. Acceptance: changing `cron.pace_pipeline` in config and running `ci_generator.py` updates the `schedule.cron` field in the generated workflow YAML.

> **Scope note (v2.0-beta implementation):** Step 5 (config_tester cross-wire) deferred. Default cron schedules changed from the values in this plan: `pace_pipeline` is `0 9 * * 1-5` (09:00 UTC, not 06:00); `planner_pipeline` is `0 8 * * 1` (Monday, not Sunday). Branch required rebase onto `main` after Phase 1 landed. See [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-8--cron-configuration) → *Variations from Plan*.

---

## Phase 3 — Integration & Ecosystem

### Item 5: Communication & Alerting

> **@Since** `v2.0-rc` &nbsp;·&nbsp; **PR:** #7 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-5--communications--alerting)

#### Assessment

PACE currently has no outbound communication. Failures, HOLD issues, SHIPPED stories, and daily reports exist only inside GitHub Issues and CI logs. Teams using Slack, Microsoft Teams, or email have no automated way to receive PACE status updates. There is no alerting system for cost overruns, repeated failures, or long-running pipelines.

#### Recommendation

Introduce a `NotificationAdapter` interface alongside the existing platform adapters, with implementations for Slack, Microsoft Teams, and email (SMTP). Pair it with a configurable alert rule engine:

```yaml
notifications:
  slack:
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#eng-pace"
  teams:
    webhook_url: "${TEAMS_WEBHOOK_URL}"
  email:
    smtp_host: "smtp.example.com"
    smtp_port: 587
    from: "pace@example.com"
    to: ["team@example.com"]

alerts:
  - event: hold_opened
    channels: [slack, email]
  - event: story_shipped
    channels: [slack]
  - event: cost_exceeded
    threshold_usd: 5.00
    channels: [slack, email]
  - event: pipeline_duration_exceeded
    threshold_minutes: 60
    channels: [teams]
  - event: update_available
    channels: [slack]
```

#### Execution Plan

1. Define `NotificationAdapter` ABC in `pace/notifications/base.py` with `send(event, payload)`.
2. Implement `SlackAdapter`, `TeamsAdapter`, `EmailAdapter` in `pace/notifications/`.
3. Add `pace/alert_engine.py`: evaluates alert rules against events; dispatches to configured channels.
4. Wire alert engine into `orchestrator.py` at key lifecycle points: HOLD opened, story SHIPPED, spend threshold exceeded, pipeline lock timeout.
5. Add `notifications` and `alerts` sections to `pace.config.yaml` schema and `config.py`.
6. `config_tester.py`: validate webhook URLs are non-empty if adapter is configured; warn if no channels are configured (PACE runs silently).
7. Acceptance: a simulated HOLD event with Slack configured sends a POST to the webhook URL containing the story title, day number, and hold reason.

---

### Item 6: Tracker Artifact Push & Issue Templates

> **@Since** `v2.0-rc` &nbsp;·&nbsp; **PR:** #8 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-6--tracker-artifact-push)

#### Assessment

All PACE artifacts — stories, test plans, handoff data, advisory findings — currently live exclusively in the `.pace/day-N/` directory tree. The configured issue tracker (`tracker_type`) is only used to open HOLD issues; it is never used to push structured story or test artifacts. Teams cannot use their tracker's native search, filtering, or reporting on PACE-generated content.

#### Recommendation

Extend `TrackingAdapter` to push artifacts as tracker items:

- Stories become tracker issues/tickets with structured labels (e.g. `pace:story`, `pace:day-N`, `pace:sprint-M`).
- Acceptance criteria are embedded as a formatted markdown checklist **within the issue body/description**, not as separate sub-tasks or checklist items outside the description. This keeps ACs visible in the issue preview without requiring sub-issue support from the tracker.
- Handoff data (test results, coverage, notes) is posted as a comment on story close.
- Advisory findings can optionally create separate issues (already gated by `advisory.push_to_issues`).
- Custom issue templates for GitHub and GitLab are generated from PACE's story schema.

#### Execution Plan

1. Extend `TrackingAdapter` ABC with `push_story(story)`, `update_story_status(story_id, status)`, `post_handoff_comment(story_id, handoff)`. The `push_story` method constructs the full issue body including story description + a `## Acceptance Criteria` section with `- [ ] AC text` lines. No separate `push_ac` method — ACs are part of the description payload.
2. Implement in `platforms/github.py`, `platforms/gitlab.py`, `platforms/jira.py`.
3. Generate GitHub issue templates (`.github/ISSUE_TEMPLATE/pace_story.yml`) and GitLab equivalents during `pace-planner` run.
4. Add `tracker.push_stories: true` option to `pace.config.yaml` (default: false to preserve existing behavior).
5. CONDUIT: on story SHIPPED, call `update_story_status` and `post_handoff_comment`.
6. Acceptance: with `tracker.push_stories: true` and GitHub configured, a new story creates a GitHub Issue whose **description body** contains a `## Acceptance Criteria` section with all AC items as `- [ ]` checkboxes; closing the story posts a handoff comment.

---

### Item 7: GitLab, Jenkins, and Bitbucket Pipeline Finalization

> **@Since** `v2.0-rc` &nbsp;·&nbsp; **PR:** #10 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-7--gitlab-jenkins-and-bitbucket-pipeline-finalization)

#### Assessment

`platforms/gitlab.py`, `platforms/jenkins.py`, and `platforms/bitbucket.py` exist but are incomplete stubs. The `ci_generator.py` proposed in Item 8 does not yet have templates for these platforms. Users who prefer GitLab CI or Jenkins cannot use PACE without significant manual work.

#### Recommendation

Finalize pipeline templates and platform adapter implementations for GitLab, Jenkins, and Bitbucket so that a correctly configured `pace.config.yaml` is sufficient to run PACE on any of the four supported platforms.

#### Execution Plan

1. **GitLab CI**: Create `.gitlab-ci.yml` template with PACE stages (`plan`, `forge`, `gate`, `sentinel`, `conduit`); use GitLab CI/CD variables for secrets; implement `gitlab.py` variable management (`set_variable`, `get_variable`).
2. **Jenkins**: Create `Jenkinsfile` (declarative pipeline) with equivalent stages; use Jenkins Credentials for secrets; implement `jenkins.py` using Jenkins REST API for variable management.
3. **Bitbucket Pipelines**: Create `bitbucket-pipelines.yml` template; implement `bitbucket.py` using Bitbucket repository variables API.
4. `ci_generator.py` (from Item 8): generate the correct CI file based on `platform.ci` in config.
5. Add integration test fixtures for each platform adapter (mock API responses).
6. Document each platform's required secrets/variables in `pace.config.yaml` comments and `config_tester.py` validation.
7. Acceptance: a `pace.config.yaml` with `platform.ci: gitlab` generates a valid `.gitlab-ci.yml` that passes `gitlab-ci-lint` validation.

---

## Phase 4 — Extensibility

### Item 10: Plugin System

> **@Since** `v2.1` &nbsp;·&nbsp; **PR:** #11 &nbsp;·&nbsp; **Status:** Merged
> Variations from plan tracked in [ROADMAP-EXECUTION-LOG.md](ROADMAP-EXECUTION-LOG.md#item-10--plugin-system)

#### Assessment

PACE's agent pipeline is tightly coupled. Adding a new agent, a custom tool, or a domain-specific workflow requires modifying core framework files. This prevents teams from extending PACE without forking the repository. As the ecosystem grows, a plugin system becomes essential for community contributions.

#### Recommendation

Introduce a lightweight plugin system using Python entry points and a plugin manifest convention:

- Plugins are Python packages installed alongside PACE that register themselves via `pyproject.toml` entry points under the `pace.plugins` group.
- Plugin types:
  - `agent` — adds a new agent to the pipeline
  - `tool` — adds a tool to FORGE/SCRIBE's tool registry
  - `adapter` — adds a new LLM/platform/notification adapter
  - `hook` — runs at a pipeline lifecycle event without modifying agent behavior
  - `webhook-in` — exposes an HTTP listener that external services can POST to, triggering PACE actions (re-plan, block/unblock story, inject context). Useful for Zapier, n8n, or CI event bridges.
  - `webhook-out` — posts a JSON payload to a configured URL on lifecycle events; simpler than a full `NotificationAdapter` for teams wanting raw event data without a named integration.
- PACE loads plugins at startup, validates their manifest, and makes them available to the orchestrator.

#### Initial Plugin Candidates

| Plugin | Type | Description |
| ------ | ---- | ----------- |
| `pace-plugin-sonarqube` | adapter | Push coverage and advisory data to SonarQube |
| `pace-plugin-linear` | adapter | TrackingAdapter for Linear issue tracker |
| `pace-plugin-notion` | adapter | Push sprint reports to Notion databases |
| `pace-plugin-openai` | adapter | LLMAdapter wrapping OpenAI API (via LiteLLM) |
| `pace-plugin-security` | agent | SAST/DAST scan agent inserted between GATE and SENTINEL |
| `pace-plugin-docs-gen` | hook | Auto-generates Markdown API docs from code on SHIPPED |
| `pace-plugin-pagerduty` | adapter | NotificationAdapter for PagerDuty incident routing |
| `pace-plugin-cost-forecast` | hook | Projects end-of-sprint cost from day-N spend at CONDUIT |
| `pace-plugin-webhook-in` | webhook-in | HTTP listener for external triggers (CI events, Zapier, n8n, manual unblocks) |
| `pace-plugin-webhook-out` | webhook-out | Posts structured JSON to arbitrary URLs on PACE lifecycle events |

#### Execution Plan

1. Define `PluginManifest` dataclass and `PluginBase` ABC in `pace/plugins/base.py`.
2. Implement plugin loader in `pace/plugins/loader.py` using `importlib.metadata.entry_points`.
3. Define entry point groups: `pace.plugins.agents`, `pace.plugins.tools`, `pace.plugins.adapters`, `pace.plugins.hooks`, `pace.plugins.webhooks_in`, `pace.plugins.webhooks_out`.
4. For `webhook-in` plugins: define a `WebhookInBase` ABC with `handle(event_type, payload)`. The framework starts a lightweight HTTP server (default port 9876, configurable) at pipeline startup if any webhook-in plugins are registered.
5. For `webhook-out` plugins: define a `WebhookOutBase` ABC with `on_event(event, payload)`. Plugins register which events they subscribe to in their manifest.
6. Update `orchestrator.py` to call `loader.load_all()` at startup and inject plugins into agent/tool registries.
7. Create `pace-plugin-template` repository with a working example plugin (a minimal `hook` that logs lifecycle events).
8. Document the plugin development guide (plugin manifest format, available hooks, webhook contracts, testing conventions).
9. `config_tester.py`: detect installed plugins; warn if a plugin's declared PACE version range is incompatible with the running framework version.
10. Acceptance: installing `pace-plugin-template` and adding it to `pace.config.yaml` under `plugins:` causes its hook to fire during the next pipeline run without any core framework change; a `webhook-out` plugin receives a POST with the correct JSON payload on a HOLD event.

---

---

## Phase 6 — Architecture Maturity (`@Since v3.0`)

Phase 6 addresses structural gaps that became apparent after operating PACE v2.0 at scale. The items in this phase are breaking changes to core data models and directory conventions. They must be delivered together as a coordinated release to avoid a partial migration state.

---

### Item 12: Release-Scoped Context Directory Versioning

> **@Since** `v3.0` &nbsp;·&nbsp; **Status:** Merged — PR #TBD (2026-03-17)

#### Assessment

`.pace/context/` files (`product.md`, `engineering.md`, `security.md`, `devops.md`, `shipped_summary.md`) are regenerated in-place on every planner run. There is no record of what context a prior release operated under, making it impossible to audit or reproduce a completed release's agent behaviour. When a new release begins, the prior context is silently overwritten.

#### Recommendation

Version context files by release:

- On first run of a new release, if context files from a prior release exist, rename them: `product.md` → `product.<release-name>.md` (e.g. `product.v2.0.md`). The archived files remain in `.pace/context/` as a read-only audit trail.
- New context files for the current release are written fresh (SCRIBE re-runs from the current source docs).
- A `context.manifest.yaml` in `.pace/context/` records which release each file was generated for, the source doc hashes used, and the generation timestamp.

#### Execution Plan

1. Add `context.manifest.yaml` schema to `schemas.py`: `release`, `generated_at`, `source_hashes` (SHA-256 of each source doc), `files` list.
2. `preflight.py`: before calling SCRIBE, check `context.manifest.yaml`. If release name differs from the current release, archive existing context files with `.{release-name}.md` suffix and delete the originals so SCRIBE generates fresh copies.
3. `scribe.py`: after generating context files, write `context.manifest.yaml` with current release, timestamp, and SHA-256 hashes of `PRD.md`, `SRS.md`, and any other source docs.
4. Add migration script `pace/migrations/v3_context_versioning.py` that retroactively archives any unversioned context files as `*.pre-v3.md`.
5. `config_tester.py`: warn if `.pace/context/` contains files with no matching `context.manifest.yaml` entry (suggests a manual edit bypassed the versioning system).
6. Acceptance: after completing release `v2.0` and starting release `v2.1`, `.pace/context/` contains `product.v2.0.md` (archived) and a fresh `product.md` generated from current source docs; `context.manifest.yaml` reflects `v2.1` as the current release.

---

### Item 13: Context Auto-Refresh on Document Updates

> **@Since** `v3.0` &nbsp;·&nbsp; **Status:** Merged — PR #TBD (2026-03-17)

#### Assessment

SCRIBE only generates context files when they are *missing* — there is no mechanism to detect that `PRD.md` or `SRS.md` has changed and re-generate the context. When a product owner uploads a revised PRD mid-release, agents continue operating on stale context until context files are manually deleted. This creates invisible drift between product intent and agent understanding.

#### Recommendation

Wire source-document change detection into the preflight and planner workflows:

- At the start of every pipeline run, `preflight.py` compares the SHA-256 hashes of source docs against the hashes recorded in `context.manifest.yaml`. A mismatch means source docs have changed.
- **Same-release update**: archive the current context files (with current release name suffix), regenerate via SCRIBE, and emit a prominent `[Context Refreshed]` notice in the pipeline log.
- **Cross-release update**: this case is already handled by Item 12 (new release = new context).
- A new CLI command `python pace/preflight.py --refresh-context` forces regeneration unconditionally, bypassing the hash check.

#### Execution Plan

1. `preflight.py`: add `_check_context_freshness()` — reads `context.manifest.yaml`, computes current source doc hashes, returns list of changed docs. If non-empty, log changed files and call `_archive_context()` + trigger SCRIBE.
2. `_archive_context()`: moves existing context files to `*.{release-name}.{iso-date}.md` to distinguish multiple same-release refreshes (e.g. `product.v2.0.2026-03-16.md`).
3. Add `--refresh-context` flag to `preflight.py` CLI to force regeneration.
4. `planner.py --replan`: also calls `_check_context_freshness()` before generating a new plan, so a revised PRD is reflected in the re-plan.
5. `config_tester.py`: validate that source doc paths configured in `pace.config.yaml` actually exist; warn if no source docs are configured (SCRIBE will generate empty context).
6. Acceptance: modifying `PRD.md` and running the pipeline regenerates `product.md`, archives the old version with an ISO-date suffix, and logs `[Context Refreshed] PRD.md changed since last run`.

---

### Item 14: Multi-Release Configuration

> **@Since** `v3.0` &nbsp;·&nbsp; **Status:** Merged — PR #TBD (2026-03-17)

#### Assessment

`pace.config.yaml` currently supports a single `release:` section — one name, one `release_days`, one `sprint_days`. Teams working on overlapping releases (e.g. `v2.0` still in QA while `v2.1` is in active development) cannot model this in PACE. Starting a new release requires manually editing the config and risks overwriting the prior release's plan.

#### Recommendation

Replace the single `release:` key with a `releases:` list. Each entry is self-contained and uniquely named:

```yaml
releases:
  - name: "v2.0"
    release_days: 90
    sprint_days: 14
    plan_file: ".pace/releases/v2.0/plan.yaml"
    status: "completed"            # completed | active | planned
  - name: "v2.1"
    release_days: 60
    sprint_days: 7
    plan_file: ".pace/releases/v2.1/plan.yaml"
    status: "active"
```

Constraints:

- `sprint_days` must be ≤ `release_days`. Violation is a hard config error.
- `name` must be unique across all releases in the list. Duplicate names are a hard config error.
- Exactly one release may have `status: active` at any time. Zero or two-or-more active releases are a hard config error.
- The active release drives all branching, planning, and agent operations.
- `PACE_RELEASE=v2.1` environment variable overrides which release is treated as active (for manual override or CI parameterization).

#### Execution Plan

1. Add `ReleaseConfig` dataclass to `config.py`: `name: str`, `release_days: int`, `sprint_days: int`, `plan_file: str`, `status: Literal["active", "completed", "planned"]`.
2. Update `PaceConfig`: replace `release: ReleaseConfig` with `releases: list[ReleaseConfig]`; add `active_release` property that returns the single active entry (or raises if none/multiple).
3. `config_tester.py`: add `_validate_releases()` — check uniqueness of names, `sprint_days ≤ release_days`, exactly one `status: active`.
4. Update all `orchestrator.py`, `planner.py`, `branching.py`, `ci_generator.py` references from `cfg.release` to `cfg.active_release`.
5. `branching.py` `ensure_hierarchy()`: use `cfg.active_release.name` and derive sprint number from `cfg.active_release.sprint_days`.
6. Add migration helper `pace/migrations/v3_multi_release.py` that reads the legacy `release:` key and rewrites it as a single-entry `releases:` list with `status: active`.
7. Acceptance: a config with two releases (`v2.0` completed, `v2.1` active) starts the pipeline on `v2.1`'s plan file and creates a `release/v2.1` branch; setting `PACE_RELEASE=v2.0` switches to the completed release without modifying the config file.

---

### Item 15: plan.yaml Versioning & Story Naming

> **@Since** `v3.0` &nbsp;·&nbsp; **Status:** Merged — PR #28 (2026-03-17)

#### Assessment

`plan.yaml` uses `day-N` as the primary key for work units. This conflates calendar day with story identity — if a story slips or is re-ordered, the key becomes misleading. There is no backup mechanism before modifications, so a failed re-plan can corrupt the only copy of the plan. Completion status is tracked implicitly by checking for a `handoff.yaml` artifact rather than being stored on the plan entry itself.

#### Recommendation

Rename `day-N` keys to `story-N`. Store explicit completion status on each story entry. Before every write operation on `plan.yaml`, create a timestamped backup. On re-plan, preserve all completed stories unchanged and only rewrite the stories after the last completed story.

New `plan.yaml` schema (per release):

```yaml
release: "v2.1"
context_version: "1.0.0"
stories:
  - id: story-1
    title: "Bootstrap project scaffolding"
    status: shipped          # pending | in_progress | shipped | hold
    shipped_at: "2026-03-10"
  - id: story-2
    title: "Implement authentication"
    status: shipped
    shipped_at: "2026-03-11"
  - id: story-3
    title: "Add OAuth2 provider support"
    status: pending
```

Re-plan contract:

- Stories with `status: shipped` are immutable — never regenerated or reordered.
- The last `shipped` story forms a boundary; only stories after it may be rewritten.
- Before any modification, `plan.yaml` is copied to `.pace/releases/<release>/plan.yaml.bak.<iso-datetime>`.
- Backup files older than 30 days are automatically pruned (configurable via `planner.backup_retention_days`).

#### Execution Plan

1. Update `plan.yaml` schema in `schemas.py`: `release` field, `stories` list with `id`, `title`, `status`, `shipped_at` (nullable).
2. `planner.py`: add `_backup_plan()` — writes `plan.yaml.bak.<iso-datetime>` before any write; add `_get_replan_boundary()` — returns index of last shipped story.
3. `planner.py` re-plan path: load existing plan, extract shipped stories, regenerate only the pending/in_progress slice starting after the boundary, merge back, call `_backup_plan()`, write.
4. `orchestrator.py`: replace all `day-N` references with `story-N`; update artifact directory naming from `.pace/day-N/` to `.pace/story-N/` (or keep `.pace/day-N/` as a path alias for backwards compatibility with training data collector).
5. `config_tester.py`: add `_validate_plan()` — check that all shipped stories have `shipped_at`; warn on any plan file without a `release` field (suggests pre-v3 plan file).
6. Add migration script `pace/migrations/v3_plan_naming.py` that renames `day-N` keys to `story-N` in existing plan files and adds `status: shipped` to entries that have a corresponding `handoff.yaml`.
7. Acceptance: after two stories are shipped, running the re-plan produces a `plan.yaml.bak.*` file, leaves the two shipped stories unchanged, and rewrites only the remaining stories.

---

### Item 16: Pre-run Configuration Validation (Extended)

> **@Since** `v3.0` &nbsp;·&nbsp; **Status:** Merged — PR #30 (2026-03-18)
> Extends Item 9 (Configuration Tester) with multi-release and cross-field validation.

#### Assessment

Item 9 added `config_tester.py` with per-section validators. With Items 14 and 15 introducing a `releases:` list and per-release `plan_file` paths, a new class of cross-field validation errors becomes possible: duplicate release names, `sprint_days > release_days`, missing plan files for active releases, and `plan.yaml` schema mismatches. These must be caught before any agent runs.

#### Recommendation

Extend `config_tester.py` to cover multi-release constraints and add an explicit `--strict` mode that exits with code 2 on any warning (suitable for CI preflight gates).

#### Execution Plan

1. Add `_validate_releases()` validator to `config_tester.py` (see Item 14, step 3).
2. Add `_validate_plan_files()`: for each release in `releases:`, check that `plan_file` path exists if `status` is `active` or `completed`; check that the file is valid YAML and matches the Item 15 plan schema.
3. Add `_validate_cross_fields()`: confirm `sprint_days ≤ release_days` for every release; confirm no duplicate release names; confirm exactly one `active` release.
4. Add `--strict` CLI flag: treats all warnings as errors (exit code 2).
5. Add `--release <name>` CLI flag: validates only the named release's config and plan file.
6. Update `pace.yml`, `.gitlab-ci.yml`, `Jenkinsfile`, and `bitbucket-pipelines.yml` to pass `--strict` to the config test step.
7. Acceptance: a config with `sprint_days: 20` and `release_days: 10` exits with code 2 (hard error); `--release v2.0` validates only that release's plan file.

---

### Item 17: `.pacemap` Directory

> **@Since** `v3.0` &nbsp;·&nbsp; **Status:** Merged — PR #TBD (2026-03-17)

#### Assessment

`ROADMAP.md` and `ROADMAP-EXECUTION-LOG.md` live in the repository root alongside `README.md`, `setup.cfg`, and other top-level files. As the ROADMAP grows (currently 530 lines, execution log >700 lines), it clutters the root and is not differentiated from other project documentation. There is no versioning or history mechanism for the ROADMAP itself — a wrong edit cannot be easily rolled back.

#### Recommendation

Move roadmap files into a dedicated `.pacemap/` directory. PACE tools automatically commit `.pacemap/` changes with each new roadmap entry, keeping the directory's git history as a timeline of roadmap evolution.

New layout:

```text
.pacemap/
├── ROADMAP.md                  # current roadmap (this file, relocated)
├── ROADMAP-EXECUTION-LOG.md    # execution log (relocated)
└── versions/
    ├── ROADMAP-v1.0.md         # snapshot at each major version
    ├── ROADMAP-v1.1.md
    └── ...
```

Versioning rules:

- On every ROADMAP.md write that changes the **Roadmap Version** header field, `ci_generator.py` snapshots the previous version into `.pacemap/versions/ROADMAP-v<N>.md`.
- Snapshots are immutable — never modified after creation.
- `.pacemap/` is committed by `ci_generator.py` or a dedicated `pace/pacemap.py` helper; the commit message follows the pattern `[pacemap] ROADMAP v<version>: <one-line summary>`.

#### Execution Plan

1. Create `.pacemap/` directory; move `ROADMAP.md` and `ROADMAP-EXECUTION-LOG.md` into it.
2. Add `pace/pacemap.py` with `snapshot_roadmap(version, summary)` — copies current `ROADMAP.md` to `.pacemap/versions/ROADMAP-v<version>.md`; commits `.pacemap/` with a standardized message.
3. Update all internal cross-references in ROADMAP.md, ROADMAP-EXECUTION-LOG.md, and `README.md` to use `.pacemap/ROADMAP.md` paths.
4. `ci_generator.py`: call `pacemap.snapshot_roadmap()` whenever the roadmap version header is updated.
5. `.gitignore`: ensure `.pacemap/` is *not* ignored (it must be committed).
6. Acceptance: updating the Roadmap Version header and running `ci_generator.py` creates a snapshot in `.pacemap/versions/`, commits it, and the new version is the current `ROADMAP.md`; prior version is preserved in `versions/`.

---

### Item 18: CHANGELOG.md

> **@Since** `v3.0` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

There is no `CHANGELOG.md` in the pace-framework-starter repository. Users and adopters have no structured way to understand what changed between framework versions without reading git log or the full ROADMAP execution log. The execution log is authoritative but verbose — it is not suitable as a user-facing change summary.

#### Recommendation

Introduce a `CHANGELOG.md` at the repository root following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions, backed by an auto-update mechanism in `pacemap.py`.

Format per release entry:

```markdown
## [v2.0.0] — 2026-03-15

### Added
- Sprint/release branching hierarchy (Items 1, 7)
- PACE Planner pipeline with re-plan support (Item 2)
- Configuration tester with hard/warning/suggestion levels (Item 9)
- Context versioning and token limits (Item 3)
- Auto-update with customization detection (Item 4)
- Cron configuration and CI generator (Item 8)
- Slack, Teams, and email notifications with alert rules (Item 5)
- Tracker artifact push and GitHub/GitLab issue templates (Item 6)
- Plugin system: hooks, adapters, webhook-in/out (Item 10)
- Training data collector, exporter, and DataExportHook (Item 11)

### Changed
- `plan.yaml` gained `context_version` field
- `spend_tracker.py` gained `install()` no-op shim for orchestrator compatibility

### Fixed
- `spend_tracker.install()` AttributeError on import (orchestrator.py line 58)
```

#### Execution Plan

1. Create `CHANGELOG.md` at repository root; populate with entries for all delivered items (v1.0 through v2.0 baseline, v2.0.0 full feature set).
2. Add `update_changelog(version, added, changed, fixed)` function to `pace/pacemap.py` that inserts a new `## [version]` block at the top of the `### Unreleased` section and moves the previous Unreleased content into the new versioned block.
3. `planner.py`: on planner completion, add a `### Unreleased` entry capturing the new stories planned (story titles, release, sprint range).
4. `orchestrator.py`: on story SHIP, call `pacemap.update_changelog_story_shipped(story_id, release, summary)` to append to the current Unreleased block.
5. `config_tester.py`: warn if `CHANGELOG.md` does not exist at the repository root.
6. Acceptance: the generated `CHANGELOG.md` contains a `## [v2.0.0]` section with correct Added/Changed/Fixed entries; shipping a story adds a line to `### Unreleased`; running `pacemap.update_changelog("v3.0.0", ...)` moves Unreleased into a versioned block.

---

## Sequencing Summary

```text
v2.0-alpha  ──►  Item 1  (Branching Model)             [DELIVERED]
                 Item 2  (PACE Planner)                 [DELIVERED]
                 Item 9  (Config Tester)                [DELIVERED]

v2.0-beta   ──►  Item 3  (Context Versioning)           [DELIVERED]
                 Item 4  (Auto-Update)                  [DELIVERED]
                 Item 8  (Cron Configuration)           [DELIVERED]

v2.0-rc     ──►  Item 5  (Communications & Alerts)      [DELIVERED]
                 Item 6  (Tracker Artifacts)            [DELIVERED]
                 Item 7  (GitLab/Jenkins/Bitbucket)     [DELIVERED]

v2.1        ──►  Item 10 (Plugin System)                [DELIVERED]

v2.2        ──►  Item 11 (Training Data Pipeline)       [DELIVERED]

v3.0        ──►  Item 12 (Context Directory Versioning) [DELIVERED]
                 Item 13 (Context Auto-Refresh)         [DELIVERED]
                 Item 14 (Multi-Release Configuration)  [DELIVERED]
                 Item 15 (plan.yaml & Story Naming)     [DELIVERED]
                 Item 16 (Pre-run Validation Extended)  [DELIVERED]
                 Item 17 (.pacemap Directory)            [DELIVERED]
                 Item 18 (CHANGELOG.md)                 [DELIVERED]

v3.1        ──►  Item 19 (Planner-Triggered Context Refresh) [PLANNED]
                 Item 20 (Human-Gate Context Refresh)        [PLANNED]
                 Item 21 (Stale File Read Eviction)          [PLANNED]
                 Item 22 (Test Output Deduplication)         [PLANNED]
                 Item 23 (Write Receipt Suppression)         [PLANNED]

v3.2        ──►  Item 24 (Haiku Context Compression)         [PLANNED]
                 Item 25 (Pre-seeded File Map)               [PLANNED]

v3.3        ──►  Item 26 (Forked Subcontext)                 [PLANNED]
```

---

## Phase 5 — Training Data Pipeline (`@Since v2.2`)

**Goal:** Instrument PACE to continuously collect and export high-quality LLM fine-tuning data from every shipped story, enabling future SFT and RLHF on PACE-generated code generation traces.

### Item 11 — Training Data Pipeline

> **@Since** `v2.2` &nbsp;·&nbsp; **PR:** #12 &nbsp;·&nbsp; **Status:** Merged

#### Background

Each PACE sprint day produces a structured triple that is exactly what is needed for LLM fine-tuning:

- `story.md` — natural language requirements (input to FORGE)
- `forge_trace.json` — FORGE's full conversation trace: system prompt, tool calls, tool results, and assistant turns (the target sequence to learn)
- `handoff.md` — structured outcome: coverage delta, test counts, iterations used, cost (output signal)
- `gate.md` — per-AC pass/fail results (reward labels for RLHF)

Filtered to shipped days only (GATE decision == SHIP), this corpus trains a smaller, faster model to replicate FORGE's code generation behaviour at 80–95% lower cost.

#### Architecture

1. **`pace/training/collector.py`** — reads `.pace/day-N/` artifacts and constructs `StoryTrace` dataclass instances; computes an RLHF reward score from GATE pass rate, `iterations_used`, and `forge_cost_usd`.
2. **`pace/training/exporter.py`** — serialises traces to JSONL in two formats:
   - **SFT**: Anthropic messages format `(system + story, FORGE trace)` pairs for supervised fine-tuning.
   - **Reward**: `(trace, score)` pairs for RLHF reward model training.
3. **`pace/training/hook.py`** — `DataExportHook(HookBase)`, subscribed to `day_shipped`; invokes collector + exporter; configured via `pace.config.yaml` `training:` section.
4. **`pace/agents/forge.py`** — on successful `complete_handoff`, write the conversation trace to `forge_trace.json` before clearing the checkpoint, so the artifact persists for the hook.
5. **`pace/config.py`** — `TrainingConfig` dataclass; `training:` key on `PaceConfig`.
6. **`pace/orchestrator.py`** — register `DataExportHook` when `cfg.training.export_on_ship`; fire remaining lifecycle hooks (`story_generated`, `forge_complete`, `gate_pass`, `sentinel_pass`, `conduit_pass`); include `pace_dir` in `day_shipped` payload.
7. **`pace/config_tester.py`** — `_validate_training()` validator.

#### Acceptance criteria

1. After a shipped day, `.pace/day-N/forge_trace.json` exists and contains a `messages` list of Anthropic-format turns.
2. `DataExportHook` appends one JSONL line per shipped story to the configured `output_dir`.
3. `export_sft_jsonl()` produces valid Anthropic fine-tuning format (system, messages array).
4. `export_reward_jsonl()` produces `{prompt, completion, reward}` lines with reward ∈ [0.0, 1.0].
5. `_validate_training()` catches invalid `output_dir`, unsupported `format`, and out-of-range `min_gate_pass_rate`.
6. All remaining `HOOK_EVENTS` (`story_generated`, `forge_complete`, `gate_pass`, `sentinel_pass`, `conduit_pass`) are fired by the orchestrator at the correct pipeline points.

---

---

## Phase 7 — Context Intelligence & FORGE Efficiency

**Goal:** Ensure context documents are always accurate at every human decision
point (plan-approval PR, human-gate review PR), and eliminate the three dominant
FORGE context growth drivers to reduce per-story FORGE cost by 60–80%.

**Target releases:** v3.1 (Sprint 7.1–7.2), v3.2 (Sprint 7.3–7.4), v3.3
(Sprint 7.5)

---

### Sprint 7.1 — Context Lifecycle

---

### Item 19 — Planner-Triggered Context Refresh

> **@Since** `v3.1` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

`pace-planner.yml` runs cost estimation and opens a plan-approval PR for human
review. SCRIBE is never invoked by the planner pipeline — context documents
(`engineering.md`, `security.md`, `devops.md`, `product.md`) are only refreshed
on the daily preflight path when files are detected as missing or their source
hashes have changed. Between sprint planning sessions the codebase evolves: new
modules are added, interfaces change, and the context docs drift from reality.

The plan-approval PR is the highest-leverage human decision point in the PACE
lifecycle. A reviewer approving it is committing to the cost estimates and story
scope for the entire upcoming sprint. If `engineering.md` is stale, PRIME
receives inaccurate module context on Day 1, story cards reference non-existent
interfaces, and FORGE starts each story with a misleading codebase map —
compounding cost across every story in the sprint.

#### Recommendation

In `run_pipeline()` in `planner.py`, before calling `run_planner()`, invoke
`_check_context_freshness()`. If any source-doc hashes have changed since the
last SCRIBE run (or if any required context docs are missing), call `run_scribe()`
to regenerate them. The refreshed context docs are then committed to the
`pace/plan-approval` branch alongside the planner report, so the plan-approval
PR body and diff both reflect the updated codebase state.

The SCRIBE call in pipeline mode is non-fatal: if it fails, planner execution
continues and the plan-approval PR is still opened with a warning in the PR body.

#### Execution Plan

1. `pace/planner.py` — in `run_pipeline()`, call `_check_context_freshness()`
   before `run_planner()`. If it returns a non-empty changed-files list, or if
   `_missing_docs()` is non-empty, call `run_scribe()` (import from
   `agents/scribe.py`). Wrap in `try/except`; log but do not raise on failure.
2. `pace/planner.py` — set a boolean flag `context_refreshed` and pass it to
   `run_pipeline()`'s return value so the workflow can log it.
3. `.github/workflows/pace-planner.yml` — after the `Run planner` step, add a
   summary step that reads `context_refreshed` from the planner output and appends
   a note to the PR body: `"Context documents refreshed: yes/no"`.
4. `pace/planner.py` — write a `context_refresh_summary` key into
   `.pace/day-0/planner.md` (the YAML report): list of docs refreshed, source
   files that triggered the refresh, and SCRIBE cost.
5. `pace/config_tester.py` — add `_validate_context_docs()`: warn if no
   `context.manifest.yaml` exists (context never generated for this release).
6. `tests/test_planner_context_refresh.py` — unit tests: (a) fresh context
   skips SCRIBE, (b) stale hash triggers SCRIBE, (c) SCRIBE failure is non-fatal,
   (d) planner.md includes `context_refresh_summary` key.

#### Acceptance criteria

1. `run_pipeline()` calls `run_scribe()` when `_check_context_freshness()`
   returns at least one changed file.
2. `run_pipeline()` calls `run_scribe()` when any required context doc is
   missing.
3. A SCRIBE failure during pipeline run does not abort `run_planner()` — a
   warning is printed and execution continues.
4. `.pace/day-0/planner.md` contains a `context_refresh_summary` key on every
   pipeline run (empty list when no refresh occurred).
5. The plan-approval PR branch contains up-to-date context docs when a refresh
   was triggered.
6. `_validate_context_docs()` emits a warning when `context.manifest.yaml` is
   absent.

---

### Item 20 — Human-Gate Context Refresh

> **@Since** `v3.1` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

When a story carries `human_gate: true`, the orchestrator opens a review PR and
exits. The reviewer is expected to audit the story's code, test results, and
security report before approving. Currently SCRIBE is never invoked at this
point — the context docs in the PR may reflect the state of the codebase from
the last time SCRIBE ran (potentially several stories ago).

The human gate is a trust point: a human is certifying that the codebase is
correct and safe before execution continues. Stale `engineering.md` and
`security.md` in the PR undermine this trust and force the reviewer to mentally
reconstruct the current module map from the diff rather than reading it directly.

#### Recommendation

In `orchestrator.py`, before calling `ci.open_review_pr()` on a human-gate
story, invoke `run_scribe()`. If SCRIBE succeeds, the refreshed context docs are
already on the working branch (SCRIBE writes to `.pace/context/` which is tracked
by git) — they will appear in the review PR diff automatically. If SCRIBE fails,
open the PR anyway with a warning comment.

Additionally, the review PR body should include a `## Context` section listing
which context docs were refreshed and the SCRIBE cost for this invocation.

#### Execution Plan

1. `pace/orchestrator.py` — in `run_cycle()`, locate the `human_gate` branch
   (currently `ci.open_review_pr(day, PACE_DIR)` then `sys.exit(0)`). Before
   `open_review_pr`, call `run_scribe()` wrapped in `try/except`. Log success or
   failure. Store result in a local `scribe_refreshed` bool.
2. `pace/orchestrator.py` — commit the refreshed context docs to the working
   branch before `open_review_pr`. Use `commit_artifact()` with message
   `"Day {day}: refresh context docs before human gate"`. If no docs changed,
   skip the commit (git will report nothing to commit — handle gracefully).
3. `pace/platforms/base.py` / `CIAdapter` — extend `open_review_pr()` signature
   to accept an optional `context_note: str | None = None` parameter. Platforms
   that support PR body customisation (GitHub, GitLab) append it to the PR body.
4. `pace/orchestrator.py` — build `context_note` from the SCRIBE result (docs
   refreshed, source files changed, cost). Pass to `open_review_pr()`.
5. `pace/spend_tracker.py` — SCRIBE's human-gate call is already tracked by the
   existing spend_tracker; confirm it is included in the daily spend update at
   `atexit`.
6. `tests/test_human_gate_context.py` — unit tests: (a) SCRIBE called before
   `open_review_pr`, (b) SCRIBE failure does not prevent PR opening, (c)
   context_note populated on success, (d) empty note on SCRIBE failure.

#### Acceptance criteria

1. When `human_gate: true` triggers, `run_scribe()` is called before
   `ci.open_review_pr()`.
2. A successful SCRIBE run results in a git commit on the working branch with
   updated context docs before the PR is opened.
3. A SCRIBE failure results in the PR opening with a `context_note` warning, not
   an abort.
4. The review PR body includes a `## Context` section when SCRIBE ran
   successfully.
5. SCRIBE cost from the human-gate invocation is included in the daily spend
   total written to `PACE_DAILY_SPEND`.
6. No regression to existing human-gate flow when `run_scribe()` raises.

---

### Sprint 7.2 — FORGE Context Efficiency: Stage 1

*Background: see [FORGE-COST-SAVING-PLAN.md](../FORGE-COST-SAVING-PLAN.md) for
the full root cause analysis and per-option savings estimates derived from the
Day 23 production run. Items 21–23 target the three identified growth drivers
with zero quality risk.*

---

### Item 21 — FORGE Stale File Read Eviction

> **@Since** `v3.1` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

FORGE's `read_file` tool results persist in the conversation history for the
entire session. When FORGE later writes to the same file via `write_file`, the
earlier `read_file` result becomes stale — it describes a version of the file
that no longer exists. On Day 23 this produced ~20,000 orphaned tokens across
iterations 1–13, 19, and 21: the model attended over source it had already
replaced, increasing both cost and the risk of the model accidentally reverting
to the stale version.

#### Recommendation

In `forge.py`, maintain a `_written_paths` set. Before each `adapter.chat()`
call, scan the `messages` list for `tool_result` blocks produced by `read_file`
where the path appears in `_written_paths`. Replace the content of those blocks
with a compact eviction notice: `"[evicted: superseded by write at iter N]"`.
The `tool_use` and `tool_result` message pair is preserved (required for Anthropic
API message structure) — only the content string is replaced.

#### Execution Plan

1. `pace/agents/forge.py` — add `_written_paths: set[str]` initialised to `set()`
   before the iteration loop.
2. `pace/agents/forge.py` — in the tool dispatch block, when `write_file` is
   called successfully, add the normalised path to `_written_paths`.
3. `pace/agents/forge.py` — add helper `_evict_stale_reads(messages, written)`.
   Iterates `messages`; for each `tool_result` that follows a `tool_use` with
   `name == "read_file"`, checks if the `path` argument is in `written`; if so,
   replaces content with the eviction notice. Returns new message list (does not
   mutate in place).
4. `pace/agents/forge.py` — call `_evict_stale_reads(messages, _written_paths)`
   immediately before `adapter.chat(messages=messages, ...)` in the loop body.
5. `pace/agents/forge.py` — log eviction count per iteration at DEBUG level:
   `[FORGE] iter {n}: evicted {k} stale read(s)`.
6. `tests/test_forge_eviction.py` — unit tests: (a) path not in written → not
   evicted, (b) path in written → content replaced, (c) multiple reads of same
   path → all evicted after write, (d) message structure valid after eviction
   (tool_use/tool_result pair preserved).

#### Acceptance criteria

1. `_evict_stale_reads()` replaces the content of `read_file` tool_results for
   any path that has been written in the current session.
2. The `tool_use` / `tool_result` pair structure is preserved (Anthropic API
   rejects orphaned tool_result blocks).
3. Eviction count is logged per iteration.
4. Existing FORGE test suite passes without modification.
5. No regression on stories that never call `write_file` on a previously-read
   file (eviction set is empty → no-op).

---

### Item 22 — FORGE Test Output Deduplication

> **@Since** `v3.1` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

Each `run_bash` call that executes the test command appends 1–3k tokens of pytest
or go-test output to the conversation history. On Day 23, FORGE ran the test
command 9 consecutive times across iterations 6, 11, 16, 17, and 25–33. Only the
most recent result carries signal; the prior 8 results are redundant noise adding
~18,000 tokens. Every subsequent `chat()` call re-attends to all of them.

#### Recommendation

In `forge.py`, maintain a `_last_bash_result: dict[str, int]` mapping
`command_signature → message_index`. Before each `adapter.chat()` call, for any
`run_bash` tool_result where a newer result with the same command signature exists
in the message list, replace the older result's content with a deduplication
notice: `"[deduplicated: superseded by run at iter N]"`. Command signature is
the full command string, normalised (stripped, lowercased).

#### Execution Plan

1. `pace/agents/forge.py` — add `_last_bash_idx: dict[str, int]` initialised to
   `{}` before the iteration loop.
2. `pace/agents/forge.py` — in the tool dispatch block, after `run_bash`
   completes, record `_last_bash_idx[cmd_sig] = current_message_index`.
3. `pace/agents/forge.py` — add helper `_dedup_bash_results(messages)`. For each
   `run_bash` tool_result, look up its command signature; if a later result with
   the same signature exists, replace content with the dedup notice. Returns new
   message list.
4. `pace/agents/forge.py` — call `_dedup_bash_results(messages)` immediately
   before `adapter.chat()`, after `_evict_stale_reads()`.
5. `pace/agents/forge.py` — log dedup count per iteration at DEBUG level.
6. `tests/test_forge_dedup.py` — unit tests: (a) single run → not deduped,
   (b) two runs same command → first deduped, (c) two different commands →
   neither deduped, (d) three runs same command → first two deduped, latest kept.

#### Acceptance criteria

1. For any command run more than once in a FORGE session, only the most recent
   `run_bash` tool_result retains its full content in the message list passed to
   `adapter.chat()`.
2. Deduplication notices reference the iteration number of the superseding run.
3. Commands with different signatures are never cross-deduped.
4. Existing FORGE test suite passes without modification.

---

### Item 23 — FORGE Write Receipt Suppression

> **@Since** `v3.1` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

The `write_file` tool result echoes the full content of the file just written
back into the conversation history. On Day 23, 6 write calls across iterations
14, 15, 20, 22, 23, and 24 produced ~12,000–14,800 tokens of write echo that
served no purpose after the write was confirmed: the model already knows what it
wrote (it generated the content), and the content is available via `read_file`
if it needs to refer to it again.

#### Recommendation

In `forge.py` (or in the tool dispatch layer), after a successful `write_file`
call, replace the tool_result content with a compact receipt before appending to
the message history: `"OK: wrote {N} bytes to {path} (iter {i})"`. The full
content is never inserted into the messages list. This is applied at write time
(not in a pre-chat pass) since there is no reason to ever accumulate the full
write echo.

#### Execution Plan

1. `pace/agents/forge.py` — in the `write_file` tool dispatch block, after the
   file is written successfully, construct the receipt string:
   `f"OK: wrote {len(content)} bytes to {path} (iter {iteration})"`.
2. `pace/agents/forge.py` — append the `tool_result` message using the receipt
   string instead of the full file content.
3. `pace/agents/forge.py` — log at DEBUG level: `[FORGE] write receipt: {path}
   ({N} bytes suppressed)`.
4. `tests/test_forge_write_suppression.py` — unit tests: (a) write_file result
   contains receipt not full content, (b) receipt includes byte count and path,
   (c) file on disk contains full content (suppression is history-only).

#### Acceptance criteria

1. `write_file` tool_result content in the messages list is always the compact
   receipt string, never the full file content.
2. The file written to disk contains the full content (suppression is message-
   history only — no data loss).
3. The receipt string includes byte count, path, and iteration number.
4. Existing FORGE test suite passes. Stories that call `read_file` after
   `write_file` on the same path correctly read the current file content from
   disk, unaffected by suppression.

---

### Sprint 7.3 — FORGE Context Efficiency: Stage 2

---

### Item 24 — FORGE Haiku Context Compression

> **@Since** `v3.2` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

Even with Stage 1 eviction applied, the cumulative message history grows linearly
across 35 iterations. Early exploration iterations contain tool call/result pairs
(file reads, directory listings, reasoning) that are no longer directly relevant
once FORGE has committed to an implementation plan. These early iterations are
not stale in the same sense as superseded reads — they informed the plan — but
the detail they carry (full directory listings, intermediate reasoning traces) is
low-signal for the implementation phase.

On Day 23 Run 4, after Stage 1 the estimated residual context would still reach
~35,000 input tokens by iteration 33. A single Haiku compression call after the
RED phase (first test failure) can reduce the early exploration context to a
structured ~2,000-token YAML summary, saving ~20,000 additional tokens.

#### Recommendation

In `forge.py`, define a compression trigger: fire once, when FORGE transitions
into the RED phase (first non-zero test exit code). At that point, call a Haiku
`complete()` with a structured prompt to compress iterations 1–N into a YAML
progress summary. Replace those iterations in the messages list with a single
`assistant` turn containing the YAML. Subsequent iterations operate on the
compressed history.

Required mitigations (from FORGE-COST-SAVING-PLAN.md risk table):

- **4a** — define a strict compression YAML schema (fields: files_read,
  files_written, plan_committed, test_results_summary, key_decisions)
- **4b** — include anti-hallucination constraints in the Haiku prompt: "only
  summarise, never infer or invent; if uncertain, omit"
- **4c** — single-trigger guard: compression fires exactly once per FORGE
  session (flag `_compressed = False`)
- **4d** — post-compression verification: assert all paths in `_written_paths`
  appear in the YAML `files_written` list; abort compression (keep original) on
  mismatch
- **4e** — fallback: if Haiku call fails or verification fails, log a warning and
  continue with the uncompressed history

#### Execution Plan

1. `pace/agents/forge.py` — add `_compressed: bool = False` before the iteration
   loop.
2. `pace/agents/forge.py` — after each `run_bash` tool result is appended, check
   if the test command returned exit code ≠ 0 and `not _compressed`. If both,
   trigger compression.
3. `pace/agents/forge.py` — add `_compress_history(messages, model, written_paths)`
   function. Builds Haiku `complete()` prompt with compression schema and
   anti-hallucination constraints. Calls `analysis_adapter.complete()` (Haiku).
   Verifies written_paths coverage. Returns compressed messages list on success,
   original list on failure.
4. `pace/agents/forge.py` — replace `messages` with the return value of
   `_compress_history()`. Set `_compressed = True` regardless of success/failure.
5. `pace/config.py` — `ForgeConfig`: add `compression_model: str | None = None`
   (defaults to `analysis_model` if set, else main model). This allows
   compression to use Haiku even when `analysis_model` is not configured.
6. `tests/test_forge_compression.py` — unit tests for all five mitigations.

#### Acceptance criteria

1. Compression fires exactly once per FORGE session, on the first RED-phase
   detection.
2. Post-compression messages list contains the YAML summary block plus all
   iterations after the trigger point.
3. All paths in `_written_paths` at trigger time appear in the YAML
   `files_written` list (verification passes).
4. Compression failure (Haiku call error or verification mismatch) leaves the
   original messages list intact and logs a warning.
5. `compression_model` config key controls which model is used for compression;
   defaults to `analysis_model` when set.
6. FORGE still ships the story correctly with compressed history (integration
   test on a simple story).

---

### Sprint 7.4 — FORGE Context Efficiency: Stage 3

---

### Item 25 — FORGE Pre-seeded File Map

> **@Since** `v3.2` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

On Day 23, FORGE spent iterations 1–13 in pure exploration: reading 11 files and
2 directory listings before writing a single line of code. This is a discovery
phase — FORGE does not know where the relevant modules are. If it already knew,
it would jump directly to the relevant files in 3–4 iterations instead of 13.

`engineering.md` contains exactly this map: module paths, interfaces, test
patterns, and conventions — synthesised by SCRIBE after every story. It already
exists in `.pace/context/` and is passed to FORGE's system prompt via the Story
Card. However, the Story Card presents it as background narrative; FORGE does not
extract a concrete file-read list from it before starting.

#### Recommendation

In the FORGE initial user message (the Story Card rendered for FORGE), append a
`## File Hints` section generated by a Haiku pre-pass over `engineering.md`.
The pre-pass extracts 5–10 file paths most likely to be relevant to the story's
acceptance criteria. These are presented as hints (not constraints): "these files
are likely relevant — read them first, but follow your own judgement."

Required mitigations (from FORGE-COST-SAVING-PLAN.md risk table):

- **5a** — explicit "hints not constraints" framing in the section header
- **5b** — confidence threshold: only inject hints when the Haiku pre-pass
  confidence score is ≥ 0.7; skip injection (not abort) when below threshold
- **5d** — freshness check: only inject hints if `engineering.md` was updated
  within the current release (compare against `context.manifest.yaml` timestamp)
- **5e** — override mechanism: story-level `disable_file_hints: true` field in
  plan.yaml skips injection for that story (useful for architectural stories that
  intentionally explore broadly)

Skip **5c** (SCRIBE self-confidence scoring): LLM self-assessment of confidence
is unreliable; confidence is computed from the Haiku pre-pass response directly.

#### Execution Plan

1. `pace/agents/forge.py` — add `_build_file_hints(story_card, cfg)` function.
   Reads `engineering.md` from CONTEXT_DIR. Makes a Haiku `complete()` call with
   a prompt: "Given this story card and the engineering context, list the 5–10
   file paths most likely to need reading or modification. Return YAML list only."
   Returns `list[str]` of paths, or `[]` on failure/low confidence.
2. `pace/agents/forge.py` — in `run_forge()`, before building the initial user
   message, call `_build_file_hints()`. If non-empty, append a `## File Hints`
   section to the user message.
3. `pace/agents/prime.py` — extend the Story Card YAML to carry an optional
   `disable_file_hints: bool` field. `run_forge()` reads it and skips hint
   injection when `true`.
4. `pace/agents/forge.py` — freshness check: read `context.manifest.yaml`; if
   `generated_at` is older than the first story in the current release, skip
   hints (log warning).
5. `pace/config.py` — `ForgeConfig`: add `file_hints_enabled: bool = True` and
   `file_hints_confidence_threshold: float = 0.7`.
6. `tests/test_forge_file_hints.py` — unit tests for all four active mitigations.

#### Acceptance criteria

1. `_build_file_hints()` returns a non-empty list for a story with clear
   acceptance criteria and a populated `engineering.md`.
2. File hints appear in the FORGE initial user message under `## File Hints`.
3. A `disable_file_hints: true` field in the story card suppresses injection
   with no error.
4. Hints are not injected when `engineering.md` is absent or stale (logs warning,
   does not abort).
5. Hints are not injected when Haiku confidence < threshold (graceful skip).
6. FORGE exploration phase is measurably shorter on stories where hints are
   injected vs. a baseline without hints (integration test on a known story).

---

### Sprint 7.5 — FORGE Context Efficiency: Stage 4

---

### Item 26 — FORGE Forked Subcontext

> **@Since** `v3.3` &nbsp;·&nbsp; **Status:** Planned

#### Assessment

Items 21–25 reduce context growth but do not eliminate it. As long as exploration
and implementation share a single conversation, the exploration context (file
reads, reasoning, partial attempts) accumulates alongside the implementation
context (writes, test runs, corrections). For complex stories with 25–35
iterations, the residual context after Stage 1–3 optimisations is still
30,000–40,000 tokens by the final iteration.

The root cause is architectural: a single Anthropic `messages` list is shared
across two qualitatively different phases. The exploration phase discovers the
relevant files and commits to a plan. The implementation phase executes the plan.
These phases have different context requirements — the implementation phase does
not need the full detail of every exploration step; it needs the committed plan
and the current file state.

#### Recommendation

Split FORGE into two API contexts. The first context (exploration) runs until
FORGE emits a `commit_plan` tool call. The second context (implementation) starts
fresh with: the system prompt, the Story Card, and the committed plan YAML
emitted by `commit_plan`. The exploration context is discarded. The implementation
context begins from a clean 8,000–12,000 token baseline regardless of how long
exploration took.

Required mitigations — deliver in three phases:

**Phase A (deliver first, validate before Phase B):**

- **6b** — `commit_plan` tool definition: schema for the plan YAML (files to
  modify, test strategy, acceptance criteria mapping). FORGE must call this before
  any `write_file` call.
- **6d** — fallback to single-context mode: if `commit_plan` is not called within
  `fork_trigger_max_iterations` (default: 20), abort the fork and continue in
  single-context mode for the remainder of the session.

**Phase B (after Phase A validated on 10+ stories):**

- **6e** — exploration budget cap: `fork_exploration_max_iterations` config key
  (default: 20). If FORGE reaches this limit without calling `commit_plan`, emit
  a synthetic `commit_plan` from the most recent file-map state and fork anyway.

**Phase C (after Phase B validated):**

- **6a** — exploration context summary: before discarding the exploration context,
  compress it with a Haiku call (reusing Item 24 compression infrastructure).
  Append the summary to the implementation context's initial message.
- **6c** — scratchpad isolation: provide FORGE with a `write_scratchpad` tool
  available only in the exploration context. Prevents accumulation of intermediate
  reasoning in the implementation context. **Note:** the scratchpad itself must be
  token-capped (max 2,000 tokens) to avoid recreating the accumulation problem.

#### Execution Plan

**Phase A:**

1. `pace/agents/forge.py` — add `commit_plan` to the tool definitions. Schema:
   `{files_to_modify: list[str], implementation_steps: list[str],
   test_strategy: str}`.
2. `pace/agents/forge.py` — add `_fork_context(plan_yaml, story_card, cfg)`
   that builds a fresh messages list: system prompt (same) + new user message
   containing Story Card + committed plan. Returns the new messages list.
3. `pace/agents/forge.py` — in the iteration loop, when `commit_plan` is the
   tool called, fork the context: `messages = _fork_context(...)`. Log:
   `[FORGE] context forked at iter {n} — implementation starts fresh`.
4. `pace/agents/forge.py` — add `_fork_triggered: bool = False`. Set after fork.
   If `max_iterations` reached and `not _fork_triggered`, fall back to single
   context and log a warning (mitigation 6d).
5. `pace/config.py` — `ForgeConfig`: add `fork_trigger_max_iterations: int = 20`
   and `fork_enabled: bool = False` (opt-in until Phase C validated).

**Phase B:**

1. `pace/config.py` — add `fork_exploration_max_iterations: int = 20`.
2. `pace/agents/forge.py` — if iteration count reaches
   `fork_exploration_max_iterations` and `commit_plan` not yet called, synthesise
   a `commit_plan` from `_written_paths` and current file map. Fork.

**Phase C:**

1. `pace/agents/forge.py` — before `_fork_context()`, call
   `_compress_history()` (Item 24 infrastructure). Append compressed summary to
   the implementation context initial message.
2. `pace/agents/forge.py` — in exploration context only, add `write_scratchpad`
   tool. Cap accumulated scratchpad content at 2,000 tokens (truncate oldest
   entries).

#### Acceptance criteria

**Phase A:**

1. FORGE calls `commit_plan` before any `write_file` call on a story where
   `fork_enabled: true`.
2. After `commit_plan`, the messages list is replaced with a fresh context
   containing only the Story Card and committed plan.
3. If `commit_plan` is not called within `fork_trigger_max_iterations`, execution
   continues in single-context mode (no abort, no data loss).
4. `[FORGE] context forked at iter N` appears in the run log when a fork occurs.

**Phase B:**

1. When `fork_exploration_max_iterations` is reached without `commit_plan`, a
   synthetic plan is committed and the fork proceeds.

**Phase C:**

1. Implementation context initial message contains the exploration summary from
   `_compress_history()`.
2. Scratchpad content in the implementation context never exceeds 2,000 tokens.

---

## Out of Scope for This Roadmap

- UI dashboard for PACE metrics (future consideration post-v2.1)
- Multi-team / multi-release parallelism (architectural prerequisite: shared state store)

---

## Post-v2.1 Horizon: LLM Fine-Tuning on PACE-Generated Stories

Once the plugin system, tracker artifact push, and context versioning are in place, PACE will have accumulated a structured, high-quality dataset of:

- `story.md` files (natural language requirements)
- `handoff.yaml` files (structured outcomes: pass/fail, coverage delta, test counts)
- FORGE conversation logs (multi-step code generation traces with tool call sequences)
- GATE/SENTINEL evaluations (quality scores and rejection reasons)

This dataset is exactly what is needed to fine-tune a smaller, faster model (e.g. a Haiku-class or open-weights model) to perform FORGE's coding task at a fraction of the cost of a frontier model.

### The fine-tuning opportunity in brief

1. **Dataset collection** (prerequisite: Items 3 + 6 + context versioning): export `story.md` + `forge_checkpoint.json` + `handoff.yaml` triples per shipped story into a training corpus. Filter to only GREEN-phase handoffs (stories that passed GATE without revision). Target: 500–1000 high-quality traces to start.

2. **Supervised fine-tuning (SFT)**: train on `(system_prompt + story + tool_defs, FORGE_conversation_trace)` pairs. The model learns to produce the correct sequence of tool calls (write file, run tests, commit) for a given story type without requiring frontier-model reasoning.

3. **RLHF signal from GATE**: GATE's structured scores (coverage delta, AC coverage, test quality) provide a natural reward signal for reinforcement learning from human feedback — without requiring human labellers. Each GATE evaluation is an automatic quality label.

4. **Cost impact**: a fine-tuned 7B–13B parameter model running locally (via Ollama + the existing LiteLLM adapter) could replace frontier-model FORGE calls entirely for routine stories, reducing per-story cost by 80–95%.

5. **Prerequisites**: the plugin system (Item 10) should expose a `DataExportHook` that streams story traces to a training store; the LiteLLM adapter (already implemented) handles routing to the fine-tuned model once it is deployed.

This is deferred to post-v2.1 because it requires a minimum viable dataset that only accumulates after several months of real PACE usage with the v2.0 feature set in production.

---

*PACE Framework Roadmap v1.6 — 2026-03-20 IST*
*Phase 7 added: Items 19–26 (Context Intelligence & FORGE Efficiency)*
*Author: Vipuul Meehniaa*
