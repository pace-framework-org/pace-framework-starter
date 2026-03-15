"""PACE Training Data Collector.

Reads `.pace/day-N/` artifacts and constructs StoryTrace instances that are
ready for export via training.exporter.

Artifact layout expected under `.pace/day-N/`:
    story.md            — natural language story card (PRIME output)
    forge_trace.json    — full FORGE conversation trace (written by forge.py
                          immediately before clearing the checkpoint on a
                          successful complete_handoff)
    handoff.md          — YAML dump of FORGE handoff data
    gate.md             — YAML dump of GATE report

Only days that have all four artifacts AND a gate_decision of "SHIP" are
included; days with HOLD decisions are filtered out by default.

Reward score formula (range [0.0, 1.0]):
    base  = gate_pass_rate  (fraction of criteria that passed)
    bonus = 0.10  if iterations_used <= 10 (efficient implementation)
    penalty = min(0.20, forge_cost_usd * 0.10)  (cost penalty, max 0.20)
    score = clamp(base + bonus - penalty, 0.0, 1.0)

Usage:
    from training.collector import collect_all_traces
    traces = collect_all_traces(Path(".pace"), min_gate_pass_rate=0.75)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class StoryTrace:
    """A single shipped sprint-day training sample."""

    day: int

    # --- Inputs ---
    story_md: str                          # raw story.md text (PRIME output)

    # --- Conversation trace (from forge_trace.json) ---
    system_prompt: str                     # FORGE system prompt
    messages: list[dict[str, Any]]         # Anthropic-format turns
    red_phase_confirmed: bool
    iterations_used: int

    # --- Outcome signals (from handoff.md) ---
    commit: str = ""
    approach: str = ""
    coverage_delta: str = ""
    tests_added: int = 0
    forge_cost_usd: float = 0.0

    # --- Quality labels (from gate.md) ---
    gate_decision: str = "SHIP"            # always SHIP for collected traces
    gate_pass_rate: float = 1.0            # fraction of criteria that passed
    criteria_results: list[dict[str, Any]] = field(default_factory=list)

    # --- Computed ---
    reward_score: float = 1.0             # RLHF reward in [0.0, 1.0]


# ---------------------------------------------------------------------------
# Artifact readers
# ---------------------------------------------------------------------------

def _read_story(day_dir: Path) -> str | None:
    p = day_dir / "story.md"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def _read_forge_trace(day_dir: Path) -> dict | None:
    p = day_dir / "forge_trace.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_yaml_artifact(day_dir: Path, filename: str) -> dict:
    p = day_dir / filename
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Reward computation
# ---------------------------------------------------------------------------

def _compute_reward(gate_pass_rate: float, iterations_used: int, forge_cost_usd: float) -> float:
    """Compute a scalar RLHF reward from observable quality signals.

    Score is anchored to the GATE pass rate; efficient implementations receive
    a small bonus, and expensive ones receive a proportional penalty.
    """
    score = gate_pass_rate
    if iterations_used <= 10:
        score += 0.10
    cost_penalty = min(0.20, forge_cost_usd * 0.10)
    score -= cost_penalty
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_story_trace(day_dir: Path) -> StoryTrace | None:
    """Attempt to build a StoryTrace from a single `.pace/day-N/` directory.

    Returns None if:
    - Any required artifact is missing (story.md, forge_trace.json, gate.md)
    - The GATE decision is not "SHIP"
    - The forge_trace has no messages
    """
    story_md = _read_story(day_dir)
    if not story_md:
        return None

    trace_data = _read_forge_trace(day_dir)
    if not trace_data or not trace_data.get("messages"):
        return None

    gate = _read_yaml_artifact(day_dir, "gate.md")
    if gate.get("gate_decision", "").upper() != "SHIP":
        return None

    handoff = _read_yaml_artifact(day_dir, "handoff.md")

    # Extract day number from directory name (day-N)
    try:
        day_num = int(day_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        day_num = 0

    # GATE pass rate
    criteria = gate.get("criteria_results") or []
    if criteria:
        passed = sum(1 for c in criteria if str(c.get("result", "")).upper() == "PASS")
        gate_pass_rate = passed / len(criteria)
    else:
        gate_pass_rate = 1.0

    iterations_used = int(trace_data.get("iterations_used", handoff.get("iterations_used", 1)))
    forge_cost_usd = float(handoff.get("forge_cost_usd", 0.0))

    reward = _compute_reward(gate_pass_rate, iterations_used, forge_cost_usd)

    return StoryTrace(
        day=day_num,
        story_md=story_md,
        system_prompt=trace_data.get("system", ""),
        messages=trace_data["messages"],
        red_phase_confirmed=bool(trace_data.get("red_phase_confirmed", False)),
        iterations_used=iterations_used,
        commit=handoff.get("commit", ""),
        approach=handoff.get("approach", ""),
        coverage_delta=str(handoff.get("coverage_delta", "")),
        tests_added=int(handoff.get("tests_added", 0) or 0),
        forge_cost_usd=forge_cost_usd,
        gate_decision="SHIP",
        gate_pass_rate=gate_pass_rate,
        criteria_results=criteria,
        reward_score=reward,
    )


def collect_all_traces(
    pace_dir: Path,
    min_gate_pass_rate: float = 0.0,
) -> list[StoryTrace]:
    """Collect all valid StoryTrace instances from a .pace directory.

    Args:
        pace_dir:           Path to the `.pace/` directory.
        min_gate_pass_rate: Minimum GATE pass rate (0.0–1.0) a trace must
                            have to be included. Default 0.0 (include all).

    Returns:
        List of StoryTrace instances sorted by day ascending.
    """
    traces: list[StoryTrace] = []

    if not pace_dir.is_dir():
        return traces

    for day_dir in sorted(pace_dir.iterdir()):
        if not day_dir.is_dir() or not day_dir.name.startswith("day-"):
            continue
        trace = collect_story_trace(day_dir)
        if trace is None:
            continue
        if trace.gate_pass_rate < min_gate_pass_rate:
            continue
        traces.append(trace)

    return sorted(traces, key=lambda t: t.day)
