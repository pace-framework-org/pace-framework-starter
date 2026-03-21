# PACE Documentation Roadmap — Phase 7

**Author:** Vipul Meehnia
**Created:** 2026-03-20 (IST — Asia/Kolkata)
**Aligned With:** ROADMAP v1.6 (Phase 7, Items 19–26)
**Docs Repo:** `pace-docs/src/content/docs/`

> Each Phase 7 item has documentation work that must ship **with or before**
> the code PR merges to main. This file tracks what needs to be written,
> updated, or extended — and why each change is necessary.

---

## Gap Analysis

### What Phase 7 adds to the framework

| Item | New capability | User-visible change |
| ---- | -------------- | ------------------- |
| 19 | SCRIBE runs during planner CI | Plan-approval PR contains fresh context docs |
| 20 | SCRIBE runs before human-gate PR | Review PR contains fresh context docs |
| 21 | Stale read eviction in FORGE | Lower per-story cost; no config needed |
| 22 | Test output dedup in FORGE | Lower per-story cost; no config needed |
| 23 | Write receipt suppression | Lower per-story cost; no config needed |
| 24 | Haiku context compression | `compression_model` config key; behaviour change |
| 25 | Pre-seeded file hints | `file_hints_enabled` config key; `disable_file_hints` in plan.yaml |
| 26 | Forked FORGE subcontext | `fork_enabled` config key; new `commit_plan` tool in FORGE |

### Existing docs that are now incomplete

| File | Gap | Triggered by |
| ---- | --- | ------------ |
| `guides/day-zero.md` | Does not mention context refresh on plan-approval PR | Item 19 |
| `guides/human-gate-workflow.md` | Does not mention SCRIBE running before review PR | Item 20 |
| `concepts/scribe-and-context.md` | Only describes Day 1 initialisation; missing planner/gate triggers | Items 19–20 |
| `concepts/token-efficiency.md` | No section on FORGE message-history management | Items 21–26 |
| `reference/pace-config-yaml.md` | Missing `forge.compression_model`, `forge.file_hints_enabled`, `forge.fork_enabled` keys | Items 24–26 |
| `reference/plan-yaml.md` | Missing `disable_file_hints` story-level field | Item 25 |

### Docs that do not exist yet

| File | Purpose | Triggered by |
| ---- | ------- | ------------ |
| `guides/context-refresh.md` | Full guide to when/how SCRIBE refreshes context docs | Items 19–20 |
| `guides/forge-context-efficiency.md` | Guide to the three growth drivers + all six options | Items 21–26 |

---

## Documentation Items

### Doc-1: New guide — `guides/context-refresh.md`

**Ships with:** Items 19 + 20 (Sprint 7.1)
**Type:** New file

#### What to cover

- Why context docs go stale between sprint planning sessions (brief recap of
  SCRIBE's role; link to `concepts/scribe-and-context.md`)
- **Planner-triggered refresh (Item 19):**
  - When it fires: `run_pipeline()` detects stale hashes or missing docs
  - What happens: SCRIBE runs, docs committed to plan-approval branch
  - What the reviewer sees: refreshed `engineering.md` diff in the plan-approval PR
  - Log output to look for: `[PACE][Planner] Context refreshed: engineering.md, security.md`
  - Non-fatal: if SCRIBE fails, planner continues and PR body notes the failure
- **Human-gate-triggered refresh (Item 20):**
  - When it fires: story has `human_gate: true`; fires before `open_review_pr()`
  - What happens: SCRIBE runs; docs committed to working branch; review PR
    includes `## Context` section listing docs refreshed
  - Log output: `[PACE] Human gate — refreshing context docs before review PR`
  - Non-fatal: PR opens even on SCRIBE failure (warning in PR body)
- **Manual refresh:**
  - `python pace/orchestrator.py --refresh-context` (already exists via
    `force_refresh_context()`) — documents this CLI path
- **Cost of a SCRIBE refresh:**
  - Single run ~$0.02–0.08 (Haiku); included in daily spend

#### Acceptance criteria for this doc

- Explains both trigger points (planner, human gate) with concrete log examples
- Explains the non-fatal fallback behaviour for both
- Links to `guides/day-zero.md` and `guides/human-gate-workflow.md`
- Has a "Troubleshooting" section: what to do if SCRIBE fails during planner CI

---

### Doc-2: Update `guides/day-zero.md`

**Ships with:** Item 19 (Sprint 7.1)
**Type:** Update existing

#### What to add

After the existing "What the planner does" section, add a `### Context refresh`
subsection:

- The planner CI checks whether context docs are stale before estimating costs
- If stale, SCRIBE runs and the refreshed docs appear in the plan-approval PR diff
- Reviewers can inspect `engineering.md` alongside the cost estimates to verify
  that PRIME will have accurate context on Day 1
- Link to `guides/context-refresh.md` for full behaviour details

#### Acceptance criteria

- New subsection fits naturally after "What the planner does"
- Does not duplicate content from `guides/context-refresh.md`

---

### Doc-3: Update `guides/human-gate-workflow.md`

**Ships with:** Item 20 (Sprint 7.1)
**Type:** Update existing

#### What to add

In the "What happens when a human gate is reached" section, add a step:

> Before opening the review PR, PACE invokes SCRIBE to refresh the context
> documents. The refreshed `engineering.md`, `security.md`, `devops.md`, and
> `product.md` appear in the review PR diff — giving reviewers an accurate
> snapshot of the codebase state at the gate point.

Also add a new `### Context in the review PR` subsection explaining:

- Why context docs are refreshed at this point (reviewer needs accurate module map)
- The `## Context` section in the PR body (docs refreshed, source files that
  triggered the refresh, SCRIBE cost)
- What to do if the context refresh failed (warning in PR body; proceed with
  review using existing docs or trigger manual refresh)

#### Acceptance criteria

- New content fits in the existing "What happens" flow
- PR body `## Context` section format is shown with an example

---

### Doc-4: Update `concepts/scribe-and-context.md`

**Ships with:** Items 19 + 20 (Sprint 7.1)
**Type:** Update existing

#### What to add

The existing doc only covers Day 1 initialisation and the `_check_context_freshness()`
path. Add a `## When SCRIBE runs` section with a clear trigger table:

| Trigger | Condition | Non-fatal? |
| ------- | --------- | ---------- |
| Day 1 preflight | Context docs missing | No — ABORT if SCRIBE fails |
| Preflight freshness check | Source-doc SHA-256 changed | Yes — continue with stale docs on failure |
| Planner CI (Item 19) | Stale/missing docs at sprint planning | Yes — planner continues |
| Human gate (Item 20) | Story has `human_gate: true` | Yes — PR opens |
| Manual (`--refresh-context`) | Always | Yes |

Also extend the "How SCRIBE updates context" section to note that post-Item 19/20,
SCRIBE may run multiple times per sprint (once per planning cycle and once per
human gate story) rather than only on Day 1.

#### Acceptance criteria

- Trigger table is accurate and complete
- Existing Day 1 and freshness-check content is preserved and cross-linked
- The "non-fatal" column is explained in prose below the table

---

### Doc-5: New guide — `guides/forge-context-efficiency.md`

**Ships with:** Items 21 + 22 + 23 (Sprint 7.2); extended for Items 24–26

#### Phase 1 content (ships with Sprint 7.2)

- **The context growth problem:** brief recap of the three drivers (stale reads,
  test accumulation, write echoes) with the Day 23 token growth chart as a
  concrete example
- **What Stage 1 does:**
  - Stale file read eviction: what it evicts, when, what the log shows
  - Test output deduplication: what "same command signature" means, what the log
    shows
  - Write receipt suppression: what the receipt string looks like, that file
    content on disk is unaffected
- **No configuration needed:** Stage 1 is always on; document that it is
  transparent to users
- **Expected savings:** "~60–65% reduction in FORGE input token growth vs
  baseline"
- **Monitoring:** how to read the per-iteration debug log lines

#### Phase 2 additions (ships with Item 24, Sprint 7.3)

Add `### Haiku context compression (Stage 2)` subsection:

- What the compression trigger is (first RED-phase test failure)
- What the YAML summary contains (files_read, files_written, plan_committed,
  key_decisions)
- The `compression_model` config key; defaults to `analysis_model`
- Expected additional savings: "~29% further reduction"
- When compression does NOT fire (failure fallback: original history preserved)

#### Phase 3 additions (ships with Item 25, Sprint 7.4)

Add `### Pre-seeded file hints (Stage 3)` subsection:

- What "file hints" are (not constraints — FORGE uses its own judgement)
- The `## File Hints` section in FORGE's initial message
- Configuration: `forge.file_hints_enabled`, `forge.file_hints_confidence_threshold`
- Per-story override: `disable_file_hints: true` in plan.yaml story entry
- When hints are skipped: absent/stale `engineering.md`, low confidence, disabled
- Expected savings: "reduces exploration phase from ~13 iterations to 3–4"

#### Phase 4 additions (ships with Item 26 Phase A, Sprint 7.5)

Add `### Forked subcontext (Stage 4)` subsection:

- What the fork means: exploration and implementation in separate API contexts
- The `commit_plan` tool: what FORGE must emit before any `write_file`
- The `fork_enabled` config key (default `false` — opt-in)
- Single-context fallback: what happens if `commit_plan` not called in time
- Expected savings: "~43% reduction in implementation-phase context"
- Migration guidance: how to enable incrementally (Phase A only first)

#### Acceptance criteria for Doc-5

- Phase 1 content is self-contained and useful without Stages 2–4
- Each stage section is clearly marked (e.g. `> Available from v3.1`, `v3.2`, `v3.3`)
- No duplication with `concepts/token-efficiency.md` (link to it for background)

---

### Doc-6: Update `concepts/token-efficiency.md`

**Ships with:** Items 21–23 (Sprint 7.2)
**Type:** Update existing

#### What to add

The existing doc covers session-level context design but has no section on FORGE's
internal message-history management. Add `## FORGE context management` section
before the existing `## Summary` table:

- The three growth drivers (stale reads, test accumulation, write echoes) with
  the per-driver token estimates from the Day 23 case study
- A table showing Stage 1–4 savings stacked:

| Stage | Option | Tokens saved | Cumulative reduction |
| ----- | ------ | ------------ | -------------------- |
| 1 | Eviction + dedup + suppression | ~47,000 | ~68% |
| 2 | Haiku compression | ~20,000 | ~97% |
| 3 | Pre-seeded hints | ~10,000 | reduces exploration phase |
| 4 | Forked subcontext | ~30,000 | fresh implementation baseline |

- Link to `guides/forge-context-efficiency.md` for configuration and monitoring

Also update the summary comparison table at the bottom to add a row:
`FORGE message-history management | No (unbounded) | Stage 1: automatic; Stage 2–4: configurable`

#### Acceptance criteria

- New section is consistent with the existing token-efficiency framing
- Savings table uses data from FORGE-COST-SAVING-PLAN.md (Day 23 case study)

---

### Doc-7: Update `reference/pace-config-yaml.md`

**Ships with:** Items 24, 25, 26 (Sprints 7.3–7.5, one update per sprint)
**Type:** Update existing (three incremental updates)

#### Sprint 7.3 additions (Item 24)

Under the `forge:` config section, add:

```yaml
forge:
  compression_model: claude-haiku-4-5-20251001  # model for Haiku compression
                                                  # defaults to analysis_model
```

Document: default value, when it is used, cost impact (~$0.005 per compression).

#### Sprint 7.4 additions (Item 25)

```yaml
forge:
  file_hints_enabled: true           # inject file hints from engineering.md
  file_hints_confidence_threshold: 0.7  # skip hints below this confidence
```

Document: default values, what "confidence" means, when to lower/raise the
threshold.

#### Sprint 7.5 additions (Item 26)

```yaml
forge:
  fork_enabled: false                    # opt-in forked subcontext
  fork_trigger_max_iterations: 20        # iterations before fallback
  fork_exploration_max_iterations: 20    # iterations before synthetic commit_plan
```

Document: default values, phased enablement recommendation (Phase A only first).

#### Acceptance criteria

- Each new key has: type, default, description, example value
- Related keys are grouped under the existing `forge:` section header

---

### Doc-8: Update `reference/plan-yaml.md`

**Ships with:** Item 25 (Sprint 7.4)
**Type:** Update existing

#### What to add

Under the per-story fields table, add `disable_file_hints`:

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `disable_file_hints` | `bool` | `false` | Skip file hint injection for this story. Use for architectural stories that intentionally explore broadly. |

Include a usage example showing when to set it (e.g. greenfield module creation
where no existing file map is relevant).

#### Acceptance criteria

- New field appears in the per-story fields table
- Example shows a realistic architectural story using it

---

## Delivery Schedule

| Doc item | Dependency | Ships with sprint |
| -------- | ---------- | ----------------- |
| Doc-1 (context-refresh.md NEW) | Items 19+20 | Sprint 7.1 |
| Doc-2 (day-zero.md update) | Item 19 | Sprint 7.1 |
| Doc-3 (human-gate-workflow.md update) | Item 20 | Sprint 7.1 |
| Doc-4 (scribe-and-context.md update) | Items 19+20 | Sprint 7.1 |
| Doc-5 Phase 1 (forge-context-efficiency.md NEW) | Items 21+22+23 | Sprint 7.2 |
| Doc-6 (token-efficiency.md update) | Items 21+22+23 | Sprint 7.2 |
| Doc-7 Part 1 (pace-config-yaml.md — compression_model) | Item 24 | Sprint 7.3 |
| Doc-5 Phase 2 extension | Item 24 | Sprint 7.3 |
| Doc-7 Part 2 (pace-config-yaml.md — file_hints) | Item 25 | Sprint 7.4 |
| Doc-8 (plan-yaml.md — disable_file_hints) | Item 25 | Sprint 7.4 |
| Doc-5 Phase 3 extension | Item 25 | Sprint 7.4 |
| Doc-7 Part 3 (pace-config-yaml.md — fork_enabled) | Item 26 Phase A | Sprint 7.5 |
| Doc-5 Phase 4 extension | Item 26 Phase A | Sprint 7.5 |

---

## What Does NOT Need New Docs

| Area | Reason |
| ---- | ------ |
| Items 21, 22, 23 individual behaviour | Covered by Doc-5 and Doc-6; no config knobs |
| SCRIBE cost from Item 19/20 invocations | Already tracked by spend_tracker; budget-cap.md does not need updating |
| `context.manifest.yaml` format | Already documented in concepts/scribe-and-context.md (Item 12) |
| `forge_trigger_max_iterations` fallback | Covered in Doc-5 Phase 4; no separate guide needed |

---

*PACE DOCS-ROADMAP v1.0 — 2026-03-20 IST*
*8 documentation items across 5 new/updated files; delivery tied to Phase 7 sprints*
