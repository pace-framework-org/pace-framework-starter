"""PACE NotificationAdapter — abstract base for outbound alerting channels."""

from __future__ import annotations

from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Canonical event names fired by alert_engine.py
# ---------------------------------------------------------------------------
EVENT_HOLD_OPENED = "hold_opened"
EVENT_STORY_SHIPPED = "story_shipped"
EVENT_COST_EXCEEDED = "cost_exceeded"
EVENT_PIPELINE_LOCK_TIMEOUT = "pipeline_lock_timeout"
EVENT_UPDATE_AVAILABLE = "update_available"


class NotificationAdapter(ABC):
    """Abstract interface for a single notification channel (Slack, Teams, email).

    Implementations must catch all internal errors — a notification failure
    must never crash the pipeline. The ``send`` method returns True on success,
    False on any failure.
    """

    @abstractmethod
    def send(self, event: str, payload: dict) -> bool:
        """Send an alert for *event* with contextual *payload*.

        Args:
            event:   One of the EVENT_* constants defined in this module.
            payload: Free-form context dict.  Common keys:
                       day (int), reason (str), cost_usd (float),
                       story_title (str), sprint (int).

        Returns:
            True on successful delivery, False on any error (errors are
            logged internally and never re-raised).
        """
