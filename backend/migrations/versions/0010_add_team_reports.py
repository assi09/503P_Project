"""Add team reports

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26 15:56:46.980109

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "team_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("members_total", sa.Integer(), nullable=False),
        sa.Column("members_included", sa.Integer(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("generated_by", sa.String(length=16), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('ready', 'withheld')", name="ck_team_reports_status"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "week_start", name="uq_team_reports_week"),
    )
    op.create_index(op.f("ix_team_reports_team_id"), "team_reports", ["team_id"], unique=False)
    # Opening a report's named levels is logged too.
    _events(
        "'created', 'code_rotated', 'joined', 'left', 'levels_shared', 'levels_unshared', "
        "'levels_viewed'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM team_events WHERE event = 'levels_viewed'")
    _events("'created', 'code_rotated', 'joined', 'left', 'levels_shared', 'levels_unshared'")
    op.drop_index(op.f("ix_team_reports_team_id"), table_name="team_reports")
    op.drop_table("team_reports")


def _events(allowed: str) -> None:
    with op.batch_alter_table("team_events") as batch:
        batch.drop_constraint("ck_team_events_event", type_="check")
        batch.create_check_constraint("ck_team_events_event", f"event IN ({allowed})")
