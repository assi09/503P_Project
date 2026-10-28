"""One pass of sending due reminders, run every minute by `app.background` and by the CLI.

Each pass logs only counts, never what a reminder says or who it is for.
"""

import logging
from datetime import UTC, datetime

from app.config import settings
from app.db.session import session_scope
from app.email import MailError, mailer_from_settings
from app.reminders.deliver import deliver_due

logger = logging.getLogger(__name__)


class _NoMail:
    """Email is not set up: each email is recorded as failed, and in-app reminders still go out."""

    def __init__(self, reason: str):
        self.reason = reason

    def send(self, email) -> None:
        raise MailError(self.reason)


def _mailer():
    try:
        return mailer_from_settings(settings)
    except MailError as error:
        return _NoMail(str(error))


def run_once() -> None:
    try:
        counts = deliver_due(session_scope, datetime.now(UTC), _mailer(), settings.app_url)
    except Exception:
        logger.exception("Sending reminders failed")
        return
    if counts:
        logger.info("Reminders sent: %s", dict(counts))
