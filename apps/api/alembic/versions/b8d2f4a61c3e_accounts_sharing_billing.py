"""accounts, sharing, billing

Revision ID: b8d2f4a61c3e
Revises: 60fed1b30deb
Create Date: 2026-09-06 09:00:00.000000

users.email_verified_at; auth_tokens (verification, reset, and invitation links, stored hashed); deal_members
(one collaborator per row, pending until accepted); purchases (Stripe Checkout sessions for the pilot).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8d2f4a61c3e"
down_revision = "60fed1b30deb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "auth_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Enum("verify", "reset", "invite", name="token_purpose", native_enum=False, length=40), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("auth_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_auth_tokens_user_id"), ["user_id"], unique=False)

    op.create_table(
        "deal_members",
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("invited_email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.Enum("viewer", "editor", name="member_role", native_enum=False, length=40), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id", "invited_email", name="uq_deal_member_email"),
    )
    with op.batch_alter_table("deal_members", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_deal_members_deal_id"), ["deal_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_deal_members_user_id"), ["user_id"], unique=False)

    op.create_table(
        "purchases",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Enum("pilot", name="purchase_kind", native_enum=False, length=40), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status", sa.Enum("pending", "paid", "failed", name="purchase_status", native_enum=False, length=40), nullable=False
        ),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_payment_intent", sa.String(length=255), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_session_id"),
    )
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_purchases_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_purchases_user_id"))
    op.drop_table("purchases")
    with op.batch_alter_table("deal_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_deal_members_user_id"))
        batch_op.drop_index(batch_op.f("ix_deal_members_deal_id"))
    op.drop_table("deal_members")
    with op.batch_alter_table("auth_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_auth_tokens_user_id"))
    op.drop_table("auth_tokens")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("email_verified_at")
