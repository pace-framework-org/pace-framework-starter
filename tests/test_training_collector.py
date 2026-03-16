"""Tests for pace/training/collector.py."""
import json
from pathlib import Path

import pytest
import yaml

from training.collector import (
    StoryTrace,
    _compute_reward,
    _read_forge_trace,
    _read_story,
    _read_yaml_artifact,
    collect_all_traces,
    collect_story_trace,
)


# ---------------------------------------------------------------------------
# _read_story
# ---------------------------------------------------------------------------

def test_read_story_exists(tmp_path):
    (tmp_path / "story.md").write_text("# My Story\n")
    assert _read_story(tmp_path) == "# My Story\n"


def test_read_story_missing(tmp_path):
    assert _read_story(tmp_path) is None


# ---------------------------------------------------------------------------
# _read_forge_trace
# ---------------------------------------------------------------------------

def test_read_forge_trace_valid(tmp_path):
    data = {"messages": [{"role": "user", "content": "hello"}], "system": "sys"}
    (tmp_path / "forge_trace.json").write_text(json.dumps(data))
    result = _read_forge_trace(tmp_path)
    assert result["system"] == "sys"


def test_read_forge_trace_missing(tmp_path):
    assert _read_forge_trace(tmp_path) is None


def test_read_forge_trace_invalid_json(tmp_path):
    (tmp_path / "forge_trace.json").write_text("not json {{{")
    assert _read_forge_trace(tmp_path) is None


# ---------------------------------------------------------------------------
# _read_yaml_artifact
# ---------------------------------------------------------------------------

def test_read_yaml_artifact_exists(tmp_path):
    data = {"gate_decision": "SHIP", "criteria_results": []}
    (tmp_path / "gate.md").write_text(yaml.dump(data))
    result = _read_yaml_artifact(tmp_path, "gate.md")
    assert result["gate_decision"] == "SHIP"


def test_read_yaml_artifact_missing(tmp_path):
    assert _read_yaml_artifact(tmp_path, "gate.md") == {}


def test_read_yaml_artifact_invalid_yaml(tmp_path):
    (tmp_path / "gate.md").write_text(": bad: yaml: {{{")
    result = _read_yaml_artifact(tmp_path, "gate.md")
    assert result == {}


def test_read_yaml_artifact_empty_file(tmp_path):
    (tmp_path / "gate.md").write_text("")
    result = _read_yaml_artifact(tmp_path, "gate.md")
    assert result == {}


# ---------------------------------------------------------------------------
# _compute_reward
# ---------------------------------------------------------------------------

def test_compute_reward_perfect():
    score = _compute_reward(1.0, 8, 0.0)
    assert score == 1.0  # 1.0 + 0.10 bonus - 0.0 cost, clamped to 1.0


def test_compute_reward_with_bonus():
    score = _compute_reward(0.8, 10, 0.0)
    assert abs(score - 0.9) < 0.001


def test_compute_reward_no_bonus():
    score = _compute_reward(0.8, 11, 0.0)
    assert abs(score - 0.8) < 0.001


def test_compute_reward_cost_penalty():
    # cost_usd=2.0 → penalty = min(0.20, 2.0 * 0.10) = 0.20
    score = _compute_reward(0.9, 15, 2.0)
    assert abs(score - 0.7) < 0.001


def test_compute_reward_max_penalty():
    # cost_usd=10.0 → penalty capped at 0.20
    score = _compute_reward(0.9, 15, 10.0)
    assert abs(score - 0.7) < 0.001


def test_compute_reward_clamped_to_zero():
    score = _compute_reward(0.0, 15, 10.0)
    assert score == 0.0


def test_compute_reward_clamped_to_one():
    score = _compute_reward(1.0, 5, 0.0)
    assert score == 1.0


# ---------------------------------------------------------------------------
# collect_story_trace
# ---------------------------------------------------------------------------

def _write_day_dir(tmp_path, day_num=1, gate_decision="SHIP", messages=None, gate_pass_rate=None):
    """Helper to write a complete .pace/day-N structure."""
    day_dir = tmp_path / f"day-{day_num}"
    day_dir.mkdir(parents=True)

    (day_dir / "story.md").write_text(f"# Story Day {day_num}\n\nSome story content.")

    if messages is None:
        messages = [{"role": "user", "content": "start"}, {"role": "assistant", "content": "done"}]

    trace_data = {
        "system": "FORGE system prompt",
        "messages": messages,
        "red_phase_confirmed": True,
        "iterations_used": 8,
    }
    (day_dir / "forge_trace.json").write_text(json.dumps(trace_data))

    criteria = [
        {"criterion": "tests pass", "result": "PASS", "evidence": "all green"},
        {"criterion": "coverage", "result": "PASS", "evidence": "85%"},
    ]
    gate_data = {
        "gate_decision": gate_decision,
        "criteria_results": criteria,
        "hold_reason": "",
    }
    (day_dir / "gate.md").write_text(yaml.dump(gate_data))

    handoff_data = {
        "commit": "abc123",
        "approach": "TDD",
        "coverage_delta": "+5%",
        "tests_added": 10,
        "forge_cost_usd": 0.5,
        "iterations_used": 8,
    }
    (day_dir / "handoff.md").write_text(yaml.dump(handoff_data))
    return day_dir


def test_collect_story_trace_success(tmp_path):
    day_dir = _write_day_dir(tmp_path, day_num=5)
    trace = collect_story_trace(day_dir)
    assert trace is not None
    assert trace.day == 5
    assert trace.gate_decision == "SHIP"
    assert trace.iterations_used == 8
    assert trace.commit == "abc123"
    assert trace.tests_added == 10
    assert trace.gate_pass_rate == 1.0


def test_collect_story_trace_missing_story(tmp_path):
    day_dir = _write_day_dir(tmp_path)
    (day_dir / "story.md").unlink()
    assert collect_story_trace(day_dir) is None


def test_collect_story_trace_missing_trace(tmp_path):
    day_dir = _write_day_dir(tmp_path)
    (day_dir / "forge_trace.json").unlink()
    assert collect_story_trace(day_dir) is None


def test_collect_story_trace_empty_messages(tmp_path):
    day_dir = _write_day_dir(tmp_path, messages=[])
    assert collect_story_trace(day_dir) is None


def test_collect_story_trace_hold_decision(tmp_path):
    day_dir = _write_day_dir(tmp_path, gate_decision="HOLD")
    assert collect_story_trace(day_dir) is None


def test_collect_story_trace_missing_gate(tmp_path):
    day_dir = _write_day_dir(tmp_path)
    (day_dir / "gate.md").unlink()
    assert collect_story_trace(day_dir) is None


def test_collect_story_trace_reward_computed(tmp_path):
    day_dir = _write_day_dir(tmp_path)
    trace = collect_story_trace(day_dir)
    assert trace is not None
    assert 0.0 <= trace.reward_score <= 1.0


def test_collect_story_trace_day_from_dirname(tmp_path):
    day_dir = _write_day_dir(tmp_path, day_num=12)
    trace = collect_story_trace(day_dir)
    assert trace.day == 12


def test_collect_story_trace_invalid_dirname(tmp_path):
    # If dir name can't be parsed, day=0
    bad_dir = tmp_path / "day-abc"
    bad_dir.mkdir()
    (bad_dir / "story.md").write_text("story")
    trace_data = {"system": "", "messages": [{"role": "user", "content": "x"}], "iterations_used": 1}
    (bad_dir / "forge_trace.json").write_text(json.dumps(trace_data))
    gate_data = {"gate_decision": "SHIP", "criteria_results": []}
    (bad_dir / "gate.md").write_text(yaml.dump(gate_data))
    (bad_dir / "handoff.md").write_text(yaml.dump({}))
    trace = collect_story_trace(bad_dir)
    assert trace is not None
    assert trace.day == 0


# ---------------------------------------------------------------------------
# collect_all_traces
# ---------------------------------------------------------------------------

def test_collect_all_traces_empty_dir(tmp_path):
    traces = collect_all_traces(tmp_path)
    assert traces == []


def test_collect_all_traces_nonexistent_dir(tmp_path):
    traces = collect_all_traces(tmp_path / "nonexistent")
    assert traces == []


def test_collect_all_traces_multiple_days(tmp_path):
    _write_day_dir(tmp_path, day_num=1)
    _write_day_dir(tmp_path, day_num=3)
    _write_day_dir(tmp_path, day_num=2)
    traces = collect_all_traces(tmp_path)
    assert len(traces) == 3
    assert [t.day for t in traces] == [1, 2, 3]  # sorted


def test_collect_all_traces_filters_hold(tmp_path):
    _write_day_dir(tmp_path, day_num=1, gate_decision="SHIP")
    _write_day_dir(tmp_path, day_num=2, gate_decision="HOLD")
    traces = collect_all_traces(tmp_path)
    assert len(traces) == 1
    assert traces[0].day == 1


def test_collect_all_traces_min_gate_pass_rate(tmp_path):
    day_dir = _write_day_dir(tmp_path, day_num=1)
    # Override gate.md with partial pass
    gate_data = {
        "gate_decision": "SHIP",
        "criteria_results": [
            {"criterion": "a", "result": "PASS", "evidence": "ok"},
            {"criterion": "b", "result": "FAIL", "evidence": "nope"},
        ],
    }
    (day_dir / "gate.md").write_text(yaml.dump(gate_data))

    # 50% pass rate — filtered out with min=0.8
    traces = collect_all_traces(tmp_path, min_gate_pass_rate=0.8)
    assert len(traces) == 0

    # included with min=0.4
    traces = collect_all_traces(tmp_path, min_gate_pass_rate=0.4)
    assert len(traces) == 1


def test_collect_all_traces_skips_non_day_dirs(tmp_path):
    _write_day_dir(tmp_path, day_num=1)
    (tmp_path / "some-other-dir").mkdir()
    (tmp_path / "config.yaml").write_text("foo: bar")
    traces = collect_all_traces(tmp_path)
    assert len(traces) == 1
