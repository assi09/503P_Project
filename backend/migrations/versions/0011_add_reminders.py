"""Add reminders, notification settings and the person's time zone

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-28 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=280), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=280), nullable=True),
        sa.Column("evidence_id", sa.String(length=32), nullable=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'active', 'paused', 'declined', 'cancelled', 'done')",
            name="ck_reminders_status",
        ),
        sa.CheckConstraint("source IN ('person', 'agent')", name="ck_reminders_source"),
        sa.CheckConstraint("version > 0", name="ck_reminders_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reminders_due", "reminders", ["status", "next_due_at"], unique=False)
    op.create_index(op.f("ix_reminders_user_id"), "reminders", ["user_id"], unique=False)
    op.create_table(
        "notification_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("quiet_start", sa.String(length=5), nullable=True),
        sa.Column("quiet_end", sa.String(length=5), nullable=True),
        sa.Column("max_per_day", sa.Integer(), nullable=False),
        sa.Column("email", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_per_day BETWEEN 1 AND 10", name="ck_notification_settings_cap"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("notification_settings")
    op.drop_index(op.f("ix_reminders_user_id"), table_name="reminders")
    op.drop_index("ix_reminders_due", table_name="reminders")
    op.drop_table("reminders")
    op.drop_column("users", "timezone")
