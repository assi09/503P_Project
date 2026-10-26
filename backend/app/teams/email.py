"""The weekly team report by email (docs/teams.md): aggregates only, and a link to the app.

An email is easily forwarded and kept, so it holds less than the app: the headline, the counts,
and how many people went each way on each metric. Named weekly levels never go in an email, even
for people who share them; they stay behind the supervisor's sign-in.

Two ways to deliver: `OutboxMailer` writes each email to `data/outbox/` (the default, for local
use and tests), and `ResendMailer` sends it through Resend's API when FA_EMAIL_BACKEND=resend.
"""

import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import httpx2
from sqlalchemy.orm import Session

from app.analysis.report import change_text
from app.db.models import Team, TeamReport, User

RESEND_URL = "https://api.resend.com/emails"

# The app's light-theme metric colors (mobile/src/theme.ts), for the bars of changed metrics.
COLORS = {
    "sleep_minutes": "#4F6BD8",
    "bedtime_hour": "#4F6BD8",
    "steps": "#D9531F",
    "active_zone_minutes": "#D9531F",
    "strain": "#D9531F",
    "resting_hr": "#D63A5A",
    "hrv_ms": "#D63A5A",
    "recovery_score": "#4E9A3A",
    "stress_score": "#7C4DCC",
}
STEADY = "#A0958A"
TRACK = "#EFE7DC"
INK, MUTED = "#1F1A16", "#6F655C"


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


def _week(report: TeamReport) -> str:
    start = report.week_start
    end = start.fromordinal(start.toordinal() + 6)
    return f"{start:%b} {start.day} – {end:%b} {end.day}"


@dataclass(frozen=True)
class _Line:
    metric: str
    label: str
    changed: bool
    up: int
    down: int
    members: int
    median: str


def _lines(report: TeamReport) -> list[_Line]:
    lines = []
    for section in report.body.get("sections", []):
        if section["status"] not in ("changed", "steady"):
            continue
        stats = report.evidence[section["evidence_id"]]["stats"]
        lines.append(
            _Line(
                metric=section["metric"],
                label=section["label"],
                changed=section["status"] == "changed",
                up=stats["members_up"],
                down=stats["members_down"],
                members=stats["members"],
                median=change_text(section["metric"], stats["median_change"]),
            )
        )
    return sorted(lines, key=lambda line: not line.changed)


def compose(team: Team, report: TeamReport, to: str, app_url: str) -> Email:
    """The email for one stored report, every figure read from its stored evidence."""
    week = _week(report)
    link = f"{app_url.rstrip('/')}/team"
    subject = f"{team.name}: week of {week}"
    lines = _lines(report) if report.status == "ready" else []
    changed = [line for line in lines if line.changed]
    counts = (
        f"{report.members_included} people with data · {len(changed)} of {len(lines)} metrics "
        "changed"
    )

    text = [f"{team.name}, week of {week}", "", report.headline, ""]
    if lines:
        text += [counts, ""]
        for line in lines:
            mark = "*" if line.changed else "-"
            text.append(
                f"{mark} {line.label}: median {line.median} "
                f"({line.down} lower, {line.up} higher of {line.members})"
            )
        text.append("")
    text += [
        f"The full report, with weekday patterns: {link}",
        "",
        "Each person is compared with their own four weeks before; only the team's counts and "
        "medians are reported, never anyone's own data. Patterns, not advice.",
    ]

    rows = "".join(_html_row(line) for line in lines)
    body = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#F7F2EA;font-family:-apple-system,Segoe UI,\
Helvetica,Arial,sans-serif;color:{INK}">
<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#FFFFFF;\
border-radius:12px;padding:24px" cellpadding="0" cellspacing="0"><tr><td>
<p style="margin:0 0 4px;font-size:12px;letter-spacing:.6px;text-transform:uppercase;\
color:{MUTED}">{html.escape(team.name)} · week of {week}</p>
<h1 style="margin:0 0 16px;font-size:20px;line-height:26px">{html.escape(report.headline)}</h1>
{f'<p style="margin:0 0 16px;color:{MUTED};font-size:14px">{counts}</p>' if lines else ""}
{_html_table(rows) if rows else ""}
<p style="margin:20px 0"><a href="{html.escape(link)}" style="display:inline-block;\
background:{INK};color:#FFFFFF;text-decoration:none;padding:10px 18px;border-radius:999px;\
font-size:14px">Open the full report</a></p>
<p style="margin:0;color:{MUTED};font-size:12px;line-height:17px">Each person is compared with \
their own four weeks before; only the team's counts and medians are reported, never anyone's own \
data. Patterns, not advice.</p>
</td></tr></table></body></html>"""
    return Email(to=to, subject=subject, text="\n".join(text), html=body)


def _html_table(rows: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="font-size:12px;color:{MUTED};padding-bottom:8px">&larr; People lower</td>'
        f'<td style="font-size:12px;color:{MUTED};padding-bottom:8px;text-align:right">'
        "People higher &rarr;</td></tr>"
        f"{rows}</table>"
    )


def _html_row(line: _Line) -> str:
    """A metric's diverging bar in table cells, which email clients draw reliably."""
    color = COLORS.get(line.metric, INK) if line.changed else STEADY
    weight = "600" if line.changed else "400"
    ink = INK if line.changed else MUTED
    down = round(100 * line.down / line.members) if line.members else 0
    up = round(100 * line.up / line.members) if line.members else 0
    return (
        f'<tr><td style="padding-top:12px;font-size:14px;font-weight:{weight};color:{ink}">'
        f"{html.escape(line.label)}</td>"
        f'<td style="padding-top:12px;font-size:14px;font-weight:{weight};color:{ink};'
        f'text-align:right">{html.escape(line.median)} '
        f'<span style="font-size:12px;color:{MUTED};font-weight:400">median</span></td></tr>'
        '<tr><td colspan="2" style="padding:6px 0 2px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td width="50%" style="background:{TRACK};height:8px;line-height:8px;font-size:0">'
        f'<div style="float:right;width:{down}%;height:8px;background:{color}"></div></td>'
        f'<td width="2" style="width:2px;min-width:2px;background:{MUTED};font-size:0">'
        "&nbsp;</td>"
        f'<td width="50%" style="background:{TRACK};height:8px;line-height:8px;font-size:0">'
        f'<div style="width:{up}%;height:8px;background:{color}"></div></td>'
        "</tr></table></td></tr>"
        f'<tr><td style="font-size:12px;color:{MUTED}">{line.down} lower</td>'
        f'<td style="font-size:12px;color:{MUTED};text-align:right">{line.up} higher</td></tr>'
    )


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


def deliver(
    db: Session, team: Team, report: TeamReport, mailer: Mailer, app_url: str, now: datetime
) -> bool:
    """Emails a report to the team's report address, or its supervisor; once per report."""
    if report.emailed_at is not None:
        return False
    to = team.report_email or db.get(User, team.supervisor_id).email
    mailer.send(compose(team, report, to, app_url))
    report.emailed_at = now
    db.flush()
    return True
