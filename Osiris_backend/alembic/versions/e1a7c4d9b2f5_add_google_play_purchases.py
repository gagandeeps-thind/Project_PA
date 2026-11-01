"""add google_play_purchases (server-verified Google Play purchases and subscriptions)

Revision ID: e1a7c4d9b2f5
Revises: d6f3a1c8e2b7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1a7c4d9b2f5"
down_revision: Union[str, Sequence[str], None] = "d6f3a1c8e2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_play_purchases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purchase_token", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("crystal_ledger_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["crystal_ledger_id"], ["crystal_ledger.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Uniqueness lives in the index only (a UniqueConstraint as well would duplicate it).
    op.create_index("ix_google_play_purchases_id", "google_play_purchases", ["id"], unique=False)
    op.create_index("ix_google_play_purchases_user_id", "google_play_purchases", ["user_id"], unique=False)
    op.create_index(
        "ix_google_play_purchases_purchase_token", "google_play_purchases", ["purchase_token"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_google_play_purchases_purchase_token", table_name="google_play_purchases")
    op.drop_index("ix_google_play_purchases_user_id", table_name="google_play_purchases")
    op.drop_index("ix_google_play_purchases_id", table_name="google_play_purchases")
    op.drop_table("google_play_purchases")
