"""Tests for small utility modules: schemas, advisory, alert_engine, issue_template."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# schemas.py
# ---------------------------------------------------------------------------

def test_story_card_schema_structure():
    from schemas import STORY_CARD_SCHEMA
    assert STORY_CARD_SCHEMA["type"] == "object"
    assert "day" in STORY_CARD_SCHEMA["properties"]
    assert "acceptance" in STORY_CARD_SCHEMA["required"]


def test_handoff_schema_structure():
    from schemas import HANDOFF_SCHEMA
    assert "commit" in HANDOFF_SCHEMA["required"]
    assert HANDOFF_SCHEMA["properties"]["agent"]["const"] == "FORGE"


def test_gate_report_schema_structure():
    from schemas import GATE_REPORT_SCHEMA
    assert "gate_decision" in GATE_REPORT_SCHEMA["required"]
    assert "SHIP" in GATE_REPORT_SCHEMA["properties"]["gate_decision"]["enum"]
    assert "HOLD" in GATE_REPORT_SCHEMA["properties"]["gate_decision"]["enum"]


def test_sentinel_report_schema_structure():
    from schemas import SENTINEL_REPORT_SCHEMA
    assert "sentinel_decision" in SENTINEL_REPORT_SCHEMA["required"]
    decisions = SENTINEL_REPORT_SCHEMA["properties"]["sentinel_decision"]["enum"]
    assert "SHIP" in decisions
    assert "HOLD" in decisions
    assert "ADVISORY" in decisions


def test_conduit_report_schema_structure():
    from schemas import CONDUIT_REPORT_SCHEMA
    assert "conduit_decision" in CONDUIT_REPORT_SCHEMA["required"]


# ---------------------------------------------------------------------------
# advisory.py
# ---------------------------------------------------------------------------

import advisory as advisory_mod


@pytest.fixture(autouse=True)
def patch_backlog_file(tmp_path, monkeypatch):
    monkeypatch.setattr(advisory_mod, "BACKLOG_FILE", tmp_path / ".pace" / "advisory_backlog.yaml")
    yield


def test_load_open_backlog_empty():
    items = advisory_mod.load_open_backlog()
    assert items == []


def test_add_advisory_items_creates_entries():
    advisory_mod.add_advisory_items(3, ["SQL injection risk", "missing auth"], "SENTINEL")
    items = advisory_mod.load_open_backlog()
    assert len(items) == 2
    assert items[0]["finding"] == "SQL injection risk"
    assert items[0]["status"] == "open"
    assert items[0]["day_raised"] == 3


def test_add_advisory_items_deduplicates():
    advisory_mod.add_advisory_items(1, ["issue A"], "SENTINEL")
    advisory_mod.add_advisory_items(2, ["issue A", "issue B"], "SENTINEL")
    items = advisory_mod.load_open_backlog()
    assert len(items) == 2  # issue A deduped


def test_add_advisory_items_generates_ids():
    advisory_mod.add_advisory_items(5, ["finding 1"], "CONDUIT")
    items = advisory_mod.load_open_backlog()
    assert items[0]["id"].startswith("conduit")


def test_clear_advisory_items_marks_cleared():
    advisory_mod.add_advisory_items(1, ["issue X"], "SENTINEL")
    advisory_mod.clear_advisory_items("SENTINEL")
    all_items = advisory_mod._load_all()
    assert all(i["status"] == "cleared" for i in all_items)


def test_clear_advisory_items_only_clears_agent():
    advisory_mod.add_advisory_items(1, ["sentinel issue"], "SENTINEL")
    advisory_mod.add_advisory_items(2, ["conduit issue"], "CONDUIT")
    advisory_mod.clear_advisory_items("SENTINEL")
    open_items = advisory_mod.load_open_backlog()
    assert len(open_items) == 1
    assert open_items[0]["agent"] == "CONDUIT"


def test_format_backlog_for_forge():
    items = [
        {"agent": "SENTINEL", "day_raised": 3, "finding": "xss risk"},
        {"agent": "CONDUIT", "day_raised": 4, "finding": "port exposed"},
    ]
    result = advisory_mod.format_backlog_for_forge(items)
    assert "xss risk" in result
    assert "port exposed" in result
    assert "SENTINEL" in result


# ---------------------------------------------------------------------------
# issue_template.py
# ---------------------------------------------------------------------------

def test_story_body_markdown_basic():
    from issue_template import story_body_markdown
    story_card = {
        "target": "implement feature X",
        "acceptance": ["AC1: tests pass", "AC2: coverage > 80%"],
    }
    body = story_body_markdown(5, story_card)
    assert "Day 5" in body
    assert "implement feature X" in body
    assert "AC1: tests pass" in body
    assert "AC2: coverage > 80%" in body


def test_story_body_markdown_no_acceptance():
    from issue_template import story_body_markdown
    body = story_body_markdown(1, {})
    assert "No acceptance criteria" in body


def test_handoff_comment_markdown_basic():
    from issue_template import handoff_comment_markdown
    handoff = {"status": "SHIP", "summary": "All done", "forge_cost_usd": 0.42}
    body = handoff_comment_markdown(3, handoff)
    assert "Day 3" in body
    assert "SHIP" in body
    assert "$0.4200" in body


def test_handoff_comment_markdown_no_cost():
    from issue_template import handoff_comment_markdown
    body = handoff_comment_markdown(1, {"status": "SHIP"})
    assert "N/A" in body


def test_handoff_comment_markdown_no_summary():
    from issue_template import handoff_comment_markdown
    body = handoff_comment_markdown(1, {"status": "HOLD"})
    assert "HOLD" in body


# ---------------------------------------------------------------------------
# alert_engine.py
# ---------------------------------------------------------------------------

def _make_pace_config(rules=None, notifications_cfg=None):
    cfg = MagicMock()
    cfg.alerts = rules or []
    cfg.notifications = notifications_cfg
    return cfg


def test_alert_engine_no_rules_fire_noop():
    from alert_engine import AlertEngine
    engine = AlertEngine(_make_pace_config())
    engine.fire("hold_opened", {"day": 1})  # should not raise


def test_alert_engine_rule_wrong_event_not_fired():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.event = "story_shipped"
    rule.threshold_usd = None
    rule.threshold_minutes = None
    rule.channels = ["slack"]
    cfg = _make_pace_config(rules=[rule])
    engine = AlertEngine(cfg)
    engine.fire("hold_opened", {"day": 1})
    # No adapters built for "slack" (notifications_cfg is None) — should not raise


def test_alert_engine_threshold_met_no_threshold():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.threshold_usd = None
    rule.threshold_minutes = None
    assert AlertEngine._threshold_met(rule, {}) is True


def test_alert_engine_threshold_met_cost_below():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.threshold_usd = 5.0
    rule.threshold_minutes = None
    assert AlertEngine._threshold_met(rule, {"cost_usd": 2.0}) is False


def test_alert_engine_threshold_met_cost_above():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.threshold_usd = 5.0
    rule.threshold_minutes = None
    assert AlertEngine._threshold_met(rule, {"cost_usd": 6.0}) is True


def test_alert_engine_threshold_met_minutes_below():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.threshold_usd = None
    rule.threshold_minutes = 10.0
    assert AlertEngine._threshold_met(rule, {"elapsed_minutes": 5.0}) is False


def test_alert_engine_threshold_met_minutes_above():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.threshold_usd = None
    rule.threshold_minutes = 10.0
    assert AlertEngine._threshold_met(rule, {"elapsed_minutes": 15.0}) is True


def test_alert_engine_channel_adapter_none_does_not_crash():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.event = "hold_opened"
    rule.threshold_usd = None
    rule.threshold_minutes = None
    rule.channels = ["slack"]
    cfg = _make_pace_config(rules=[rule])
    engine = AlertEngine(cfg)
    engine._adapters["slack"] = None  # explicitly null adapter
    engine.fire("hold_opened", {"day": 1})  # should not raise


def test_alert_engine_adapter_exception_is_caught():
    from alert_engine import AlertEngine
    rule = MagicMock()
    rule.event = "hold_opened"
    rule.threshold_usd = None
    rule.threshold_minutes = None
    rule.channels = ["slack"]
    cfg = _make_pace_config(rules=[rule])
    engine = AlertEngine(cfg)
    broken_adapter = MagicMock()
    broken_adapter.send.side_effect = RuntimeError("network down")
    engine._adapters["slack"] = broken_adapter
    engine.fire("hold_opened", {"day": 1})  # should not raise — exception is caught
