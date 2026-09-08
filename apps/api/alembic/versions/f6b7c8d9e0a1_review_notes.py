"""review notes

Revision ID: f6b7c8d9e0a1
Revises: e4a5b6c7d8f9
Create Date: 2026-09-08 21:00:00.000000

review_notes: the reviewer's notebook (conclusions, assumptions, open questions) with the sources each rests on.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f6b7c8d9e0a1"
down_revision = "e4a5b6c7d8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_notes",
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("metric_ids", sa.JSON(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("review_notes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_review_notes_deal_id"), ["deal_id"], unique=False)


def downgrade() -> None:
    op.drop_table("review_notes")
