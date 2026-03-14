"""PACE Plugin System — public exports.

Import from this module to build PACE-compatible plugins:

    from pace.plugins import HookBase, PluginManifest, HOOK_EVENTS

    class MyHook(HookBase):
        def manifest(self):
            return PluginManifest(
                name="pace-plugin-my-hook",
                version="1.0.0",
                plugin_type="hook",
                subscribed_events=["day_shipped", "day_held"],
            )

        def on_event(self, event, payload):
            print(f"[MyHook] {event}: {payload}")
"""

from plugins.base import (
    HOOK_EVENTS,
    HookBase,
    PluginBase,
    PluginManifest,
    WebhookInBase,
    WebhookOutBase,
)
from plugins.loader import PluginRegistry, load_all

__all__ = [
    "HOOK_EVENTS",
    "HookBase",
    "PluginBase",
    "PluginManifest",
    "PluginRegistry",
    "WebhookInBase",
    "WebhookOutBase",
    "load_all",
]
