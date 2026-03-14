"""PACE Email Notification Adapter — sends alerts via SMTP."""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from notifications.base import NotificationAdapter

if TYPE_CHECKING:
    from config import EmailConfig


_SUBJECTS = {
    "hold_opened":           "[PACE] HOLD — Day {day}",
    "story_shipped":         "[PACE] SHIPPED — Day {day}",
    "cost_exceeded":         "[PACE] Cost Alert — ${cost_usd:.2f} exceeded",
    "pipeline_lock_timeout": "[PACE] Pipeline Lock Timeout",
    "update_available":      "[PACE] Update Available — v{new_version}",
}

_BODIES = {
    "hold_opened": (
        "PACE pipeline blocked on Day {day}.\n\n"
        "Reason: {reason}\n\n"
        "Resolve the hold issue and set PACE_PAUSED=false to resume."
    ),
    "story_shipped": (
        "Day {day} shipped successfully.\n\n"
        "Story: {story_title}"
    ),
    "cost_exceeded": (
        "Daily spend ${cost_usd:.2f} has exceeded the configured threshold of ${threshold_usd:.2f}.\n\n"
        "Review spend in .pace/day-{day}/cycle.md and adjust max_story_cost_usd if needed."
    ),
    "pipeline_lock_timeout": (
        "The PACE pipeline lock has been held for more than {threshold_minutes} minutes.\n\n"
        "This may indicate a hung pipeline run. Check your CI environment and delete "
        ".pace/pipeline.lock if the previous run is no longer active."
    ),
    "update_available": (
        "PACE v{new_version} is available (installed: v{current_version}).\n\n"
        "{customization_note}"
    ),
}


def _render(template: str, payload: dict) -> str:
    try:
        return template.format_map({k: (v if v is not None else "") for k, v in payload.items()})
    except KeyError:
        return str(payload)


class EmailAdapter(NotificationAdapter):
    """Send PACE alerts via SMTP email."""

    def __init__(self, cfg: "EmailConfig") -> None:
        self._host = cfg.smtp_host
        self._port = cfg.smtp_port
        self._from = cfg.from_addr
        self._to = cfg.to
        self._user = cfg.smtp_user
        self._password = cfg.smtp_password

    def send(self, event: str, payload: dict) -> bool:
        if not self._host or not self._to:
            return False
        subject_tpl = _SUBJECTS.get(event, f"[PACE] {event}")
        body_tpl = _BODIES.get(event, f"PACE event: {event}\n\n{payload}")
        subject = _render(subject_tpl, payload)
        body = _render(body_tpl, payload)
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = ", ".join(self._to) if isinstance(self._to, list) else self._to
        try:
            with smtplib.SMTP(self._host, self._port, timeout=15) as server:
                server.ehlo()
                if server.has_extn("starttls"):
                    server.starttls()
                    server.ehlo()
                if self._user and self._password:
                    server.login(self._user, self._password)
                recipients = self._to if isinstance(self._to, list) else [self._to]
                server.sendmail(self._from, recipients, msg.as_string())
            return True
        except Exception as exc:
            print(f"[PACE][Email] Failed to send notification: {exc}")
            return False
