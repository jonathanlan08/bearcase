"""report shares

Revision ID: b9c0d1e2f3a4
Revises: a7b8c9d0e1f2
Create Date: 2026-09-28 09:00:00.000000

report_shares: read-only bearer links to one validated report. Only the SHA-256 of the token is stored.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_shares",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("report_shares", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_report_shares_report_id"), ["report_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_report_shares_deal_id"), ["deal_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("report_shares", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_report_shares_deal_id"))
        batch_op.drop_index(batch_op.f("ix_report_shares_report_id"))
    op.drop_table("report_shares")
