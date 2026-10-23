"""Add findings, context questions, check-ins and memory facts

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 00:25:10.489041

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "checkins",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_checkins_rating"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.create_table(
        "context_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("answer", sa.String(length=32), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('asked', 'answered', 'dismissed')", name="ck_context_questions_status"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_context_questions_user_asked",
        "context_questions",
        ["user_id", "asked_at"],
        unique=False,
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("effect", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_findings_user_metric_created",
        "findings",
        ["user_id", "metric", "created_at"],
        unique=False,
    )
    op.create_table(
        "memory_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.String(length=120), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_run_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('routine', 'goal', 'preference', 'context')", name="ck_memory_facts_kind"
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'declined')", name="ck_memory_facts_status"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_facts_user_status", "memory_facts", ["user_id", "status"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memory_facts_user_status", table_name="memory_facts")
    op.drop_table("memory_facts")
    op.drop_index("ix_findings_user_metric_created", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_context_questions_user_asked", table_name="context_questions")
    op.drop_table("context_questions")
    op.drop_table("checkins")
