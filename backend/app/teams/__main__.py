"""Command line for team reports: `python -m app.teams weekly`.

Run from the repository root with the virtual environment active; the deployed platform's
scheduler runs `weekly` on Mondays. A team's week is made once, so running it again is safe.
Prints counts only, never anyone's data.
"""

import argparse
import sys
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.agent.llm import OpenAILLM
from app.analysis.team import week_of
from app.config import settings
from app.db.models import Team
from app.db.session import session_scope
from app.teams import reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.teams")
    commands = parser.add_subparsers(dest="command", required=True)
    weekly = commands.add_parser("weekly", help="make every team's report for the last full week")
    weekly.add_argument("--week", type=date.fromisoformat, help="any day of the week to report")
    weekly.add_argument("--team", type=uuid.UUID, help="only this team")
    weekly.add_argument(
        "--narrate", action="store_true", help="have a model write the prose (paid; checked)"
    )
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
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


if __name__ == "__main__":
    sys.exit(main())
