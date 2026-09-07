"""Transactional email behind one small adapter.

`ConsoleEmailer` (the default) logs each message and keeps the last fifty in memory so tests and a developer can
read the links; `ResendEmailer` posts to the Resend API when BEARCASE_EMAIL_PROVIDER=resend and a key is set.
Nothing here ever runs during tests against a real provider: the test environment keeps the console emailer.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import httpx

from bearcase.config import Settings, get_settings
from bearcase.models.base import utcnow

log = logging.getLogger("bearcase.email")
RESEND_URL = "https://api.resend.com/emails"
OUTBOX_SIZE = 50


@dataclass
class SentEmail:
    to: str
    subject: str
    text: str
    html: str | None = None
    sent_at: datetime = field(default_factory=utcnow)


class Emailer(Protocol):
    def send(self, to: str, subject: str, text: str, html: str | None = None) -> None: ...


class ConsoleEmailer:
    """Logs every message at INFO and keeps the newest OUTBOX_SIZE in memory."""

    def __init__(self) -> None:
        self.outbox: deque[SentEmail] = deque(maxlen=OUTBOX_SIZE)

    def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        message = SentEmail(to=to, subject=subject, text=text, html=html)
        self.outbox.append(message)
        log.info("email to %s: %s\n%s", to, subject, text)


class ResendEmailer:
    def __init__(self, api_key: str, sender: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout = timeout

    def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        payload: dict[str, object] = {"from": self._sender, "to": [to], "subject": subject, "text": text}
        if html:
            payload["html"] = html
        response = httpx.post(
            RESEND_URL, json=payload, headers={"Authorization": f"Bearer {self._api_key}"}, timeout=self._timeout
        )
        if response.status_code >= 400:
            # The body may echo the request; the key never appears in it, but keep the log short anyway.
            raise EmailDeliveryError(f"Resend answered {response.status_code} for a message to {to}: {response.text[:300]}")


class EmailDeliveryError(RuntimeError):
    pass


_console = ConsoleEmailer()


def console_outbox() -> list[SentEmail]:
    """Messages the console emailer has sent, oldest first. Tests read verification and reset links from here."""
    return list(_console.outbox)


def last_email_to(address: str) -> SentEmail | None:
    address = address.lower()
    for message in reversed(_console.outbox):
        if message.to.lower() == address:
            return message
    return None


def get_emailer(settings: Settings | None = None) -> Emailer:
    s = settings or get_settings()
    if s.email_provider == "resend":
        if s.resend_api_key:
            return ResendEmailer(s.resend_api_key, s.email_from)
        log.warning("BEARCASE_EMAIL_PROVIDER=resend but no RESEND_API_KEY; falling back to the console emailer")
    return _console


def email_status(settings: Settings) -> tuple[str, str]:
    """(status, detail) for `bearcase doctor`: ok, warn, or fail, and a sentence with no secret in it."""
    if settings.email_provider == "resend":
        if settings.resend_api_key:
            return "ok", f"Resend, from {settings.email_from}; links point at {settings.app_base_url}"
        return "fail", "Resend selected but RESEND_API_KEY is not set; verification and reset emails cannot be delivered"
    status = "warn" if settings.env == "production" else "ok"
    return (
        status,
        f"console: messages are logged, not delivered (last {OUTBOX_SIZE} kept in memory); links point at {settings.app_base_url}",
    )
