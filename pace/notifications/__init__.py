"""PACE Notification Adapters — outbound alerting for pipeline lifecycle events.

Usage:
    from notifications import get_notification_adapter
    adapter = get_notification_adapter("slack", cfg.notifications)
    adapter.send("hold_opened", {"day": 4, "reason": "GATE HOLD: tests failed"})

Supported channels: "slack" | "teams" | "email"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import NotificationsConfig


def get_notification_adapter(channel: str, cfg: "NotificationsConfig"):
    """Return the NotificationAdapter for *channel*, or None if unconfigured."""
    if channel == "slack":
        from notifications.slack import SlackAdapter
        if cfg.slack and cfg.slack.webhook_url:
            return SlackAdapter(cfg.slack)
    elif channel == "teams":
        from notifications.teams import TeamsAdapter
        if cfg.teams and cfg.teams.webhook_url:
            return TeamsAdapter(cfg.teams)
    elif channel == "email":
        from notifications.email import EmailAdapter
        if cfg.email and cfg.email.smtp_host:
            return EmailAdapter(cfg.email)
    return None
