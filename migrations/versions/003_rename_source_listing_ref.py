"""rename leads.source_listing_ref to source_listing_ref_code

Revision ID: 003
Revises: 002
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("leads", "source_listing_ref", new_column_name="source_listing_ref_code")


def downgrade() -> None:
    op.alter_column("leads", "source_listing_ref_code", new_column_name="source_listing_ref")
