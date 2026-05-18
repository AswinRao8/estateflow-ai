"""create follow_ups table

Revision ID: 002
Revises: 001
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_follow_ups_tenant_id", "follow_ups", ["tenant_id"])
    op.create_index("ix_follow_ups_lead_id", "follow_ups", ["lead_id"])
    op.create_index("ix_follow_ups_scheduled_at", "follow_ups", ["scheduled_at"])
    op.create_index(
        "ix_follow_ups_status_scheduled",
        "follow_ups",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_table("follow_ups")
