# PACE Token Saving — Decision Log

## Overview

Three token-saving techniques were evaluated for the PACE framework: (1) **prompt caching extensions** — wrapping system prompts in `cache_control: ephemeral` so the Anthropic API reuses KV state across repeated calls with the same system prompt; (2) **streaming** — switching both `complete()` and `chat()` to use the Anthropic streaming API so text is printed to stdout as it is generated; and (3) **batch API** — submitting groups of independent LLM calls as a single batch job to receive a ~50% price discount at the cost of asynchronous, multi-run state management. Phases 1 and 2 were implemented. Phases 3 and 4 (batch API) were declined by the owner.

## Phases

### Phase 1 — Prompt Caching Extensions

Status: Implemented

Changes made:

- `pace/llm/anthropic_adapter.py` — `complete()` now wraps the system prompt in `cache_control: ephemeral` (matching the existing behaviour in `chat()`). The PLANNER calls `complete()` N times with the same large system prompt, so calls 2+ hit the cache and pay only 10% of normal input-token cost for those tokens.
- `pace/llm/anthropic_adapter.py` — both `complete()` and `chat()` now pass `cache_read` and `cache_create` counts from `response.usage` to `spend_tracker.record()`.
- `pace/spend_tracker.py` — `record()` accepts two new keyword args: `cache_read: int = 0` and `cache_create: int = 0`. Both are stored in each record dict.
- `pace/spend_tracker.py` — `total_usd()` prices cache tokens correctly: cache_read at 10% of the model's input rate, cache_create at 125% of the model's input rate.
- `pace/spend_tracker.py` — `summary()` shows per-model cache columns (`X cache_read + W cache_create`) when at least one record in the session has non-zero cache tokens; the columns are omitted otherwise for backwards compatibility with non-Anthropic providers.
- `pace/spend_tracker.py` — new `cache_stats()` function returns `{"cache_read_tokens": int, "cache_create_tokens": int, "cache_savings_usd": float}`.

Expected saving: ~90% on repeated system-prompt tokens for planner N-story runs and FORGE/SCRIBE iteration loops (every agentic loop turn after the first reuses the cached system-prompt KV state).

---

### Phase 2 — Streaming

Status: Implemented

Changes made:

- `pace/llm/anthropic_adapter.py` — `complete()` now uses `self._client.messages.stream()` as a context manager. Text chunks are printed to stdout as they arrive via `stream.text_stream`. `stream.get_final_message()` provides usage data and the return value. The compact-retry path uses the same streaming pattern.
- `pace/llm/anthropic_adapter.py` — `chat()` uses the same `self._client.messages.stream()` pattern. Text chunks stream to stdout. `stream.get_final_message()` is used to obtain content blocks (text and tool_use) and usage data.

UX improvement only — streaming has no effect on cost. Token counts and billing are identical to non-streaming calls.

---

### Phase 3 — Batch API: Day 0 Planner

Status: Declined

Owner declined. Would save ~50% on planner estimation calls. Requires async state across CI runs.

---

### Phase 4 — Batch API: Advisory Clearance

Status: Declined

Owner declined. Also requires Phase 3 infrastructure.

---

## Cache Pricing Reference

| Token type     | Billed rate              | Notes                                        |
|----------------|--------------------------|----------------------------------------------|
| `input`        | 100% of model input rate | Normal uncached tokens                       |
| `cache_read`   | 10% of model input rate  | KV state already in cache; ~90% discount     |
| `cache_create` | 125% of model input rate | First call writes cache; small write premium |

Break-even: 2 calls with the same system prompt. The first call pays 125% to create the cache entry; every subsequent call pays only 10%. Net saving turns positive on the second call.
