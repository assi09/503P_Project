"""Command line for team reports: `python -m app.teams weekly`.

Run from the repository root with the virtual environment active; the deployed platform's
scheduler runs `weekly` on Mondays. A team's week is made once, so running it again is safe.
Prints counts only, never anyone's data. `demo-members` fills a team with made-up members on a
local database, to try reports before real people join (`demo.py`).
"""

import argparse
import sys
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.agent.llm import OpenAILLM
from app.analysis.team import week_of
from app.config import settings
from app.db.models import Team
from app.db.session import session_scope
from app.teams import memberships, reports
from app.teams.demo import add_demo_members

LOCAL_HOSTS = {None, "localhost", "127.0.0.1", "::1", "db"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.teams")
    commands = parser.add_subparsers(dest="command", required=True)
    weekly = commands.add_parser("weekly", help="make every team's report for the last full week")
    weekly.add_argument("--week", type=date.fromisoformat, help="any day of the week to report")
    weekly.add_argument("--team", type=uuid.UUID, help="only this team")
    weekly.add_argument(
        "--narrate", action="store_true", help="have a model write the prose (paid; checked)"
    )
    demo = commands.add_parser(
        "demo-members", help="fill a team with made-up members (local database only)"
    )
    demo.add_argument("code", help="the team's invite code")
    demo.add_argument("--count", type=int, default=6)
    demo.add_argument("--sharing", type=int, default=3, help="how many share their levels")
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
    if args.command == "demo-members":
        return _demo_members(args.code, args.count, args.sharing, now)
    week = week_of(args.week) if args.week else reports.last_full_week(now.date())
    if week.start > reports.last_full_week(now.date()).start:
        print("That week is not over yet.", file=sys.stderr)
        return 1
    writer = OpenAILLM.from_settings(settings) if args.narrate else None
    made = withheld = written = 0
    cost = 0.0
    with session_scope() as session:
        query = select(Team).order_by(Team.created_at)
        if args.team:
            query = query.where(Team.id == args.team)
        for team in session.scalars(query):
            report = reports.build_report(
                session, team, week, now, writer, settings.team_report_cap_usd
            )
            made += report.status == "ready"
            withheld += report.status == "withheld"
            written += report.generated_by == "model"
            cost += report.cost_usd
    print(f"Week of {week.start}: {made} reports ready, {withheld} withheld (too few people).")
    if writer:
        print(f"{written} written by the model, the rest templated; ${cost:.4f}.")
    return 0


def _demo_members(code: str, count: int, sharing: int, now: datetime) -> int:
    if make_url(settings.database_url).host not in LOCAL_HOSTS:
        print("Made-up members go only into a local database.", file=sys.stderr)
        return 1
    if not 1 <= count <= 50 or not 0 <= sharing <= count:
        print("Use 1 to 50 members, and at most that many sharing.", file=sys.stderr)
        return 1
    with session_scope() as session:
        team = memberships.team_for_code(session, code)
        if team is None:
            print("No team has this code.", file=sys.stderr)
            return 1
        added = add_demo_members(session, team, count, sharing, now.date(), now)
        name = team.name
    print(
        f"{name}: {added.created} made-up members created, {added.joined} joined, "
        f"{added.sharing} sharing their levels."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
