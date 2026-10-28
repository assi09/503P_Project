"""Add reminder deliveries and in-app notifications

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-28 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reminder_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("channel IN ('email', 'in_app')", name="ck_reminder_deliveries_channel"),
        sa.CheckConstraint(
            "status IN ('sent', 'failed', 'skipped_quiet', 'skipped_cap', 'skipped_late', "
            "'skipped_off')",
            name="ck_reminder_deliveries_status",
        ),
        sa.ForeignKeyConstraint(["reminder_id"], ["reminders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reminder_id", "due_at", "channel", name="uq_reminder_deliveries_once"),
    )
    op.create_index(
        op.f("ix_reminder_deliveries_reminder_id"),
        "reminder_deliveries",
        ["reminder_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reminder_deliveries_user_id"), "reminder_deliveries", ["user_id"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("body", sa.String(length=400), nullable=False),
        sa.Column("link", sa.String(length=200), nullable=True),
        sa.Column("reminder_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reminder_id"], ["reminders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_reminder_deliveries_user_id"), table_name="reminder_deliveries")
    op.drop_index(op.f("ix_reminder_deliveries_reminder_id"), table_name="reminder_deliveries")
    op.drop_table("reminder_deliveries")
