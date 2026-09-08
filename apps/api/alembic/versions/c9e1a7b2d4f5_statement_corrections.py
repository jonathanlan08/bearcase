"""statement corrections

Revision ID: c9e1a7b2d4f5
Revises: b8d2f4a61c3e
Create Date: 2026-09-08 10:00:00.000000

statement_corrections: a person's correction of one mapped figure, kept beside the original value with the impact
of applying it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9e1a7b2d4f5"
down_revision = "b8d2f4a61c3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "statement_corrections",
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("line_key", sa.String(length=64), nullable=False),
        sa.Column("period_label", sa.String(length=32), nullable=False),
        sa.Column("original_value", sa.Numeric(20, 8), nullable=True),
        sa.Column("corrected_value", sa.Numeric(20, 8), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("impact", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("statement_corrections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_statement_corrections_deal_id"), ["deal_id"], unique=False)


def downgrade() -> None:
    op.drop_table("statement_corrections")
