"""rename sessions.listing_ref to listing_ref_code

Revision ID: 004
Revises: 003
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("sessions", "listing_ref", new_column_name="listing_ref_code")


def downgrade() -> None:
    op.alter_column("sessions", "listing_ref_code", new_column_name="listing_ref")
