"""PACE Slack Notification Adapter — sends alerts via Incoming Webhook."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notifications.base import NotificationAdapter

if TYPE_CHECKING:
    from config import SlackConfig

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


_EMOJI = {
    "hold_opened":            ":rotating_light:",
    "story_shipped":          ":white_check_mark:",
    "cost_exceeded":          ":moneybag:",
    "pipeline_lock_timeout":  ":lock:",
    "update_available":       ":arrow_up:",
}

_TEMPLATES = {
    "hold_opened":           "PACE *HOLD* — Day {day}: {reason}",
    "story_shipped":         "PACE *SHIPPED* — Day {day}: {story_title}",
    "cost_exceeded":         "PACE *COST ALERT* — daily spend ${cost_usd:.2f} exceeded threshold ${threshold_usd:.2f}",
    "pipeline_lock_timeout": "PACE *LOCK TIMEOUT* — pipeline lock held for >{threshold_minutes}m (possible hung run)",
    "update_available":      "PACE *UPDATE* — v{new_version} available (installed: v{current_version}). {customization_note}",
}


def _format_message(event: str, payload: dict) -> str:
    template = _TEMPLATES.get(event, f"PACE event: {event}")
    emoji = _EMOJI.get(event, ":bell:")
    try:
        body = template.format_map({k: (v if v is not None else "") for k, v in payload.items()})
    except KeyError:
        body = f"{event}: {payload}"
    return f"{emoji} {body}"


class SlackAdapter(NotificationAdapter):
    """Send PACE alerts to a Slack channel via Incoming Webhook URL."""

    def __init__(self, cfg: "SlackConfig") -> None:
        self._webhook_url = cfg.webhook_url
        self._channel = cfg.channel  # informational — webhook target is fixed at creation time

    def send(self, event: str, payload: dict) -> bool:
        if not _REQUESTS_AVAILABLE:
            print("[PACE][Slack] requests library not available — notification skipped.")
            return False
        if not self._webhook_url:
            return False
        text = _format_message(event, payload)
        try:
            resp = _requests.post(
                self._webhook_url,
                json={"text": text},
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[PACE][Slack] Webhook returned {resp.status_code}: {resp.text[:200]}")
                return False
            return True
        except Exception as exc:
            print(f"[PACE][Slack] Failed to send notification: {exc}")
            return False
