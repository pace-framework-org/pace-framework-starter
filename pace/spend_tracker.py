"""PACE daily API spend tracker.

Called directly by the LLM adapters after each API response — no monkeypatching
needed because all calls go through the adapter layer.

Usage (adapter code):
    import spend_tracker
    spend_tracker.record(model, input_tokens, output_tokens)
    spend_tracker.record(model, input_tokens, output_tokens,
                         cache_read=r, cache_create=w)

Usage (orchestrator):
    import spend_tracker
    cost = spend_tracker.total_usd()
    print(spend_tracker.summary())
    stats = spend_tracker.cache_stats()

Token-limit helpers (Item 3 — Context Versioning):
    import spend_tracker
    spend_tracker.session_total()              # (input_tokens, output_tokens) totals
    spend_tracker.call_exceeds_limit(          # True if a single call would breach limits
        agent_class="forge",
        input_tokens=45000,
        output_tokens=2000,
        limits=cfg.llm.limits,
    )
"""

from __future__ import annotations

MODEL_COSTS_PER_M: dict[str, dict[str, float]] = {
    # (USD per million tokens)
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":         {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input":  0.80, "output":  4.00},
}
_FALLBACK_COSTS: dict[str, float] = {"input": 3.00, "output": 15.00}  # sonnet rate

_records: list[dict] = []


def install() -> None:
    """No-op compatibility shim.

    Originally intended to monkeypatch the Anthropic SDK for forge.py's direct
    API calls, but forge.py routes all calls through the LLM adapter which
    already calls record() explicitly.  Kept so orchestrator.py need not be
    version-gated.
    """


def record(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_create: int = 0,
) -> None:
    """Record a single API call's token usage.

    cache_read:   tokens served from the prompt cache (billed at 10% of input rate).
    cache_create: tokens written into the prompt cache (billed at 125% of input rate).
    input_tokens: non-cached new tokens only (as reported by the Anthropic API).
    """
    _records.append({
        "model": model,
        "in": input_tokens,
        "out": output_tokens,
        "cache_read": cache_read,
        "cache_create": cache_create,
    })


def total_usd() -> float:
    """Return the estimated cost (USD) accumulated in this process so far."""
    total = 0.0
    for r in _records:
        # Strip provider prefix (e.g. "openai/gpt-4o" → "gpt-4o") for lookup.
        model_key = r["model"].split("/")[-1] if "/" in r["model"] else r["model"]
        c = MODEL_COSTS_PER_M.get(model_key, MODEL_COSTS_PER_M.get(r["model"], _FALLBACK_COSTS))
        total += (r["in"] / 1_000_000) * c["input"]
        total += (r["out"] / 1_000_000) * c["output"]
        # Cache read: 10% of normal input rate.
        total += (r.get("cache_read", 0) / 1_000_000) * c["input"] * 0.10
        # Cache create: 125% of normal input rate.
        total += (r.get("cache_create", 0) / 1_000_000) * c["input"] * 1.25
    return total


def session_total() -> tuple[int, int]:
    """Return (total_input_tokens, total_output_tokens) for this process run."""
    total_in = sum(r["in"] for r in _records)
    total_out = sum(r["out"] for r in _records)
    return total_in, total_out


def call_exceeds_limit(
    agent_class: str,
    input_tokens: int,
    output_tokens: int,
    limits: "object | None" = None,
) -> bool:
    """Return True if the given token counts breach the per-agent-class limit.

    agent_class: "forge" (covers FORGE + SCRIBE) or "analysis" (covers PRIME,
                 GATE, SENTINEL, CONDUIT). Any unrecognised class returns False.
    limits: an LLMLimitsConfig instance (from config.llm.limits). When None,
            the check is skipped and False is returned.
    """
    if limits is None:
        return False
    agent_class = agent_class.lower()
    if agent_class == "forge":
        return (
            input_tokens > getattr(limits, "forge_input_tokens", 160000)
            or output_tokens > getattr(limits, "forge_output_tokens", 16384)
        )
    if agent_class == "analysis":
        return (
            input_tokens > getattr(limits, "analysis_input_tokens", 80000)
            or output_tokens > getattr(limits, "analysis_output_tokens", 8192)
        )
    return False


def summary() -> str:
    """Return a human-readable per-model cost breakdown.

    Cache columns (cache_read / cache_create) are shown only when at least one
    record in the session has non-zero cache token counts, keeping the output
    backwards-compatible for non-Anthropic providers.
    """
    by_model: dict[str, dict[str, int]] = {}
    for r in _records:
        m = r["model"]
        if m not in by_model:
            by_model[m] = {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0}
        by_model[m]["in"] += r["in"]
        by_model[m]["out"] += r["out"]
        by_model[m]["cache_read"] += r.get("cache_read", 0)
        by_model[m]["cache_create"] += r.get("cache_create", 0)

    if not by_model:
        return "  No API calls recorded."

    # Only show cache columns when at least one record has cache activity.
    show_cache = any(
        r.get("cache_read", 0) or r.get("cache_create", 0) for r in _records
    )

    lines = []
    for m, v in sorted(by_model.items()):
        model_key = m.split("/")[-1] if "/" in m else m
        c = MODEL_COSTS_PER_M.get(model_key, MODEL_COSTS_PER_M.get(m, _FALLBACK_COSTS))
        cost = (
            (v["in"] / 1_000_000) * c["input"]
            + (v["out"] / 1_000_000) * c["output"]
            + (v["cache_read"] / 1_000_000) * c["input"] * 0.10
            + (v["cache_create"] / 1_000_000) * c["input"] * 1.25
        )
        if show_cache:
            lines.append(
                f"  {m}: {v['in']:,} in + {v['out']:,} out"
                f" + {v['cache_read']:,} cache_read"
                f" + {v['cache_create']:,} cache_create"
                f" = ${cost:.4f}"
            )
        else:
            lines.append(f"  {m}: {v['in']:,} in + {v['out']:,} out = ${cost:.4f}")
    lines.append(f"  Run total: ${total_usd():.4f}")
    return "\n".join(lines)


def cache_stats() -> dict:
    """Return aggregate cache token counts and estimated savings for this session.

    Returns:
        {
            "cache_read_tokens":  int,
            "cache_create_tokens": int,
            "cache_savings_usd":  float,  # USD saved vs paying full input price
        }

    cache_savings_usd is calculated as the difference between what the
    cache_read tokens *would* have cost at full input price and what they
    *actually* cost at the 10% cache-read rate — i.e. 90% of the full price.
    The weighted input rate is computed per record so mixed-model sessions are
    handled correctly.
    """
    total_cache_read = 0
    total_cache_create = 0
    savings = 0.0

    for r in _records:
        cr = r.get("cache_read", 0)
        cw = r.get("cache_create", 0)
        total_cache_read += cr
        total_cache_create += cw

        if cr:
            model_key = r["model"].split("/")[-1] if "/" in r["model"] else r["model"]
            c = MODEL_COSTS_PER_M.get(
                model_key, MODEL_COSTS_PER_M.get(r["model"], _FALLBACK_COSTS)
            )
            # Saving = 90% of full input price per cache-read token.
            savings += (cr / 1_000_000) * c["input"] * 0.90

    return {
        "cache_read_tokens": total_cache_read,
        "cache_create_tokens": total_cache_create,
        "cache_savings_usd": savings,
    }
