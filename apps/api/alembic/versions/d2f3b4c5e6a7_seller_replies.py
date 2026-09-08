"""seller replies

Revision ID: d2f3b4c5e6a7
Revises: c9e1a7b2d4f5
Create Date: 2026-09-08 14:00:00.000000

seller_replies: what the seller said back to an exported question, with the buyer's reading of it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2f3b4c5e6a7"
down_revision = "c9e1a7b2d4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seller_replies",
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(length=80), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("seller_replies", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_seller_replies_deal_id"), ["deal_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_seller_replies_question_id"), ["question_id"], unique=False)


def downgrade() -> None:
    op.drop_table("seller_replies")
