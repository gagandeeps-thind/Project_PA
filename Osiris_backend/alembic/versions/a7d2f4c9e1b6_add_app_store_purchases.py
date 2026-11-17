"""add app_store_purchases (server-verified App Store purchases and subscriptions)

Revision ID: a7d2f4c9e1b6
Revises: e5c1a9d7b3f2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d2f4c9e1b6"
down_revision: Union[str, Sequence[str], None] = "e5c1a9d7b3f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Migrations run at container boot: a boot that died after creating the table must not fail the next one.
    if sa.inspect(bind).has_table("app_store_purchases"):
        return
    op.create_table(
        "app_store_purchases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("crystal_ledger_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["crystal_ledger_id"], ["crystal_ledger.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Uniqueness lives in the index only (a UniqueConstraint as well would duplicate it).
    op.create_index("ix_app_store_purchases_id", "app_store_purchases", ["id"], unique=False)
    op.create_index("ix_app_store_purchases_user_id", "app_store_purchases", ["user_id"], unique=False)
    op.create_index(
        "ix_app_store_purchases_transaction_id", "app_store_purchases", ["transaction_id"], unique=True,
    )
    if bind.dialect.name == "postgresql":
        # Supabase exposes the public schema through its Data API; the backend connects as the owner.
        op.execute("ALTER TABLE app_store_purchases ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_app_store_purchases_transaction_id", table_name="app_store_purchases")
    op.drop_index("ix_app_store_purchases_user_id", table_name="app_store_purchases")
    op.drop_index("ix_app_store_purchases_id", table_name="app_store_purchases")
    op.drop_table("app_store_purchases")
