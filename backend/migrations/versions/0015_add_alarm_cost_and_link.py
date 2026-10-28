"""Add the alarm explanation's cost and the alarm an inbox entry carries

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-28 20:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("alarms") as batch:
        batch.add_column(sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"))
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("alarm_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_notifications_alarm_id_alarms", "alarms", ["alarm_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("fk_notifications_alarm_id_alarms", type_="foreignkey")
        batch.drop_column("alarm_id")
    with op.batch_alter_table("alarms") as batch:
        batch.drop_column("cost_usd")
