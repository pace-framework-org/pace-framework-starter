"""PACE Plugin Loader — discovers and manages installed plugins.

Plugins are discovered via importlib.metadata entry points under the
pace.plugins.* groups. Call load_all() once at orchestrator startup.

Usage:
    from plugins.loader import PluginRegistry, load_all
    registry = load_all(cfg)
    registry.fire_hook("pipeline_start", {"day": 1})
    # ...at shutdown:
    registry.shutdown()
"""

from __future__ import annotations

import threading
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any

from plugins.base import HookBase, PluginBase, WebhookInBase, WebhookOutBase

if TYPE_CHECKING:
    from config import PaceConfig

# Entry point groups PACE scans at startup
_ENTRY_POINT_GROUPS = [
    "pace.plugins.agents",
    "pace.plugins.tools",
    "pace.plugins.adapters",
    "pace.plugins.hooks",
    "pace.plugins.webhooks_in",
    "pace.plugins.webhooks_out",
]

_WEBHOOK_IN_DEFAULT_PORT = 9876


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Holds all loaded plugin instances; provides fire_hook() and shutdown()."""

    def __init__(self) -> None:
        self._hooks: list[HookBase] = []
        self._webhooks_out: list[WebhookOutBase] = []
        self._webhooks_in: list[WebhookInBase] = []
        self._all: list[PluginBase] = []
        self._webhook_server: threading.Thread | None = None
        self._shutdown_event = threading.Event()

    def _register(self, plugin: PluginBase) -> None:
        self._all.append(plugin)
        if isinstance(plugin, HookBase):
            self._hooks.append(plugin)
        if isinstance(plugin, WebhookOutBase):
            self._webhooks_out.append(plugin)
        if isinstance(plugin, WebhookInBase):
            self._webhooks_in.append(plugin)

    def fire_hook(self, event: str, payload: dict[str, Any]) -> None:
        """Call on_event() on all hook and webhook-out plugins subscribed to event.

        Errors are caught and logged — a broken plugin never aborts the pipeline.
        """
        for hook in self._hooks:
            manifest = hook.manifest()
            if event not in manifest.subscribed_events:
                continue
            try:
                hook.on_event(event, payload)
            except Exception as exc:
                print(f"[Plugins] Hook '{manifest.name}' raised on event '{event}': {exc}")

        for wo in self._webhooks_out:
            manifest = wo.manifest()
            if event not in manifest.subscribed_events:
                continue
            try:
                wo.on_event(event, payload)
            except Exception as exc:
                print(f"[Plugins] WebhookOut '{manifest.name}' raised on event '{event}': {exc}")

    def start_webhook_server(self, port: int = _WEBHOOK_IN_DEFAULT_PORT) -> None:
        """Start the webhook-in HTTP listener in a daemon thread."""
        if not self._webhooks_in:
            return
        self._shutdown_event.clear()
        self._webhook_server = threading.Thread(
            target=self._serve,
            args=(port,),
            daemon=True,
            name="pace-webhook-in",
        )
        self._webhook_server.start()
        print(
            f"[Plugins] Webhook-in server started on port {port} "
            f"({len(self._webhooks_in)} handler(s))"
        )

    def _serve(self, port: int) -> None:
        import json
        from http.server import BaseHTTPRequestHandler, HTTPServer

        handlers = self._webhooks_in
        shutdown_event = self._shutdown_event

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass  # suppress default access log noise

            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length)) if length else {}
                except Exception:
                    body = {}

                event_type = body.get("event", "")
                response: dict = {}
                for h in handlers:
                    try:
                        result = h.handle(event_type, body)
                        if result:
                            response.update(result)
                    except Exception as exc:
                        print(f"[Plugins] WebhookIn '{h.manifest().name}' raised: {exc}")

                raw = json.dumps(response or {}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = HTTPServer(("", port), _Handler)
        server.timeout = 1  # allows periodic check for shutdown
        while not shutdown_event.is_set():
            server.handle_request()
        server.server_close()

    def shutdown(self) -> None:
        """Signal the webhook-in server to stop (call from atexit)."""
        self._shutdown_event.set()

    @property
    def active_count(self) -> int:
        return len(self._all)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def load_all(cfg: "PaceConfig") -> PluginRegistry:
    """Discover and load all installed PACE plugins.

    Steps:
    1. Scan all pace.plugins.* entry point groups.
    2. Instantiate each discovered class (must be a PluginBase subclass).
    3. If the plugin name appears in cfg.plugins, call configure() with its
       config dict (after applying ${VAR} env interpolation to string values).
    4. Validate manifest PACE version range against PACE_VERSION.
    5. If any webhook-in plugins are loaded, start the HTTP server.

    Returns a PluginRegistry the orchestrator uses to fire lifecycle events.
    Errors are logged and skipped — a broken plugin never prevents startup.
    """
    from config import PACE_VERSION, _interpolate_env

    registry = PluginRegistry()

    # Build a name → PluginEntryConfig map from the YAML plugins: section
    plugins_conf: dict[str, object] = {}
    if cfg.plugins:
        for entry in cfg.plugins:
            plugins_conf[entry.name] = entry

    loaded: list[str] = []

    for group in _ENTRY_POINT_GROUPS:
        try:
            eps = entry_points(group=group)
        except Exception as exc:
            print(f"[Plugins] Failed to scan entry point group '{group}': {exc}")
            continue

        for ep in eps:
            try:
                klass = ep.load()
            except Exception as exc:
                print(f"[Plugins] Failed to load entry point '{ep.name}' from '{group}': {exc}")
                continue

            if not (isinstance(klass, type) and issubclass(klass, PluginBase)):
                print(f"[Plugins] Entry point '{ep.name}' is not a PluginBase subclass — skipping")
                continue

            try:
                instance: PluginBase = klass()
                manifest = instance.manifest()
            except Exception as exc:
                print(f"[Plugins] Failed to instantiate '{ep.name}': {exc}")
                continue

            # Check if disabled in plugins: section
            entry = plugins_conf.get(manifest.name)
            if entry is not None and not getattr(entry, "enabled", True):
                print(f"[Plugins] '{manifest.name}' is disabled in plugins: config — skipping")
                continue

            # Version compatibility check
            if not _version_compatible(PACE_VERSION, manifest.pace_version_min, manifest.pace_version_max):
                print(
                    f"[Plugins] '{manifest.name}' requires PACE "
                    f"{manifest.pace_version_min}"
                    + (f"–{manifest.pace_version_max}" if manifest.pace_version_max else "+")
                    + f" (installed: {PACE_VERSION}) — skipping"
                )
                continue

            # Configure if named in plugins: section
            if entry is not None:
                raw_config = getattr(entry, "config", {}) or {}
                interp_config = {
                    k: _interpolate_env(v) if isinstance(v, str) else v
                    for k, v in raw_config.items()
                }
                try:
                    instance.configure(interp_config)
                except Exception as exc:
                    print(f"[Plugins] '{manifest.name}'.configure() raised: {exc}")

            registry._register(instance)
            loaded.append(manifest.name)

    if loaded:
        print(f"[Plugins] Loaded {len(loaded)} plugin(s): {', '.join(loaded)}")
    else:
        print("[Plugins] No plugins installed.")

    # Start webhook-in server if any webhook-in plugins were loaded
    if registry._webhooks_in:
        port = _WEBHOOK_IN_DEFAULT_PORT
        # Allow any webhook-in plugin entry to override the port
        if cfg.plugins:
            for entry in cfg.plugins:
                if entry.webhook_in_port is not None:
                    port = entry.webhook_in_port
                    break
        registry.start_webhook_server(port)

    return registry


def _version_compatible(current: str, min_ver: str, max_ver: str | None) -> bool:
    """Return True if current falls within [min_ver, max_ver] (inclusive).

    Uses tuple comparison of (major, minor, patch) integers.
    Returns True on any parse error (fail-open) to avoid blocking startup.
    """
    try:
        def _t(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.split(".")[:3])

        cur = _t(current)
        return _t(min_ver) <= cur and (max_ver is None or cur <= _t(max_ver))
    except Exception:
        return True
