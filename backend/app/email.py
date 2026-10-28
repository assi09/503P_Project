"""Sending email, shared by the weekly team report and reminders.

Two ways to deliver: `OutboxMailer` writes each email to `data/outbox/` (the default, for local
use and tests), and `ResendMailer` sends it through Resend's API when FA_EMAIL_BACKEND=resend.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx2

RESEND_URL = "https://api.resend.com/emails"


class MailError(Exception):
    """An email could not be delivered; the message is safe to print."""


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    def send(self, email: Email) -> None: ...


class OutboxMailer:
    """Writes each email to a folder instead of sending it: an .html to open and a .txt."""

    def __init__(self, folder: Path):
        self.folder = folder

    def send(self, email: Email) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^a-z0-9]+", "-", email.subject.lower()).strip("-")[:80]
        (self.folder / f"{stem}.html").write_text(email.html)
        (self.folder / f"{stem}.txt").write_text(
            f"To: {email.to}\nSubject: {email.subject}\n\n{email.text}\n"
        )


class ResendMailer:
    """Sends through Resend's API (https://resend.com/docs/api-reference/emails/send-email)."""

    def __init__(self, api_key: str, sender: str, http: httpx2.Client | None = None):
        self.api_key = api_key
        self.sender = sender
        self.http = http or httpx2.Client(timeout=15)

    def send(self, email: Email) -> None:
        try:
            response = self.http.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "from": self.sender,
                    "to": [email.to],
                    "subject": email.subject,
                    "html": email.html,
                    "text": email.text,
                },
            )
        except httpx2.HTTPError as error:
            raise MailError(f"Could not reach Resend ({type(error).__name__}).") from None
        if response.status_code >= 300:
            # Resend's error message says what is wrong (e.g. an unverified sender), not the key.
            try:
                message = response.json().get("message", "")
            except ValueError:
                message = ""
            raise MailError(f"Resend refused the email ({response.status_code}): {message}")


def mailer_from_settings(settings) -> Mailer:
    if settings.email_backend == "resend":
        if settings.email_api_key is None:
            raise MailError("FA_EMAIL_BACKEND=resend needs FA_EMAIL_API_KEY in .env.")
        return ResendMailer(settings.email_api_key.get_secret_value(), settings.email_from)
    return OutboxMailer(settings.data_dir / "outbox")
