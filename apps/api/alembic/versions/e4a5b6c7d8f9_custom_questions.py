"""custom questions

Revision ID: e4a5b6c7d8f9
Revises: d2f3b4c5e6a7
Create Date: 2026-09-08 18:00:00.000000

custom_questions: seller questions written or edited by a person, exported beside the generated ones.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e4a5b6c7d8f9"
down_revision = "d2f3b4c5e6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_questions",
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("custom_questions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_custom_questions_deal_id"), ["deal_id"], unique=False)


def downgrade() -> None:
    op.drop_table("custom_questions")
