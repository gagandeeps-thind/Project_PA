"""add the crystal_purchases indexes that c4f9a2b7e1d8 declared in models.py but never created

Includes the UNIQUE index on stripe_payment_intent_id, the guard against crediting one PaymentIntent twice.

Revision ID: d6f3a1c8e2b7
Revises: b5d2e8f1a9c3
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d6f3a1c8e2b7"
down_revision: Union[str, Sequence[str], None] = "b5d2e8f1a9c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = (
    ("ix_crystal_purchases_id", ["id"], False),
    ("ix_crystal_purchases_user_id", ["user_id"], False),
    ("ix_crystal_purchases_status", ["status"], False),
    ("ix_crystal_purchases_stripe_payment_intent_id", ["stripe_payment_intent_id"], True),
)


def upgrade() -> None:
    # if_not_exists: old create_all dev databases already have them.
    for name, columns, unique in INDEXES:
        op.create_index(name, "crystal_purchases", columns, unique=unique, if_not_exists=True)


def downgrade() -> None:
    for name, _, _ in INDEXES:
        op.drop_index(name, table_name="crystal_purchases", if_exists=True)
