"""Tests for pace/platforms/local.py."""
import json
from pathlib import Path

import pytest
import yaml

from platforms.local import LocalCIAdapter, LocalTrackerAdapter


# ---------------------------------------------------------------------------
# LocalCIAdapter.open_review_pr
# ---------------------------------------------------------------------------

def _write_gate(pace_dir: Path, day: int, decision: str = "SHIP", deferred=None):
    day_dir = pace_dir / f"day-{day}"
    day_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "gate_decision": decision,
        "deferred": deferred or [],
    }
    (day_dir / "gate.md").write_text(yaml.dump(data))


def test_open_review_pr_writes_file(tmp_path):
    pace_dir = tmp_path / ".pace"
    adapter = LocalCIAdapter()
    url = adapter.open_review_pr(1, pace_dir)
    out_file = pace_dir / "day-1" / "review-pr.md"
    assert out_file.exists()
    assert "Review Gate" in out_file.read_text()
    assert url == str(out_file)


def test_open_review_pr_counts_ship_hold(tmp_path):
    pace_dir = tmp_path / ".pace"
    _write_gate(pace_dir, 1, "SHIP")
    _write_gate(pace_dir, 2, "HOLD")
    adapter = LocalCIAdapter()
    adapter.open_review_pr(3, pace_dir)
    body = (pace_dir / "day-3" / "review-pr.md").read_text()
    assert "1" in body  # ship count
    assert "1" in body  # hold count


def test_open_review_pr_deferred_items(tmp_path):
    pace_dir = tmp_path / ".pace"
    _write_gate(pace_dir, 1, "SHIP", deferred=["item A", "item B"])
    adapter = LocalCIAdapter()
    adapter.open_review_pr(2, pace_dir)
    body = (pace_dir / "day-2" / "review-pr.md").read_text()
    assert "item A" in body
    assert "item B" in body


def test_open_review_pr_day_range_15(tmp_path):
    pace_dir = tmp_path / ".pace"
    adapter = LocalCIAdapter()
    adapter.open_review_pr(15, pace_dir)
    body = (pace_dir / "day-15" / "review-pr.md").read_text()
    assert "Days 15" in body


def test_open_review_pr_day_range_29(tmp_path):
    pace_dir = tmp_path / ".pace"
    adapter = LocalCIAdapter()
    adapter.open_review_pr(29, pace_dir)
    body = (pace_dir / "day-29" / "review-pr.md").read_text()
    assert "Days 29" in body


def test_open_review_pr_no_gate_files(tmp_path):
    pace_dir = tmp_path / ".pace"
    adapter = LocalCIAdapter()
    url = adapter.open_review_pr(5, pace_dir)
    body = (pace_dir / "day-5" / "review-pr.md").read_text()
    assert "N/A" in body  # ship rate when total=0


# ---------------------------------------------------------------------------
# LocalCIAdapter.wait_for_commit_ci
# ---------------------------------------------------------------------------

def test_wait_for_commit_ci_returns_no_runs(capsys):
    adapter = LocalCIAdapter()
    result = adapter.wait_for_commit_ci("abc1234")
    assert result["conclusion"] == "no_runs"
    assert result["sha"] == "abc1234"
    assert result["url"] == ""


def test_wait_for_commit_ci_empty_sha(capsys):
    adapter = LocalCIAdapter()
    result = adapter.wait_for_commit_ci("")
    assert result["sha"] == ""
    out = capsys.readouterr().out
    assert "unknown" in out


# ---------------------------------------------------------------------------
# LocalCIAdapter.post_daily_summary
# ---------------------------------------------------------------------------

def test_post_daily_summary_ship(capsys):
    adapter = LocalCIAdapter()
    adapter.post_daily_summary(3, {"gate_decision": "SHIP"})
    out = capsys.readouterr().out
    assert "✅" in out
    assert "SHIP" in out


def test_post_daily_summary_hold(capsys):
    adapter = LocalCIAdapter()
    adapter.post_daily_summary(3, {"gate_decision": "HOLD"})
    out = capsys.readouterr().out
    assert "🔴" in out
    assert "HOLD" in out


def test_post_daily_summary_unknown(capsys):
    adapter = LocalCIAdapter()
    adapter.post_daily_summary(3, {})
    out = capsys.readouterr().out
    assert "UNKNOWN" in out


# ---------------------------------------------------------------------------
# LocalCIAdapter.write_job_summary
# ---------------------------------------------------------------------------

def test_write_job_summary(tmp_path, monkeypatch):
    # Patch _REPO_ROOT so it writes to tmp_path
    import platforms.local as local_mod
    monkeypatch.setattr(local_mod, "_REPO_ROOT", tmp_path)
    adapter = LocalCIAdapter()
    adapter.write_job_summary("## Summary\n\nAll good.")
    summary_file = tmp_path / "pace-summary.md"
    assert summary_file.exists()
    assert "All good." in summary_file.read_text()


# ---------------------------------------------------------------------------
# LocalCIAdapter.set_variable
# ---------------------------------------------------------------------------

def test_set_variable_creates_json(tmp_path, monkeypatch):
    import platforms.local as local_mod
    monkeypatch.setattr(local_mod, "_REPO_ROOT", tmp_path)
    adapter = LocalCIAdapter()
    result = adapter.set_variable("PACE_DAY", "5")
    assert result is True
    vars_file = tmp_path / ".pace" / "variables.json"
    assert vars_file.exists()
    data = json.loads(vars_file.read_text())
    assert data["PACE_DAY"] == "5"


def test_set_variable_overwrites_existing(tmp_path, monkeypatch):
    import platforms.local as local_mod
    monkeypatch.setattr(local_mod, "_REPO_ROOT", tmp_path)
    adapter = LocalCIAdapter()
    adapter.set_variable("X", "first")
    adapter.set_variable("X", "second")
    data = json.loads((tmp_path / ".pace" / "variables.json").read_text())
    assert data["X"] == "second"


def test_set_variable_preserves_others(tmp_path, monkeypatch):
    import platforms.local as local_mod
    monkeypatch.setattr(local_mod, "_REPO_ROOT", tmp_path)
    adapter = LocalCIAdapter()
    adapter.set_variable("A", "1")
    adapter.set_variable("B", "2")
    data = json.loads((tmp_path / ".pace" / "variables.json").read_text())
    assert data["A"] == "1"
    assert data["B"] == "2"


def test_set_variable_recovers_from_corrupt_json(tmp_path, monkeypatch):
    import platforms.local as local_mod
    monkeypatch.setattr(local_mod, "_REPO_ROOT", tmp_path)
    pace_dir = tmp_path / ".pace"
    pace_dir.mkdir()
    (pace_dir / "variables.json").write_text("NOT JSON")
    adapter = LocalCIAdapter()
    result = adapter.set_variable("KEY", "val")
    assert result is True


# ---------------------------------------------------------------------------
# LocalTrackerAdapter.open_escalation_issue
# ---------------------------------------------------------------------------

def test_open_escalation_issue_basic(tmp_path):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    url = adapter.open_escalation_issue(1, day_dir, hold_reason="tests failed")
    out_file = day_dir / "escalation-issue.md"
    assert out_file.exists()
    body = out_file.read_text()
    assert "tests failed" in body
    assert url == str(out_file)


def test_open_escalation_issue_reads_story_md(tmp_path):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    (day_dir / "story.md").write_text("# My Story\n")
    adapter.open_escalation_issue(1, day_dir, hold_reason="error")
    body = (day_dir / "escalation-issue.md").read_text()
    assert "My Story" in body


def test_open_escalation_issue_reads_hold_from_gate(tmp_path):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    gate = {"gate_decision": "HOLD", "hold_reason": "coverage too low"}
    (day_dir / "gate.md").write_text(yaml.dump(gate))
    adapter.open_escalation_issue(1, day_dir)
    body = (day_dir / "escalation-issue.md").read_text()
    assert "coverage too low" in body


def test_open_escalation_issue_reads_hold_from_sentinel(tmp_path):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-2"
    day_dir.mkdir()
    # No gate.md hold_reason, but sentinel has one
    gate = {"gate_decision": "SHIP", "hold_reason": ""}
    (day_dir / "gate.md").write_text(yaml.dump(gate))
    sentinel = {"sentinel_decision": "HOLD", "hold_reason": "security issue"}
    (day_dir / "sentinel.md").write_text(yaml.dump(sentinel))
    adapter.open_escalation_issue(2, day_dir)
    body = (day_dir / "escalation-issue.md").read_text()
    assert "security issue" in body


def test_open_escalation_issue_fallback_reason(tmp_path):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    adapter.open_escalation_issue(1, day_dir)
    body = (day_dir / "escalation-issue.md").read_text()
    assert "Unknown" in body


# ---------------------------------------------------------------------------
# LocalTrackerAdapter.push_story
# ---------------------------------------------------------------------------

def test_push_story_missing_story_md(tmp_path, capsys):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    url = adapter.push_story(1, day_dir)
    assert url == ""


def test_push_story_writes_ticket(tmp_path):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    story_card = {
        "day": 1,
        "agent": "PRIME",
        "story": "implement feature",
        "target": "feature X",
        "acceptance": ["AC1", "AC2"],
        "given": "given",
        "when": "when",
        "then": "then",
        "out_of_scope": [],
    }
    (day_dir / "story.md").write_text(yaml.dump(story_card))
    url = adapter.push_story(1, day_dir)
    assert url != ""
    assert (day_dir / "story-ticket.md").exists()
    assert (day_dir / "story-ticket.yaml").exists()


# ---------------------------------------------------------------------------
# LocalTrackerAdapter.update_story_status
# ---------------------------------------------------------------------------

def test_update_story_status_no_ref(tmp_path, capsys):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    adapter.update_story_status(1, day_dir, "SHIPPED")
    out = capsys.readouterr().out
    assert "no ticket reference" in out


def test_update_story_status_with_ref(tmp_path, capsys):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    (day_dir / "story-ticket.yaml").write_text(yaml.dump({"id": "local-day-1", "url": "local"}))
    (day_dir / "story-ticket.md").write_text("# Ticket\n\nContent here.")
    adapter.update_story_status(1, day_dir, "SHIPPED")
    content = (day_dir / "story-ticket.md").read_text()
    assert "SHIPPED" in content


# ---------------------------------------------------------------------------
# LocalTrackerAdapter.post_handoff_comment
# ---------------------------------------------------------------------------

def test_post_handoff_comment_missing_ref(tmp_path, capsys):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    (day_dir / "handoff.md").write_text(yaml.dump({"status": "SHIP"}))
    adapter.post_handoff_comment(1, day_dir)
    out = capsys.readouterr().out
    assert "missing ticket ref" in out


def test_post_handoff_comment_writes_file(tmp_path):
    adapter = LocalTrackerAdapter()
    day_dir = tmp_path / "day-1"
    day_dir.mkdir()
    (day_dir / "story-ticket.yaml").write_text(yaml.dump({"id": "local-day-1"}))
    handoff = {"status": "SHIP", "summary": "Done", "forge_cost_usd": 0.5}
    (day_dir / "handoff.md").write_text(yaml.dump(handoff))
    adapter.post_handoff_comment(1, day_dir)
    assert (day_dir / "story-handoff-comment.md").exists()


# ---------------------------------------------------------------------------
# LocalTrackerAdapter.push_advisory_items
# ---------------------------------------------------------------------------

def test_push_advisory_items_empty(tmp_path, capsys):
    adapter = LocalTrackerAdapter()
    url = adapter.push_advisory_items(1, [], "SENTINEL")
    assert url == ""


def test_push_advisory_items_writes_file(tmp_path, monkeypatch):
    import platforms.local as local_mod
    monkeypatch.setattr(local_mod, "_REPO_ROOT", tmp_path)
    adapter = LocalTrackerAdapter()
    items = [
        {"id": "s-1", "finding": "SQL injection risk"},
        {"id": "s-2", "finding": "missing auth check"},
    ]
    url = adapter.push_advisory_items(3, items, "SENTINEL")
    assert url != ""
    out_file = Path(url)
    assert out_file.exists()
    body = out_file.read_text()
    assert "SQL injection risk" in body
    assert "missing auth check" in body
