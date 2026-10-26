"""Add teams

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26 15:29:48.758329

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supervisor_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("invite_code", sa.String(length=16), nullable=False),
        sa.Column("report_email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supervisor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_index(op.f("ix_teams_supervisor_id"), "teams", ["supervisor_id"], unique=False)
    op.create_table(
        "team_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event IN ('created', 'code_rotated', 'joined', 'left', 'levels_shared', "
            "'levels_unshared')",
            name="ck_team_events_event",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_team_events_team_id"), "team_events", ["team_id"], unique=False)
    op.create_table(
        "team_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_version", sa.String(length=32), nullable=False),
        sa.Column("share_levels", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("levels_consent_version", sa.String(length=32), nullable=True),
        sa.Column("levels_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_team_memberships_team_id"), "team_memberships", ["team_id"], unique=False
    )
    op.create_index(
        op.f("ix_team_memberships_user_id"), "team_memberships", ["user_id"], unique=False
    )
    op.create_index(
        "uq_team_memberships_active",
        "team_memberships",
        ["team_id", "user_id"],
        unique=True,
        sqlite_where=sa.text("left_at IS NULL"),
        postgresql_where=sa.text("left_at IS NULL"),
    )
    # Everyone existing is a member; the owner grants supervisor with `python -m app.auth`.
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("role", sa.String(length=16), server_default="member", nullable=False)
        )
        batch.create_check_constraint("ck_users_role", "role IN ('member', 'supervisor')")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_role", type_="check")
        batch.drop_column("role")
    op.drop_index(
        "uq_team_memberships_active",
        table_name="team_memberships",
        sqlite_where=sa.text("left_at IS NULL"),
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.drop_index(op.f("ix_team_memberships_user_id"), table_name="team_memberships")
    op.drop_index(op.f("ix_team_memberships_team_id"), table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_index(op.f("ix_team_events_team_id"), table_name="team_events")
    op.drop_table("team_events")
    op.drop_index(op.f("ix_teams_supervisor_id"), table_name="teams")
    op.drop_table("teams")
