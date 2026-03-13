# PACE Framework — Product Roadmap

**Author:** Vipuul Meehniaa
**Date:** 2026-03-13:19:09 (IST — Asia/Kolkata)
**Roadmap Version:** 1.1 (revised 2026-03-13 IST)
**PACE Framework Baseline:** v1.2.0
**Target Release:** PACE v2.0

---

## Overview

This roadmap covers ten strategic improvements to the PACE framework, each assessed for impact, complexity, and delivery sequencing. Items are grouped into four execution phases based on dependency order and effort. Each item includes an Assessment (current state and problem), a Recommendation (proposed solution), and an Execution Plan (concrete deliverables and acceptance criteria).

---

## Execution Phases at a Glance

| Phase | Theme | Items | Target |
|-------|-------|-------|--------|
| 1 | Foundation | Branching Model, PACE Planner, Config Tester | v2.0-alpha |
| 2 | Intelligence & Efficiency | Context Versioning, Auto-Update, Cron Management | v2.0-beta |
| 3 | Integration & Ecosystem | Comms & Alerts, Tracker Artifacts, CI/CD Pipelines | v2.0-rc |
| 4 | Extensibility | Plugin System | v2.1 |

---

## Phase 1 — Foundation

### Item 1: Sprint/Release Branching Model

**Assessment**

The current model treats the `pace/sprint-N` branch as the primary delivery unit, but this conflates a sprint (a short time-box) with a release (a shippable increment). In real AGILE practice, multiple sprints compose a release. The current flat branch structure prevents PACE from reasoning about long-horizon deliverables and forces every sprint into an implicit full release cycle.

**Recommendation**

Redefine the delivery hierarchy as follows:

```
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

**Execution Plan**

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
5. CONDUIT: after all sprint PRs are merged to `release/<name>`, open a PR to `staging`. Monitor the staging CI run; once it passes, open the final PR from `staging` → `main`. If staging CI fails, open a HOLD issue and set `PACE_PAUSED=true`.
6. Add branch-protection checks to `preflight.py` — abort if `main` or `staging` protection rules are missing.
7. Acceptance: (a) PACE creates the full `main → staging → release/v2.0 → rel/sprint/pace-1` hierarchy on first run; (b) end-of-sprint PR is opened to `release/v2.0`; (c) after all sprints merge, a PR to `staging` is opened; (d) once staging CI passes, the final PR to `main` is opened automatically.

---

### Item 2: PACE Planner Pipeline

**Assessment**

Day-0 planning is currently baked into the orchestrator as a one-time initialization step. There is no way to re-plan mid-release without manually editing `plan.yaml` and potentially breaking sprint accounting. Re-budgeting after scope changes is entirely manual. The absence of an approval gate means a broken plan can silently propagate into sprint execution.

**Recommendation**

Extract Day-0 into a standalone, re-runnable **pace-planner** pipeline:

- `pace-planner` runs independently of the main PACE cron.
- On first run: produces the initial `plan.yaml` + budget, commits shipped items, opens a plan-approval PR.
- On re-run (triggered manually or by context update): diffs against current `plan.yaml`, identifies already-SHIPPED items, regenerates plan for remaining scope, opens a re-plan PR.
- Execution of PACE sprints is **blocked** (`PACE_PAUSED=true`) until the plan-approval PR is merged.
- Budget and AC counts are re-estimated by PRIME on each planner run.

**Execution Plan**

1. Extract planning logic from `orchestrator.py` into `planner.py` (already exists as a stub — flesh it out).
2. Add `pace-planner.yml` CI workflow alongside `pace.yml`.
3. PRIME agent: add `plan_mode` flag that returns a structured re-plan diff (new stories, removed stories, scope changes) rather than directly writing `plan.yaml`.
4. CONDUIT: create plan-approval PR; set `PACE_PAUSED=true` as a CI/CD variable; unset after merge.
5. SCRIBE: generate a human-readable planning report summarising budget impact and scope delta when re-planning.
6. `planner.py`: serialize shipped stories to a `shipped.yaml` manifest; never re-plan shipped items.
7. Acceptance: re-running `pace-planner` after two stories are SHIPPED produces a PR that excludes those stories and shows updated cost projection.

---

### Item 9: Configuration Tester

**Assessment**

`pace.config.yaml` is the single most critical file in a PACE setup. Misconfiguration (wrong model IDs, missing `github_org`, non-semantic sprint/release day values, cost thresholds that are too low for the model in use) silently degrades or breaks the entire pipeline. Currently there is no validation beyond Python `KeyError`s at runtime.

**Recommendation**

Build a `pace-config-test` CLI command and CI step that validates `pace.config.yaml` before any agent is invoked:

- **Hard errors**: missing required fields, invalid provider/model IDs, unreachable `docs_dir`.
- **Warnings**: `sprint_days > release_days`, `max_story_cost_usd` lower than the cheapest model call (~$0.01), `analysis_model` set to an opus-class model (unnecessarily expensive for analysis tasks).
- **Suggestions**: fields not set that have useful non-default options (e.g. `reporter.timezone`, `forge.max_iterations`).
- Output is human-readable on CLI and JSON-serializable for CI integration.

**Execution Plan**

1. Create `pace/config_tester.py` with a `ConfigTestResult` dataclass (errors, warnings, suggestions).
2. Implement validators for each top-level config section (product, sprint, release, source, tech, platform, llm, forge, cost_control, advisory, reporter, cron).
3. Add known-valid model ID list (sync with Anthropic and LiteLLM release notes quarterly).
4. Expose as `python pace/config_tester.py` CLI; exit code 0 = clean, 1 = warnings, 2 = errors.
5. Add `pace-config-test` as the first step in both `pace.yml` and `pace-planner.yml`.
6. Acceptance: a config with `sprint_days: 200` and `release_days: 90` exits with code 1 and prints a warning; a config with no `llm.model` exits with code 2.

---

## Phase 2 — Intelligence & Efficiency

### Item 3: Context Versioning & Token Management

**Assessment**

PACE currently has no systematic approach to managing the total token context across multi-day sprints. Each agent call starts fresh except for FORGE's new checkpoint (added in v1.2). Story files, handoff YAML, and plan data grow unbounded. There is no versioning of the planning context, so drift between `plan.yaml` and `.pace/day-N/story.md` is invisible.

**Recommendation**

Implement three complementary mechanisms:

1. **Context versioning**: every write to `plan.yaml` or `pace.config.yaml` increments a `context_version` field (semver patch bump). Agents log the context version they operated under. Divergence between the version at plan time and at execution time triggers a re-plan warning.

2. **Context compaction**: before each PRIME/GATE/SENTINEL call, `orchestrator.py` compacts the context by summarizing completed-sprint stories into a brief `shipped_summary.md` rather than passing full story text. Full story text is only passed for the current sprint.

3. **Token budget enforcement**: each agent call records `input_tokens + output_tokens` in `spend_tracker.py`. If a single agent call exceeds a configurable `max_call_tokens` threshold, it is retried with a compacted prompt. Running totals are emitted in SCRIBE's daily report.

**Execution Plan**

1. Add `context_version: "1.0.0"` to `plan.yaml` schema; bump on every planner write.
2. `orchestrator.py`: build `shipped_summary.md` at start of each day from `.pace/day-*/handoff.yaml` files where `status == SHIPPED`.
3. Pass `shipped_summary.md` content instead of full story files to PRIME, GATE, SENTINEL.
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
6. Acceptance: a 30-day sprint with 20 shipped stories passes PRIME a summary of ≤500 tokens for those stories rather than full text.

---

### Item 4: Auto-Update Mechanism

**Assessment**

PACE is pinned at whatever version was installed at setup time. Bug fixes, new platform support, and agent improvements are only available after a manual `git pull` or re-installation. There is no mechanism to notify users of new versions or to self-update safely.

**Recommendation**

Add a daily version-check with customization-aware update behaviour:

- Once per calendar day, at the start of any PACE pipeline run, query the `pace-framework-starter` GitHub releases API for the latest tag.
- Compare against the installed `PACE_VERSION` constant in `config.py`.
- Before any update, **detect whether PACE core files have local modifications** (git diff against the installed tag). Projects routinely customize `forge.py`, `orchestrator.py`, and `config.py` for their specific needs. Silently overwriting these customizations would be destructive.
- **If no customizations are detected** and a newer version exists: apply the update automatically (lockfile guard still applies).
- **If customizations are detected**: skip the update entirely and emit a prominent WARNING at every pipeline run until resolved:
  ```
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

**Execution Plan**

1. Add `pace/updater.py` with `check_for_update()`, `detect_customizations()`, and `apply_update()`.
2. `check_for_update()`: hits the GitHub releases API; caches result to `.pace/update_check.json` with a TTL of 23 hours.
3. `detect_customizations()`: runs `git diff <installed_tag> -- pace/` and returns a list of modified PACE core files. Any non-empty list blocks auto-update.
4. `apply_update()`: only called when `detect_customizations()` returns empty; git-fetches the new tag; runs `pip install -r requirements.txt -q`; writes the new version to `.pace/update_check.json`.
5. Add pipeline lock: `.pace/pipeline.lock` created at pipeline start, deleted at pipeline end; `apply_update()` aborts if lock exists.
6. `preflight.py`: call `check_for_update()` and `detect_customizations()` at startup; emit WARNING block if newer version available but customizations block update.
7. CONDUIT: include version-update summary in daily report if an update was applied; include deferred-update warning if customizations block it.
8. Reference the upgrade tutorial (`tutorials/updating-customised-pace` in pace-docs) in all WARNING output.
9. Acceptance: (a) with no customizations, a version bump triggers auto-update; (b) with a modified `forge.py`, update is skipped and WARNING lists the file; (c) `updates.suppress_warning: true` silences the WARNING without disabling version checking.

---

### Item 8: Cron Configuration

**Assessment**

Cron schedules for PACE pipelines are currently hardcoded in CI YAML files, requiring manual edits to change frequency. There is no concurrency guard in the framework itself — if a pipeline run takes longer than the cron interval, a second run starts while the first is still in progress, causing race conditions on `.pace/` state files.

**Recommendation**

Centralize cron configuration in `pace.config.yaml` and add a framework-level execution lock:

```yaml
cron:
  pace_pipeline: "0 6 * * 1-5"     # main PACE run (UTC)
  planner_pipeline: "0 7 * * 0"    # weekly re-plan (Sunday)
  update_check: "0 0 * * *"        # daily update check (midnight)
  timezone: "UTC"
```

The CI pipeline generators (GitHub, GitLab, Jenkins) read `cron` from `pace.config.yaml` and regenerate the workflow files when the config changes. A `pipeline.lock` file prevents concurrent runs.

**Execution Plan**

1. Add `cron` section to `pace.config.yaml` schema and `config.py` dataclasses.
2. Add `pace/ci_generator.py`: reads `cron` config and regenerates `.github/workflows/pace.yml` (or `.gitlab-ci.yml`, `Jenkinsfile`) cron triggers.
3. `preflight.py`: acquire `.pace/pipeline.lock` (write PID + timestamp); fail immediately if lock is stale (> 4 hours old, configurable).
4. `orchestrator.py` `finally` block: always release the lock.
5. Add `python pace/ci_generator.py` to `pace-config-test` output as a suggestion if cron fields differ from workflow file.
6. Acceptance: changing `cron.pace_pipeline` in config and running `ci_generator.py` updates the `schedule.cron` field in the generated workflow YAML.

---

## Phase 3 — Integration & Ecosystem

### Item 5: Communication & Alerting

**Assessment**

PACE currently has no outbound communication. Failures, HOLD issues, SHIPPED stories, and daily reports exist only inside GitHub Issues and CI logs. Teams using Slack, Microsoft Teams, or email have no automated way to receive PACE status updates. There is no alerting system for cost overruns, repeated failures, or long-running pipelines.

**Recommendation**

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

**Execution Plan**

1. Define `NotificationAdapter` ABC in `pace/notifications/base.py` with `send(event, payload)`.
2. Implement `SlackAdapter`, `TeamsAdapter`, `EmailAdapter` in `pace/notifications/`.
3. Add `pace/alert_engine.py`: evaluates alert rules against events; dispatches to configured channels.
4. Wire alert engine into `orchestrator.py` at key lifecycle points: HOLD opened, story SHIPPED, spend threshold exceeded, pipeline lock timeout.
5. Add `notifications` and `alerts` sections to `pace.config.yaml` schema and `config.py`.
6. `config_tester.py`: validate webhook URLs are non-empty if adapter is configured; warn if no channels are configured (PACE runs silently).
7. Acceptance: a simulated HOLD event with Slack configured sends a POST to the webhook URL containing the story title, day number, and hold reason.

---

### Item 6: Tracker Artifact Push & Issue Templates

**Assessment**

All PACE artifacts — stories, test plans, handoff data, advisory findings — currently live exclusively in the `.pace/day-N/` directory tree. The configured issue tracker (`tracker_type`) is only used to open HOLD issues; it is never used to push structured story or test artifacts. Teams cannot use their tracker's native search, filtering, or reporting on PACE-generated content.

**Recommendation**

Extend `TrackingAdapter` to push artifacts as tracker items:

- Stories become tracker issues/tickets with structured labels (e.g. `pace:story`, `pace:day-N`, `pace:sprint-M`).
- Acceptance criteria are embedded as a formatted markdown checklist **within the issue body/description**, not as separate sub-tasks or checklist items outside the description. This keeps ACs visible in the issue preview without requiring sub-issue support from the tracker.
- Handoff data (test results, coverage, notes) is posted as a comment on story close.
- Advisory findings can optionally create separate issues (already gated by `advisory.push_to_issues`).
- Custom issue templates for GitHub and GitLab are generated from PACE's story schema.

**Execution Plan**

1. Extend `TrackingAdapter` ABC with `push_story(story)`, `update_story_status(story_id, status)`, `post_handoff_comment(story_id, handoff)`. The `push_story` method constructs the full issue body including story description + a `## Acceptance Criteria` section with `- [ ] AC text` lines. No separate `push_ac` method — ACs are part of the description payload.
2. Implement in `platforms/github.py`, `platforms/gitlab.py`, `platforms/jira.py`.
3. Generate GitHub issue templates (`.github/ISSUE_TEMPLATE/pace_story.yml`) and GitLab equivalents during `pace-planner` run.
4. Add `tracker.push_stories: true` option to `pace.config.yaml` (default: false to preserve existing behavior).
5. CONDUIT: on story SHIPPED, call `update_story_status` and `post_handoff_comment`.
6. Acceptance: with `tracker.push_stories: true` and GitHub configured, a new story creates a GitHub Issue whose **description body** contains a `## Acceptance Criteria` section with all AC items as `- [ ]` checkboxes; closing the story posts a handoff comment.

---

### Item 7: GitLab, Jenkins, and Bitbucket Pipeline Finalization

**Assessment**

`platforms/gitlab.py`, `platforms/jenkins.py`, and `platforms/bitbucket.py` exist but are incomplete stubs. The `ci_generator.py` proposed in Item 8 does not yet have templates for these platforms. Users who prefer GitLab CI or Jenkins cannot use PACE without significant manual work.

**Recommendation**

Finalize pipeline templates and platform adapter implementations for GitLab, Jenkins, and Bitbucket so that a correctly configured `pace.config.yaml` is sufficient to run PACE on any of the four supported platforms.

**Execution Plan**

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

**Assessment**

PACE's agent pipeline is tightly coupled. Adding a new agent, a custom tool, or a domain-specific workflow requires modifying core framework files. This prevents teams from extending PACE without forking the repository. As the ecosystem grows, a plugin system becomes essential for community contributions.

**Recommendation**

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

**Initial Plugin Candidates**

| Plugin | Type | Description |
|--------|------|-------------|
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

**Execution Plan**

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

## Sequencing Summary

```
v2.0-alpha  ──►  Item 1  (Branching Model)
                 Item 2  (PACE Planner)
                 Item 9  (Config Tester)

v2.0-beta   ──►  Item 3  (Context Versioning)
                 Item 4  (Auto-Update)
                 Item 8  (Cron Configuration)

v2.0-rc     ──►  Item 5  (Communications & Alerts)
                 Item 6  (Tracker Artifacts)
                 Item 7  (GitLab/Jenkins/Bitbucket)

v2.1        ──►  Item 10 (Plugin System)
```

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

**The fine-tuning opportunity in brief:**

1. **Dataset collection** (prerequisite: Items 3 + 6 + context versioning): export `story.md` + `forge_checkpoint.json` + `handoff.yaml` triples per shipped story into a training corpus. Filter to only GREEN-phase handoffs (stories that passed GATE without revision). Target: 500–1000 high-quality traces to start.

2. **Supervised fine-tuning (SFT)**: train on `(system_prompt + story + tool_defs, FORGE_conversation_trace)` pairs. The model learns to produce the correct sequence of tool calls (write file, run tests, commit) for a given story type without requiring frontier-model reasoning.

3. **RLHF signal from GATE**: GATE's structured scores (coverage delta, AC coverage, test quality) provide a natural reward signal for reinforcement learning from human feedback — without requiring human labellers. Each GATE evaluation is an automatic quality label.

4. **Cost impact**: a fine-tuned 7B–13B parameter model running locally (via Ollama + the existing LiteLLM adapter) could replace frontier-model FORGE calls entirely for routine stories, reducing per-story cost by 80–95%.

5. **Prerequisites**: the plugin system (Item 10) should expose a `DataExportHook` that streams story traces to a training store; the LiteLLM adapter (already implemented) handles routing to the fine-tuned model once it is deployed.

This is deferred to post-v2.1 because it requires a minimum viable dataset that only accumulates after several months of real PACE usage with the v2.0 feature set in production.

---

*PACE Framework Roadmap v1.0 — 2026-03-13 IST*
*Author: Vipull Meehniaa*