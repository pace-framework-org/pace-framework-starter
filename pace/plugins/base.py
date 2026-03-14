"""PACE Plugin System — base classes and manifest for all plugin types.

Plugins are Python packages that register themselves via pyproject.toml entry
points under the pace.plugins.* groups. PACE loads them at startup via
pace/plugins/loader.py.

Entry point groups:
    pace.plugins.agents       — new PACE agents
    pace.plugins.tools        — tools added to FORGE/SCRIBE's tool registry
    pace.plugins.adapters     — LLM/platform/notification adapters
    pace.plugins.hooks        — lifecycle hooks (fire at pipeline events)
    pace.plugins.webhooks_in  — HTTP listeners for external triggers
    pace.plugins.webhooks_out — JSON POST to a URL on lifecycle events

Example pyproject.toml entry:
    [project.entry-points."pace.plugins.hooks"]
    my-logger = "myplugin.hook:LifecycleLoggerHook"
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Plugin manifest
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    """Metadata every plugin must declare.

    Returned by PluginBase.manifest() so PACE can validate compatibility and
    log which plugins are active without importing the full plugin package.
    """
    name: str                              # Unique plugin identifier (e.g. "pace-plugin-linear")
    version: str                           # SemVer string (e.g. "1.0.0")
    plugin_type: str                       # "agent" | "tool" | "adapter" | "hook" | "webhook-in" | "webhook-out"
    pace_version_min: str = "2.0.0"       # Minimum PACE version this plugin requires
    pace_version_max: str | None = None    # Maximum PACE version (None = no upper bound)
    description: str = ""
    author: str = ""
    subscribed_events: list[str] = field(default_factory=list)  # for hook/webhook-out plugins


# ---------------------------------------------------------------------------
# Plugin base
# ---------------------------------------------------------------------------

class PluginBase(ABC):
    """Base class for all PACE plugins.

    Every plugin entry point must point to a class that:
    - Is a subclass of PluginBase (or one of its specialised subclasses)
    - Implements manifest() returning a PluginManifest
    - Is instantiated with no arguments (configuration is passed via configure())
    """

    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Return the plugin's manifest (metadata)."""

    def configure(self, config: dict[str, Any]) -> None:
        """Accept plugin-specific config from the plugins: YAML section.

        Called once after instantiation if the plugin's name appears in the
        plugins: section of pace.config.yaml. Override to read your settings.
        The default implementation does nothing.
        """


# ---------------------------------------------------------------------------
# Hook plugin
# ---------------------------------------------------------------------------

# Lifecycle event names fired by the PACE orchestrator.
HOOK_EVENTS: frozenset[str] = frozenset({
    "pipeline_start",   # fired at the top of main(), after adapters are ready
    "pipeline_end",     # fired at the end of main() (always, via atexit)
    "day_start",        # fired before run_cycle is called for day N
    "day_shipped",      # fired after a successful SHIP in main()
    "day_held",         # fired after a HOLD escalation in main()
    "story_generated",  # fired after PRIME writes story.md
    "forge_complete",   # fired after FORGE writes handoff.md
    "gate_pass",        # fired after GATE decision == SHIP
    "sentinel_pass",    # fired after SENTINEL decision == SHIP or ADVISORY
    "conduit_pass",     # fired after CONDUIT decision == SHIP or ADVISORY
})


class HookBase(PluginBase):
    """Base class for lifecycle hook plugins.

    Hooks are called synchronously at specific points in the pipeline.
    They must not raise exceptions — any exception is caught by the loader
    and logged; execution always continues.
    """

    @abstractmethod
    def on_event(self, event: str, payload: dict[str, Any]) -> None:
        """Called when a subscribed event fires.

        Args:
            event:   One of the HOOK_EVENTS constants.
            payload: Context dict (keys vary per event; see orchestrator.py).
        """


# ---------------------------------------------------------------------------
# Webhook-in plugin
# ---------------------------------------------------------------------------

class WebhookInBase(PluginBase):
    """Base class for webhook-in plugins.

    When any webhook-in plugin is registered, PACE starts a lightweight HTTP
    server on the configured port (default 9876) and routes incoming POST
    requests to all registered handlers.
    """

    @abstractmethod
    def handle(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Handle an incoming webhook POST.

        Args:
            event_type: String identifier from the POST body's "event" field.
            payload:    Full decoded JSON body.

        Returns:
            Optional response dict to serialize as JSON. None → 200 OK with {}.
        """


# ---------------------------------------------------------------------------
# Webhook-out plugin
# ---------------------------------------------------------------------------

class WebhookOutBase(PluginBase):
    """Base class for webhook-out plugins.

    Called by the orchestrator when a subscribed lifecycle event fires.
    Implementations are expected to POST structured JSON to an external URL.
    """

    @abstractmethod
    def on_event(self, event: str, payload: dict[str, Any]) -> None:
        """Called when a subscribed lifecycle event fires.

        Must not raise exceptions — errors are caught and logged by the loader.
        """
