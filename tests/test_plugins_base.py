"""Tests for pace/plugins/base.py."""
from typing import Any
import pytest

from plugins.base import (
    HOOK_EVENTS,
    HookBase,
    PluginBase,
    PluginManifest,
    WebhookInBase,
    WebhookOutBase,
)


# ---------------------------------------------------------------------------
# PluginManifest
# ---------------------------------------------------------------------------

def test_plugin_manifest_required_fields():
    m = PluginManifest(name="my-plugin", version="1.0.0", plugin_type="hook")
    assert m.name == "my-plugin"
    assert m.version == "1.0.0"
    assert m.plugin_type == "hook"
    assert m.pace_version_min == "2.0.0"
    assert m.pace_version_max is None
    assert m.description == ""
    assert m.author == ""
    assert m.subscribed_events == []


def test_plugin_manifest_all_fields():
    m = PluginManifest(
        name="test",
        version="2.1.0",
        plugin_type="agent",
        pace_version_min="2.1.0",
        pace_version_max="3.0.0",
        description="A test plugin",
        author="Tester",
        subscribed_events=["day_shipped", "pipeline_start"],
    )
    assert m.pace_version_max == "3.0.0"
    assert "day_shipped" in m.subscribed_events


# ---------------------------------------------------------------------------
# HOOK_EVENTS
# ---------------------------------------------------------------------------

def test_hook_events_contains_required_events():
    required = {
        "pipeline_start", "pipeline_end",
        "day_start", "day_shipped", "day_held",
        "story_generated", "forge_complete",
        "gate_pass", "sentinel_pass", "conduit_pass",
    }
    assert required == HOOK_EVENTS


def test_hook_events_is_frozenset():
    assert isinstance(HOOK_EVENTS, frozenset)


# ---------------------------------------------------------------------------
# PluginBase concrete subclass
# ---------------------------------------------------------------------------

class ConcretePlugin(PluginBase):
    def manifest(self) -> PluginManifest:
        return PluginManifest(name="concrete", version="1.0.0", plugin_type="hook")


def test_plugin_base_configure_default_noop():
    plugin = ConcretePlugin()
    plugin.configure({"key": "value"})  # should not raise


def test_plugin_base_manifest():
    plugin = ConcretePlugin()
    m = plugin.manifest()
    assert m.name == "concrete"


# ---------------------------------------------------------------------------
# HookBase concrete subclass
# ---------------------------------------------------------------------------

class ConcreteHook(HookBase):
    def __init__(self):
        self.received_events = []

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="test-hook",
            version="1.0.0",
            plugin_type="hook",
            subscribed_events=["day_shipped"],
        )

    def on_event(self, event: str, payload: dict[str, Any]) -> None:
        self.received_events.append((event, payload))


def test_hook_on_event_receives_event():
    hook = ConcreteHook()
    hook.on_event("day_shipped", {"day": 1})
    assert hook.received_events == [("day_shipped", {"day": 1})]


def test_hook_manifest():
    hook = ConcreteHook()
    m = hook.manifest()
    assert "day_shipped" in m.subscribed_events


# ---------------------------------------------------------------------------
# WebhookInBase concrete subclass
# ---------------------------------------------------------------------------

class ConcreteWebhookIn(WebhookInBase):
    def manifest(self) -> PluginManifest:
        return PluginManifest(name="wh-in", version="1.0.0", plugin_type="webhook-in")

    def handle(self, event_type: str, payload: dict) -> dict | None:
        return {"received": event_type}


def test_webhook_in_handle():
    wh = ConcreteWebhookIn()
    result = wh.handle("push", {"ref": "refs/heads/main"})
    assert result == {"received": "push"}


# ---------------------------------------------------------------------------
# WebhookOutBase concrete subclass
# ---------------------------------------------------------------------------

class ConcreteWebhookOut(WebhookOutBase):
    def __init__(self):
        self.fired_events = []

    def manifest(self) -> PluginManifest:
        return PluginManifest(name="wh-out", version="1.0.0", plugin_type="webhook-out")

    def on_event(self, event: str, payload: dict) -> None:
        self.fired_events.append(event)


def test_webhook_out_on_event():
    wh = ConcreteWebhookOut()
    wh.on_event("day_shipped", {"day": 3})
    assert wh.fired_events == ["day_shipped"]
