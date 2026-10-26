"""Teams: supervisors create them and share a code; people join with consent and may leave.

Only a supervisor's own teams are visible to them, and only as a count of members. A person sees
their own memberships. Reports come later (docs/teams.md, build order).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api import schemas
from app.api.auth import Db, Now, approved_user
from app.api.errors import ApiError
from app.auth.accounts import LoginThrottle
from app.db.models import Team, TeamMembership, User
from app.teams import memberships as teams

router = APIRouter(tags=["teams"])
# Wrong codes count like wrong passwords, so codes cannot be guessed one after another.
code_throttle = LoginThrottle(max_failures=10)

Person = Annotated[User, Depends(approved_user)]


def supervisor_user(user: Person) -> User:
    if user.role != "supervisor":
        raise ApiError(403, "not_supervisor", "Only supervisors can do this.")
    return user


Supervisor = Annotated[User, Depends(supervisor_user)]


def _team(db, team: Team) -> schemas.Team:
    return schemas.Team(
        id=str(team.id),
        name=team.name,
        invite_code=team.invite_code,
        members=teams.active_members(db, team),
        minimum_members=teams.MIN_MEMBERS,
        report_email=team.report_email,
        created_at=team.created_at,
    )


def _membership(membership: TeamMembership, team: Team, supervisor: User) -> schemas.Membership:
    return schemas.Membership(
        team_id=str(team.id),
        team=team.name,
        supervisor=supervisor.email,
        joined_at=membership.joined_at,
        share_levels=membership.share_levels,
        levels_consent=teams.LEVELS_CONSENT_TEXT,
        levels_consent_version=teams.LEVELS_CONSENT_VERSION,
    )


# Supervisors


@router.post("/teams", response_model=schemas.Team, status_code=201)
def create_team(body: schemas.NewTeam, db: Db, clock: Now, user: Supervisor) -> schemas.Team:
    return _team(db, teams.create_team(db, user, body.name, body.report_email, clock))


@router.get("/teams", response_model=list[schemas.Team])
def list_teams(db: Db, user: Supervisor) -> list[schemas.Team]:
    return [_team(db, team) for team in teams.supervised(db, user)]


@router.get("/teams/{team_id}", response_model=schemas.Team)
def get_team(team_id: str, db: Db, user: Supervisor) -> schemas.Team:
    return _team(db, teams.supervised_team(db, user, team_id))


@router.post("/teams/{team_id}/invite-code", response_model=schemas.Team)
def rotate_code(team_id: str, db: Db, clock: Now, user: Supervisor) -> schemas.Team:
    """A new code; the old one stops working, people already in the team stay."""
    team = teams.supervised_team(db, user, team_id)
    return _team(db, teams.rotate_code(db, team, user, clock))


# Members


def _team_for_code(db, user: User, code: str, clock) -> Team:
    key = f"team-code:{user.id}"
    code_throttle.check(key, clock)
    team = teams.team_for_code(db, code)
    if team is None:
        code_throttle.failed(key, clock)
        raise ApiError(404, "unknown_code", "No team has this code. Check it with your supervisor.")
    code_throttle.succeeded(key)
    return team


@router.post("/teams/preview", response_model=schemas.TeamPreview)
def preview(body: schemas.TeamCode, db: Db, clock: Now, user: Person) -> schemas.TeamPreview:
    """What joining the team means, for the person to read before agreeing."""
    team = _team_for_code(db, user, body.code, clock)
    return schemas.TeamPreview(
        team=team.name,
        supervisor=db.get(User, team.supervisor_id).email,
        consent=teams.consent_text(),
        consent_version=teams.CONSENT_VERSION,
    )


@router.post("/teams/join", response_model=schemas.Membership, status_code=201)
def join(body: schemas.JoinTeam, db: Db, clock: Now, user: Person) -> schemas.Membership:
    team = _team_for_code(db, user, body.code, clock)
    if body.consent_version != teams.CONSENT_VERSION:
        raise ApiError(409, "consent_changed", "What joining means has changed. Read it again.")
    membership = teams.join(db, team, user, clock)
    return _membership(membership, team, db.get(User, team.supervisor_id))


@router.get("/me/teams", response_model=list[schemas.Membership])
def my_teams(db: Db, user: Person) -> list[schemas.Membership]:
    return [_membership(*row) for row in teams.memberships(db, user)]


@router.post("/me/teams/{team_id}/levels", response_model=schemas.Membership)
def share_levels(
    team_id: str, body: schemas.ShareLevels, db: Db, clock: Now, user: Person
) -> schemas.Membership:
    """Turns on or off showing one's own named weekly levels to the supervisor."""
    if body.share and body.consent_version != teams.LEVELS_CONSENT_VERSION:
        raise ApiError(409, "consent_changed", "Read what sharing your levels means first.")
    membership = teams.share_levels(db, user, team_id, body.share, clock)
    team = db.get(Team, membership.team_id)
    return _membership(membership, team, db.get(User, team.supervisor_id))


@router.post("/me/teams/{team_id}/leave", status_code=204)
def leave(team_id: str, db: Db, clock: Now, user: Person) -> Response:
    teams.leave(db, user, team_id, clock)
    return Response(status_code=204)
