"""PACE Microsoft Teams Notification Adapter — sends alerts via Incoming Webhook."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notifications.base import NotificationAdapter

if TYPE_CHECKING:
    from config import TeamsConfig

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


_TITLES = {
    "hold_opened":           "🚨 PACE HOLD",
    "story_shipped":         "✅ PACE SHIPPED",
    "cost_exceeded":         "💰 PACE Cost Alert",
    "pipeline_lock_timeout": "🔒 PACE Lock Timeout",
    "update_available":      "⬆️ PACE Update Available",
}

_TEMPLATES = {
    "hold_opened":           "Day {day} blocked: {reason}",
    "story_shipped":         "Day {day} shipped: {story_title}",
    "cost_exceeded":         "Daily spend ${cost_usd:.2f} exceeded threshold ${threshold_usd:.2f}",
    "pipeline_lock_timeout": "Pipeline lock held for >{threshold_minutes} minutes — possible hung run.",
    "update_available":      "v{new_version} available (installed: v{current_version}). {customization_note}",
}


def _build_card(event: str, payload: dict) -> dict:
    title = _TITLES.get(event, f"PACE: {event}")
    template = _TEMPLATES.get(event, f"{event}: {payload}")
    try:
        text = template.format_map({k: (v if v is not None else "") for k, v in payload.items()})
    except KeyError:
        text = str(payload)
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF0000" if "hold" in event or "lock" in event or "cost" in event else "00AA00",
        "summary": title,
        "sections": [{"activityTitle": title, "activityText": text}],
    }


class TeamsAdapter(NotificationAdapter):
    """Send PACE alerts to a Microsoft Teams channel via Incoming Webhook."""

    def __init__(self, cfg: "TeamsConfig") -> None:
        self._webhook_url = cfg.webhook_url

    def send(self, event: str, payload: dict) -> bool:
        if not _REQUESTS_AVAILABLE:
            print("[PACE][Teams] requests library not available — notification skipped.")
            return False
        if not self._webhook_url:
            return False
        card = _build_card(event, payload)
        try:
            resp = _requests.post(self._webhook_url, json=card, timeout=10)
            if resp.status_code not in (200, 202):
                print(f"[PACE][Teams] Webhook returned {resp.status_code}: {resp.text[:200]}")
                return False
            return True
        except Exception as exc:
            print(f"[PACE][Teams] Failed to send notification: {exc}")
            return False
