"""note drafts

Revision ID: a7b8c9d0e1f2
Revises: f6b7c8d9e0a1
Create Date: 2026-09-09 09:00:00.000000

review_notes.include_in_report: a note can stay a private draft until the reviewer includes it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6b7c8d9e0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("review_notes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("include_in_report", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("review_notes", schema=None) as batch_op:
        batch_op.drop_column("include_in_report")
