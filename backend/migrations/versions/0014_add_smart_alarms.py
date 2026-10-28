"""Add smart alarms and their settings

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-28 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "alarms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=True),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=600), nullable=False),
        sa.Column("written_by", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("feedback", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'suppressed', 'expired')", name="ck_alarms_status"
        ),
        sa.CheckConstraint(
            "feedback IS NULL OR feedback IN ('useful', 'not_useful')", name="ck_alarms_feedback"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alarms_user_id"), "alarms", ["user_id"], unique=False)
    op.create_index("ix_alarms_user_key", "alarms", ["user_id", "key", "created_at"], unique=False)
    op.create_table(
        "alarm_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("muted_kinds", sa.JSON(), nullable=False),
        sa.Column("sensitivity", sa.String(length=8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sensitivity IN ('fewer', 'normal', 'more')", name="ck_alarm_settings_sensitivity"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("alarm_settings")
    op.drop_index("ix_alarms_user_key", table_name="alarms")
    op.drop_index(op.f("ix_alarms_user_id"), table_name="alarms")
    op.drop_table("alarms")
