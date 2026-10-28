"""The minute loop inside the API that sends due reminders.

One background thread, started with the app and stopped with it. It is safe to have two (during a
deploy both copies run for a moment): deliveries are claimed by a unique key. Each pass logs only
counts, never what a reminder says or who it is for.
"""

import logging
import threading
from datetime import UTC, datetime

from app.config import settings
from app.db.session import session_scope
from app.email import MailError, mailer_from_settings
from app.reminders.deliver import deliver_due

logger = logging.getLogger(__name__)
INTERVAL_S = 60


class ReminderLoop:
    def __init__(self, interval_s: float = INTERVAL_S):
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            run_once()


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
