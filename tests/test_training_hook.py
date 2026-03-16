"""Tests for pace/training/hook.py."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from training.hook import DataExportHook


# ---------------------------------------------------------------------------
# manifest()
# ---------------------------------------------------------------------------

def test_manifest_returns_correct_metadata():
    hook = DataExportHook()
    m = hook.manifest()
    assert m.name == "pace-data-export-hook"
    assert m.plugin_type == "hook"
    assert "day_shipped" in m.subscribed_events
    assert m.pace_version_min == "2.2.0"


# ---------------------------------------------------------------------------
# configure()
# ---------------------------------------------------------------------------

def test_configure_output_dir(tmp_path):
    hook = DataExportHook()
    hook.configure({"output_dir": str(tmp_path / "custom")})
    assert hook._output_dir == Path(str(tmp_path / "custom"))


def test_configure_format_sft():
    hook = DataExportHook()
    hook.configure({"format": "sft"})
    assert hook._format == "sft"


def test_configure_format_reward():
    hook = DataExportHook()
    hook.configure({"format": "reward"})
    assert hook._format == "reward"


def test_configure_format_both():
    hook = DataExportHook()
    hook.configure({"format": "both"})
    assert hook._format == "both"


def test_configure_invalid_format():
    hook = DataExportHook()
    with pytest.raises(ValueError, match="training.format"):
        hook.configure({"format": "invalid"})


def test_configure_min_gate_pass_rate():
    hook = DataExportHook()
    hook.configure({"min_gate_pass_rate": 0.75})
    assert hook._min_gate_pass_rate == 0.75


def test_configure_min_gate_pass_rate_out_of_range():
    hook = DataExportHook()
    with pytest.raises(ValueError, match="min_gate_pass_rate"):
        hook.configure({"min_gate_pass_rate": 1.5})


def test_configure_min_gate_pass_rate_negative():
    hook = DataExportHook()
    with pytest.raises(ValueError, match="min_gate_pass_rate"):
        hook.configure({"min_gate_pass_rate": -0.1})


def test_configure_empty_dict():
    hook = DataExportHook()
    hook.configure({})  # should not raise


# ---------------------------------------------------------------------------
# on_event()
# ---------------------------------------------------------------------------

def test_on_event_ignores_non_day_shipped():
    hook = DataExportHook()
    with patch.object(hook, "_export_day") as mock_export:
        hook.on_event("pipeline_start", {})
        mock_export.assert_not_called()


def test_on_event_day_shipped_calls_export(tmp_path):
    hook = DataExportHook()
    pace_dir = tmp_path / ".pace"
    pace_dir.mkdir()
    with patch.object(hook, "_export_day") as mock_export:
        hook.on_event("day_shipped", {"day": 5, "pace_dir": pace_dir})
        mock_export.assert_called_once_with(5, pace_dir / "day-5")


def test_on_event_uses_default_pace_dir(tmp_path):
    hook = DataExportHook()
    with patch.object(hook, "_export_day") as mock_export:
        hook.on_event("day_shipped", {"day": 3})
        args = mock_export.call_args[0]
        assert args[0] == 3
        assert args[1] == Path(".pace") / "day-3"


# ---------------------------------------------------------------------------
# _export_day()
# ---------------------------------------------------------------------------

def _make_day_dir(tmp_path, day_num=1, gate_pass_rate=1.0):
    day_dir = tmp_path / f"day-{day_num}"
    day_dir.mkdir(parents=True)

    (day_dir / "story.md").write_text(f"# Story Day {day_num}")
    trace = {
        "system": "SYS",
        "messages": [{"role": "user", "content": "go"}, {"role": "assistant", "content": "done"}],
        "red_phase_confirmed": True,
        "iterations_used": 5,
    }
    (day_dir / "forge_trace.json").write_text(json.dumps(trace))
    gate = {
        "gate_decision": "SHIP",
        "criteria_results": [{"criterion": "a", "result": "PASS", "evidence": "ok"}],
    }
    (day_dir / "gate.md").write_text(yaml.dump(gate))
    (day_dir / "handoff.md").write_text(yaml.dump({"forge_cost_usd": 0.1, "iterations_used": 5}))
    return day_dir


def test_export_day_no_trace_prints_skip(tmp_path, capsys):
    hook = DataExportHook()
    empty_dir = tmp_path / "day-99"
    empty_dir.mkdir()
    hook._export_day(99, empty_dir)
    out = capsys.readouterr().out
    assert "skipping export" in out


def test_export_day_below_min_rate_prints_skip(tmp_path, capsys):
    hook = DataExportHook()
    hook.configure({"min_gate_pass_rate": 0.9, "output_dir": str(tmp_path / "out")})
    day_dir = _make_day_dir(tmp_path)
    # gate_pass_rate will be 1.0 (1 PASS / 1 criteria), so this won't be filtered
    # Let's set a really high bar
    hook._min_gate_pass_rate = 1.5  # above possible max — always skip
    hook._export_day(1, day_dir)
    out = capsys.readouterr().out
    assert "skipping export" in out


def test_export_day_writes_sft(tmp_path, capsys):
    hook = DataExportHook()
    hook.configure({"output_dir": str(tmp_path / "out"), "format": "sft"})
    day_dir = _make_day_dir(tmp_path)
    hook._export_day(1, day_dir)
    out = capsys.readouterr().out
    assert "sft=1" in out
    sft_file = tmp_path / "out" / "sft_corpus.jsonl"
    assert sft_file.exists()


def test_export_day_writes_reward(tmp_path, capsys):
    hook = DataExportHook()
    hook.configure({"output_dir": str(tmp_path / "out"), "format": "reward"})
    day_dir = _make_day_dir(tmp_path)
    hook._export_day(1, day_dir)
    out = capsys.readouterr().out
    assert "reward=1" in out
    reward_file = tmp_path / "out" / "reward_corpus.jsonl"
    assert reward_file.exists()


def test_export_day_writes_both(tmp_path, capsys):
    hook = DataExportHook()
    hook.configure({"output_dir": str(tmp_path / "out"), "format": "both"})
    day_dir = _make_day_dir(tmp_path)
    hook._export_day(1, day_dir)
    out = capsys.readouterr().out
    assert "sft=1" in out
    assert "reward=1" in out
