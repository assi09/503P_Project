"""One paid team-report narrative on a synthetic team of 8, checked like every report.

The members' time asleep drops by a planted 70 minutes in the reported week, so a sound report
covers that change (and recovery with it) and nothing it did not find.

Run explicitly from the repository root with the venv active:
    python eval/team_report_smoke.py --run-paid
Prints whether the prose passed its checks, any problems, the text (made-up data) and the cost.
Record the cost in docs/costs.md and experiments.md.
"""

import argparse
import json
from datetime import date, timedelta

from app.agent.llm import OpenAILLM
from app.analysis.team import team_statistics, week_of
from app.config import settings
from app.synthetic import Step, generate
from app.teams.narrative import narrate

WEEK = week_of(date(2026, 10, 19))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-paid", action="store_true", required=True)
    parser.parse_args()
    start = WEEK.start - timedelta(days=70)
    drop = (Step("sleep_minutes", WEEK.start, -70),)
    statistics = team_statistics([generate(start, 77, drop, seed=s).frame for s in range(8)], WEEK)
    attempt = narrate(OpenAILLM.from_settings(settings), statistics, settings.team_report_cap_usd)
    changed = [e.metrics[0] for e in statistics.changed]
    print(
        json.dumps(
            {
                "changes_found": changed,
                "passed": attempt.narrated is not None,
                "problems": attempt.problems,
                "headline": attempt.narrated.headline if attempt.narrated else None,
                "paragraphs": attempt.narrated.paragraphs if attempt.narrated else None,
                "cost_usd": round(attempt.cost_usd, 6),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
