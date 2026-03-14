"""PACE Alert Engine — evaluates alert rules and dispatches notifications.

Used by orchestrator.py at four lifecycle points:
  - hold_opened          after FORGE exhausts retries and an escalation issue is opened
  - story_shipped        after all agents pass and cycle.md is written
  - cost_exceeded        when accumulated daily spend crosses threshold_usd
  - pipeline_lock_timeout when preflight detects a live lock (concurrent run)
  - update_available     when updater.py detects a newer PACE version

Usage:
    from alert_engine import AlertEngine
    engine = AlertEngine(cfg)
    engine.fire("hold_opened", {"day": 4, "reason": "GATE HOLD: coverage below 80%"})
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import PaceConfig


class AlertEngine:
    """Evaluate alert rules and dispatch to configured notification channels.

    All dispatches are best-effort: a failure in any channel is logged but
    never re-raised — the pipeline must not be blocked by a notification error.
    """

    def __init__(self, cfg: "PaceConfig") -> None:
        self._rules = cfg.alerts or []
        self._notifications_cfg = cfg.notifications
        self._adapters: dict = {}  # channel_name → NotificationAdapter | None
        self._build_adapters()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fire(self, event: str, payload: dict) -> None:
        """Evaluate all rules matching *event* and dispatch to their channels."""
        if not self._rules:
            return
        for rule in self._rules:
            if rule.event != event:
                continue
            if not self._threshold_met(rule, payload):
                continue
            for channel in (rule.channels or []):
                adapter = self._adapters.get(channel)
                if adapter is None:
                    continue
                try:
                    adapter.send(event, payload)
                except Exception as exc:
                    print(f"[PACE][AlertEngine] Channel '{channel}' raised unexpectedly: {exc}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_adapters(self) -> None:
        if not self._notifications_cfg:
            return
        from notifications import get_notification_adapter
        # Collect the unique channel names referenced across all rules
        channels_needed: set[str] = set()
        for rule in self._rules:
            channels_needed.update(rule.channels or [])
        for channel in channels_needed:
            self._adapters[channel] = get_notification_adapter(channel, self._notifications_cfg)

    @staticmethod
    def _threshold_met(rule, payload: dict) -> bool:
        """Return True when the rule's optional numeric threshold is satisfied."""
        if rule.threshold_usd is not None:
            cost = float(payload.get("cost_usd", 0) or 0)
            if cost < rule.threshold_usd:
                return False
        if rule.threshold_minutes is not None:
            minutes = float(payload.get("elapsed_minutes", 0) or 0)
            if minutes < rule.threshold_minutes:
                return False
        return True
