"""Add conversations

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25 17:45:39.015101

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TITLE_LENGTH = 60


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_user_updated", "conversations", ["user_id", "updated_at"], unique=False
    )
    # Batch mode so SQLite (the tests) can add the foreign key too.
    with op.batch_alter_table("chat_messages") as batch:
        batch.add_column(sa.Column("conversation_id", sa.Uuid(), nullable=True))
        batch.create_index("ix_chat_messages_conversation_id", ["conversation_id"], unique=False)
        batch.create_foreign_key(
            "fk_chat_messages_conversation",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Each person's existing thread becomes their first conversation, named by its first question.
    messages = sa.table(
        "chat_messages",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("role", sa.String()),
        sa.column("text", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("conversation_id", sa.Uuid()),
    )
    conversations = sa.table(
        "conversations",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("title", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    users = bind.execute(
        sa.select(
            messages.c.user_id,
            sa.func.min(messages.c.created_at),
            sa.func.max(messages.c.created_at),
        ).group_by(messages.c.user_id)
    ).all()
    for user_id, first, last in users:
        question = bind.execute(
            sa.select(messages.c.text)
            .where(messages.c.user_id == user_id, messages.c.role == "user")
            .order_by(messages.c.created_at)
            .limit(1)
        ).scalar()
        title = " ".join((question or "Earlier chat").split())
        if len(title) > TITLE_LENGTH:
            title = title[: TITLE_LENGTH - 1].rstrip() + "…"
        conversation = uuid.uuid4()
        bind.execute(
            conversations.insert().values(
                id=conversation, user_id=user_id, title=title, created_at=first, updated_at=last
            )
        )
        bind.execute(
            messages.update()
            .where(messages.c.user_id == user_id)
            .values(conversation_id=conversation)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_constraint("fk_chat_messages_conversation", type_="foreignkey")
        batch.drop_index("ix_chat_messages_conversation_id")
        batch.drop_column("conversation_id")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
