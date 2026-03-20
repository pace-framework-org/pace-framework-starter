# FORGE Context Cost Saving Plan

## Background

FORGE is the highest-cost agent in the PACE pipeline, accounting for 85–95% of per-story spend. Unlike the single-turn analysis agents (PRIME, GATE, SENTINEL, CONDUIT), FORGE runs a multi-iteration tool-calling loop — each iteration sends the entire conversation history to the Anthropic API from scratch. As the loop progresses, input token count grows continuously, and cost compounds with every iteration.

This plan documents the root cause analysis, the three identified context growth drivers, six mitigation options, and the recommended implementation order — derived from a live production run (Day 23, nolapse-platform).

---

## Case Study: Day 23 — `nolapse run --lang python` Coverage Extraction

**Story:** CLI parses `--lang python`, invokes Python coverage runner, reads `.coverage`/`coverage.json`, computes delta vs baseline.

**Run history (4 attempts before SHIP):**

| Run | Outcome | Cost |
|-----|---------|------|
| 1 | HOLD — FORGE did not call `complete_handoff` after 35 iterations | $9.05 |
| 2 | HOLD — FORGE did not call `complete_handoff` after 35 iterations | $7.79 |
| 3 | HOLD — FORGE did not call `complete_handoff` after 50 iterations | $12.21 |
| 4 | **SHIP** | $13.09 |
| **Total** | | **$42.14** |

**Run 4 (the SHIP run) — FORGE cost: $5.97 across 33 iterations**

Context growth across the 33 iterations:

```
Iter  1:   4,510 input tokens   (story card + system prompt + 2 file reads)
Iter 13:  38,683 input tokens   (+ 11 more reads — exploration complete, nothing written yet)
Iter 22:  57,472 input tokens   (+ 2 writes to run.go — 16k chars now in history)
Iter 33:  68,995 input tokens   (+ 9 consecutive test runs, all showing PASS)
```

Input tokens grew **15× over 33 iterations**. Output tokens were relatively flat (44–5,030 per iteration). Context accumulation, not response generation, was the dominant cost driver.

---

## The Three Context Growth Drivers

Analysis of the Day 23 message history identified three distinct causes of context growth:

| Driver | Estimated tokens added | Iterations |
|--------|----------------------|------------|
| **Stale file reads** — `read_file` results remain in history after the file is overwritten | ~20,000 | 1–13, 19, 21 |
| **Accumulated test output** — each `run_bash(pytest/go test)` adds 1–3k tokens; prior runs are obsolete but stay | ~18,000 | 6, 11, 16, 17, 25–33 |
| **Write echo accumulation** — `write_file` tool results (full file content) persist in history after the write | ~12,000 | 14, 15, 20, 22, 23, 24 |

The Anthropic API is stateless — every `chat()` call in `anthropic_adapter.py` sends the complete `messages` list. There is no server-side session; context reduction must happen client-side in `forge.py` before each API call.

---

## Option 1 — Stale File Read Eviction

**Concept:** When FORGE calls `write_file(path)`, any prior `read_file(path)` or `write_file(path)` tool result in the message history is now stale — FORGE wrote the new version and knows its contents. Evict those entries from the messages list before the next `adapter.chat()` call.

**Where:** `forge.py` — scan messages before each `adapter.chat()` call; remove tool results whose associated path has since been overwritten.

**Day 23 example:** `run.go` was read in iteration 1 (~4,500 chars), re-read in iteration 21, then overwritten in iteration 22. Both reads accumulated through all subsequent iterations. Evicting them after iteration 22 removes ~2,600 tokens from each of iterations 23–33 (11 iterations) — approximately 28,600 tokens eliminated.

| Metric | Value |
|--------|-------|
| Estimated token reduction (Day 23) | ~20,000 tokens (~29%) |
| Implementation effort | Low |
| Quality risk | Low — FORGE wrote the file; the prior content is superseded |

---

## Option 2 — Test Output Deduplication

**Concept:** Keep only the most recent tool result for each unique command. When FORGE runs the same test command five times, the first four results are obsolete the moment the fifth arrives. Replace rather than accumulate.

**Where:** `forge.py` — maintain a `_last_result_index` dict keyed by `(tool_name, normalized_command)`. When a new result arrives for the same key, find and replace the old entry in the messages list.

**Day 23 example:** FORGE ran test suites 9 times in iterations 25–33, each run adding ~1,500 tokens to a context where the prior run was already irrelevant.

| Metric | Value |
|--------|-------|
| Estimated token reduction (Day 23) | ~12,000 tokens (~17%) |
| Implementation effort | Low |
| Quality risk | Low for test commands (idempotent, FORGE only cares about latest output) |

**Note:** Key normalisation is important. `pytest test_coverage_runner_conduit.py -v` and `pytest test_coverage_runner_conduit.py` should be treated as the same command for deduplication purposes.

---

## Option 3 — Write Receipt Suppression

**Concept:** `write_file` tool results currently persist in message history. The full written content is not needed after confirmation — FORGE produced it and knows what it wrote. Replace full-content write receipts with a compact acknowledgement: `"OK: wrote N bytes to path"`.

**Where:** `forge.py` tool result handling — strip file content from write receipts immediately before appending to the messages list. Retain path, byte count, and success status only.

**Day 23 example:** Six `write_file` calls in iterations 14, 15, 20, 22, 23, 24 wrote files of sizes 8,934 / 5,258 / 12,595 / 16,193 / 5,187 / 2,599 bytes respectively. At ~3.5 chars/token, those write receipts added ~14,800 tokens to every subsequent iteration's context.

| Metric | Value |
|--------|-------|
| Estimated token reduction (Day 23) | ~14,800 tokens (~21%) |
| Implementation effort | Very low |
| Quality risk | Very low — FORGE knows the file content; only the confirmation is needed |

**Combined saving (Options 1 + 2 + 3):** ~46,800 tokens removed from Day 23 (~68% of total input growth). These three options are additive, non-conflicting, and carry no quality risk. They should be implemented as a unit before considering Options 4–6.

---

## Option 4 — Sliding Window with Haiku Compression

**Concept:** After a threshold is crossed (e.g., context exceeds 30k input tokens), call Haiku to compress the oldest N message pairs into a compact structured YAML summary. Replace those turns with the summary and continue. One compression trigger per run, not rolling.

**Estimated token reduction (Day 23):** ~20,000 tokens (~29%) — compressing iterations 1–10 after RED phase confirmation reduces history from ~38,000 tokens to ~18,000 before GREEN implementation begins.

**Additional cost:** ~$0.002–0.004 per compression call (Haiku, ~2k-token prompt).

### Risk Mitigations

| # | Mitigation | Implementation complexity | Looped risk |
|---|-----------|--------------------------|-------------|
| 4a | **Compress only after `confirm_red_phase`** — `red_phase_confirmed` boolean already exists in `forge.py`; gate the trigger on it | Low | If TDD is off or it's a clearance story, `confirm_red_phase` is never called → compression never triggers → zero benefit for those story types |
| 4b | **Structured YAML compression schema** — force Haiku to output typed fields (`files_read`, `symbols_noted`, `issues_confirmed`, `tests_written`, `test_status`) rather than prose | Medium | Haiku can hallucinate field values — inventing symbol names or file paths. FORGE trusts the summary and references fabricated details. Schema validation catches structure; it cannot validate content truth |
| 4c | **Keep last 5 turns verbatim** — only compress turns older than 5 iterations back | Low | "5" is arbitrary and unvalidated. If a critical detail was in turn 6, it is still compressed. Threshold requires empirical tuning across story types |
| 4d | **Retain `write_file` results** — never compress write receipts; only compress `read_file` and `run_bash` results | Low | Negligible — write receipts are small and factual |
| 4e | **Single trigger per run** — one boolean flag `_compressed`; do not trigger again after first compression | Low | If triggered too early (e.g., iteration 12 of 33), FORGE loses context it still actively needs. If too late (iteration 28), most compounding cost has already been paid. Threshold requires empirical calibration |

**Which mitigations to implement:** All five. 4a, 4c, 4d are trivial and collectively close the main failure modes. 4b is required — unstructured prose summaries from Haiku are the highest-risk path and must be avoided. 4e is a one-line flag that prevents double-compression. Running Option 4 without 4b is not safe to ship.

---

## Option 5 — Pre-seeded File Map from engineering.md

**Concept:** SCRIBE already maintains `engineering.md` — a structured module map of the codebase. Inject a curated subset of it into the initial FORGE user message as `suggested_starting_files`. FORGE reads the relevant files directly in iteration 1–2 instead of spending 10–13 iterations discovering the codebase through exploration.

**Day 23 example:** Iterations 1–13 were pure exploration — 13 iterations before a single file was written. If FORGE had started with a map pointing to `run.go`, `coverage_runner.py`, `ci.yml`, and the test files, iterations 1–4 would have covered the same ground as iterations 1–13, collapsing the exploration phase.

**Estimated token reduction (Day 23):** ~10,000 tokens (~14%) — 9 fewer exploration iterations, each compounding less context into the subsequent write phase.

### Risk Mitigations

| # | Mitigation | Implementation complexity | Looped risk |
|---|-----------|--------------------------|-------------|
| 5a | **Map as hints, not constraints** — explicit instruction: "These are suggested starting points. You may read any file you need — do not limit yourself to this list" | Low | FORGE may ignore hints entirely (zero benefit) or over-trust them and skip a required unlisted file (quality risk). The hint framing limits the over-trust failure but not the ignore failure |
| 5b | **Include `scribe_generated_at` timestamp; skip injection if map age exceeds sprint cadence** — read metadata already written by SCRIBE in `forge.py` | Low | Age is a weak proxy for accuracy. A 6-day-old map may be perfectly accurate; a 1-day-old map may be stale after a major refactor. Provides false confidence in recently-generated but inaccurate maps |
| 5c | **SCRIBE emits `map_confidence: high/medium/low`** — SCRIBE self-assesses confidence; `forge.py` skips injection when `low` | Medium-High | LLMs are systematically overconfident in self-assessment. SCRIBE will emit `high` even when the map is partially wrong. High implementation cost for unreliable signal — **do not implement** |
| 5d | **Cap to 5 files + `related_modules` freetext** — inject at most 5 files; SCRIBE adds a `related_modules` hint for adjacent context | Low | 5 files may be insufficient for cross-cutting stories. FORGE still needs to explore for the remaining files — cap prevents bloat in the injection but does not guarantee full coverage |
| 5e | **Day 1 no-op fallback** — if `engineering.md` absent, skip injection entirely | Trivial | None |

**Which mitigations to implement:** 5a, 5b, 5d, 5e. **Skip 5c** — SCRIBE confidence self-assessment has high implementation cost and low reliability. Age-based freshness check (5b) plus file cap (5d) are a practical substitute that closes the worst-case stale-map scenario without requiring LLM self-evaluation.

---

## Option 6 — Forked Subcontext (Exploration + Implementation Phases)

**Concept:** Split the FORGE loop into two separate API contexts with a structured handoff between them:

1. **Exploration context** — FORGE reads files and produces a `commit_plan` YAML: files to write, tests to write, approach summary. Runs until `commit_plan` is called. Context is discarded after.
2. **Implementation context** — fresh context starts with `system prompt + story card + plan`. FORGE executes writes and test runs only. No file reads accumulate in history because the plan was built up front.

The implementation context starts at ~5,000 tokens instead of ~38,000. In Day 23 terms, this caps the implementation context at ~30,000 tokens total instead of 68,995.

**Estimated token reduction (Day 23):** ~30,000 tokens (~43%) on the successful SHIP run alone. On the three HOLDs before it, the saving compounds further since exploration context is discarded rather than checkpointed.

### Risk Mitigations

| # | Mitigation | Implementation complexity | Looped risk |
|---|-----------|--------------------------|-------------|
| 6a | **Haiku validates plan against acceptance criteria before implementation starts** — new inter-phase Haiku call checks each criterion has a corresponding `test_to_write` entry; rejects plan if incomplete | High | Haiku approves bad plans (false positive — evaluates alignment on paper, not executability). Haiku over-rejects valid plans (false negative) → FORGE loops in exploration → hits 8-iteration cap → falls back to monolithic frequently. Adds a new rejection/retry coordination layer between the two phases |
| 6b | **Structured `commit_plan` schema** — typed YAML with mandatory fields (`files_to_write[]`, `tests_to_write[]`, `approach_summary`, `files_to_read_in_implementation[]`); JSON schema validated in `forge.py` | Medium | Schema completeness ≠ plan correctness. A fully valid schema can still encode an architecturally wrong plan. Creates a false sense of validation — the guard passes but the plan fails in GATE. Should be treated as a necessary-but-not-sufficient safety check |
| 6c | **`read_file` in implementation context routes to scratchpad** — `read_file` calls during implementation write to `.pace/forge_scratchpad.md` rather than accumulating in API message history | Medium-High | The scratchpad grows unboundedly if FORGE reads many files during implementation — same accumulation problem one level removed. Requires its own size cap, which reintroduces the truncation/eviction problem |
| 6d | **8-iteration hard cap on exploration + monolithic fallback** — if `commit_plan` not called within 8 iterations, abandon forked mode and continue as standard FORGE loop | Low | Complex stories legitimately require 10–13 exploration iterations (Day 23 used 13). For precisely the stories with worst context growth, monolithic fallback triggers most often — the option provides no benefit where it is needed most |
| 6e | **Checkpoint stores plan + implementation messages separately** — checkpoint format extended to `{plan, implementation_messages, implementation_iteration}`; retry resumes implementation phase without re-exploration | High | If HOLD reason is architectural ("wrong approach") rather than a code fix, reusing the plan from checkpoint is incorrect. Orchestrator must classify HOLD reasons to decide whether to re-explore or re-implement. Misclassification causes FORGE to retry with the plan that caused the HOLD |
| 6f | **Inject Option 5 file map into exploration context** — if Option 5 is already built, pass the file map hint into the exploration phase to collapse it to 3–4 iterations | Low (if Option 5 built) / Medium (standalone) | Compounds the risks of both options. If the file map is stale and the exploration phase commits to files based on it, the plan is wrong before implementation starts — and checkpoint saves that wrong plan for all future retries |

**Which mitigations to implement:** Do not build all six at once.

**Phase A (before first production use):** 6b + 6d — the schema validation and hard cap are non-negotiable safety rails. Without 6d, a failed exploration has no escape valve. Without 6b, the plan has no structural validation. Combined effort: ~1 week.

**Phase B (after Phase A validates in production):** 6e — retry reliability is required for production use without manual intervention. Implement HOLD reason classification before enabling `commit_plan` checkpoint. Effort: ~1 week.

**Phase C (once core is stable):** 6a and 6c — Haiku plan validation adds meaningful coverage; the scratchpad reduces implementation context further. Both need their own mitigation work (6a needs false-negative rate measurement; 6c needs scratchpad size cap). Effort: ~1.5 weeks.

**6f:** Only add if Option 5 is already in production. Do not build standalone.

---

## Summary Table

| Option | What it does | Token reduction (Day 23) | Implementation effort | Quality risk |
|--------|-------------|--------------------------|----------------------|--------------|
| **1 — Stale file eviction** | Removes superseded `read_file` results after a `write_file` to the same path | ~20,000 (~29%) | Low | Low |
| **2 — Test deduplication** | Keeps only the latest result for each repeated test command | ~12,000 (~17%) | Low | Low |
| **3 — Write receipt suppression** | Replaces full write echoes with compact `OK: wrote N bytes` receipts | ~14,800 (~21%) | Very low | Very low |
| **4 — Haiku compression** | Compresses iterations 1–N into a structured YAML summary after RED phase | ~20,000 (~29%) | Medium | Medium (mitigable) |
| **5 — Pre-seeded file map** | Injects `engineering.md` file hints to collapse the exploration phase | ~10,000 (~14%) | Medium | Medium (mitigable) |
| **6 — Forked subcontext** | Splits exploration and implementation into separate API contexts | ~30,000 (~43%) | High | High (phased mitigation required) |

**Options 1 + 2 + 3 combined:** ~46,800 tokens (~68% of Day 23 input growth) with no quality risk.
**Options 1 + 2 + 3 + 4:** ~66,800 tokens (~97% of Day 23 input growth).
**Options 1 + 2 + 3 + 6 (fully mitigated):** Near-elimination of compounding context growth as a cost driver.

---

## Recommended Implementation Order

### Stage 1 — Low-hanging fruit (implement together, 2–3 days)
**Options 1, 2, 3** — All changes are in `forge.py` before the `adapter.chat()` call. No new tools, no new agents, no API changes. Eliminates ~68% of context growth on Day 23 with zero quality risk. Validate in production before proceeding.

### Stage 2 — Compression layer (1 week)
**Option 4** with all five mitigations (4a–4e). Requires a Haiku compression call and prompt engineering for the structured schema. Gate behind `confirm_red_phase` confirmation. Adds incremental saving on top of Stage 1 for long-running loops.

### Stage 3 — Exploration collapse (1 week)
**Option 5** with mitigations 5a, 5b, 5d, 5e (skip 5c). Requires SCRIBE to emit a structured file map and `forge.py` to inject it into the initial user message. Reduces exploration iterations from ~13 to ~3–4 for stories on well-mapped codebases.

### Stage 4 — Forked subcontext (3–4 weeks, phased)
**Option 6** with Phase A (6b + 6d) first, validated before Phase B (6e), then Phase C (6a + 6c). Architectural change to the FORGE loop. Only justified if Stage 1–3 are insufficient — which the production data will determine.

---

## Notes

- All token reduction estimates are derived from the Day 23 checkpoint (`forge_checkpoint.json`, 33 iterations, 67 messages). Actual savings will vary by story complexity and iteration count. Complex stories with more iterations will benefit proportionally more.
- Prompt caching (already implemented in `anthropic_adapter.py`) addresses the **system prompt** cost. The options above address the **message history** cost. They are orthogonal and additive.
- The cost of the Day 23 run ($5.97 for Run 4 alone; $42.14 total across all 4 attempts) makes this the highest-priority cost reduction surface in the PACE pipeline. Analysis agents combined cost less than $0.05 per story.
