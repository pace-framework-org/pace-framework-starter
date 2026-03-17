# Changelog

All notable changes to the PACE Framework Starter are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

---

## [v2.1.0] — 2026-03-17

### Added
- `.pacemap/` directory: `ROADMAP.md` and `ROADMAP-EXECUTION-LOG.md` moved from repo root; `versions/` subdirectory for immutable snapshots (Item 17)
- `pace/pacemap.py`: `snapshot_roadmap()`, `snapshot_roadmap_if_version_changed()`, `update_changelog()`, `update_changelog_story_shipped()` (Items 17 + 18)
- `CHANGELOG.md` at repo root with full history; auto-updated by `pacemap.py` on story SHIP and planner completion (Item 18)
- `config_tester.py` warns when `CHANGELOG.md` is absent from repo root (Item 18)
- `pace-planner.yml`: CI workflow YAML syntax fixed — multi-line git commit message and PR body heredoc rewritten to avoid YAML block scalar column-0 errors

### Changed
- `pace/ci_generator.py`: `generate(apply=True)` now calls `_maybe_snapshot_roadmap()` to snapshot `.pacemap/ROADMAP.md` whenever the Roadmap Version header changes
- `pace/config_tester.py`: cross-references updated from `ROADMAP.md` → `.pacemap/ROADMAP.md`

---

## [v2.0.0] — 2026-03-16

### Added
- All 11 deferred steps from Items 1–8 implemented (Deferred Steps Cleanup sprint, PR #21):
  - `orchestrator.py`: `_try_open_staging_pr()` — opens sprint→release PR after CONDUIT SHIP + passing CI
  - `preflight.py`: `_check_branch_protection()` — non-fatal stdlib-only GitHub branch protection check
  - `agents/prime.py`: `plan_diff` parameter injected into PRIME user message for `PACE_REPLAN=true`
  - `agents/scribe.py`: `_write_scribe_report()` — emits `.pace/scribe_report.yaml` after SCRIBE completes
  - `llm/anthropic_adapter.py`: token limit retry — catch `BadRequestError`, compact user message to 60%, retry once
  - `updater.py`: `_write_update_status()`, `_clear_update_status()`, `_fire_update_available_event()`; fixed placeholder docs URL
  - `reporter.py`: `_load_update_status()` + "PACE Update Available" section in `write_job_summary()`
  - `config_tester.py`: suggest `ci_generator.py --check` in `_validate_cron()` when no cron errors

---

## [v1.1.0] — 2026-03-15

### Added
- Plugin system with `pace/plugins/base.py` and hook dispatching (Item 10, PR #11)
- Training data pipeline: `pace/training/` — `collector.py`, `exporter.py`, `hook.py` for SFT/reward dataset export (Item 11, PR #12)
- Platform finalization: GitHub Actions, GitLab CI, Jenkins, Bitbucket Pipelines adapters production-ready (Item 7, PR #10)
- Tracker artifact push: JIRA, Linear, GitHub Issues push after SHIP (Item 6, PR #8)

---

## [v1.0.0] — 2026-03-14

### Added
- Sprint/release branching model: `branching.py` with `get_branching_adapter()` (Item 1, PR #2)
- PACE Planner pipeline: `planner.py` with re-plan support; `pace-planner.yml` GitHub Actions workflow (Item 2, PR #3)
- Context versioning: `context.py` with version tracking and `context_version` field in `plan.yaml` (Item 3, PR #4)
- Auto-update mechanism: `updater.py` — checks for new framework versions, applies non-breaking updates (Item 4, PR #5)
- Communications and alerting: `alert_engine.py` with Slack, Teams, email adapters; `AlertEngine.fire()` (Item 5, PR #7)
- Cron configuration: `pace.config.yaml` `cron:` section; `ci_generator.py` keeps CI workflow cron in sync (Item 8, PR #6)
- Configuration tester: `config_tester.py` with hard errors, warnings, and suggestions (Item 9, direct commit `75f25b0`)

### Fixed
- Timestamp precision in orchestrator cycle artifacts (pre-ROADMAP fix, PR #1)
