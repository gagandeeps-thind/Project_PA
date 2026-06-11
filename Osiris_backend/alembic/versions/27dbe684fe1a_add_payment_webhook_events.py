"""add_payment_webhook_events

Idempotency table for the payment webhook. Stores one row per delivered provider event
(`provider_event_id`); unique constraint blocks duplicate processing on Stripe retries.

Revision ID: 27dbe684fe1a
Revises: f913af2a474d
Create Date: 2026-05-22 23:39:37.197640
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '27dbe684fe1a'
down_revision: Union[str, Sequence[str], None] = 'f913af2a474d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_webhook_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_event_id', sa.String(), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=True),
        sa.Column('payment_status', sa.String(), nullable=True),
        sa.Column('provider_payment_id', sa.String(), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('payment_webhook_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payment_webhook_events_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_webhook_events_merchant_id'), ['merchant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_webhook_events_provider_event_id'), ['provider_event_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_payment_webhook_events_received_at'), ['received_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('payment_webhook_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payment_webhook_events_received_at'))
        batch_op.drop_index(batch_op.f('ix_payment_webhook_events_provider_event_id'))
        batch_op.drop_index(batch_op.f('ix_payment_webhook_events_merchant_id'))
        batch_op.drop_index(batch_op.f('ix_payment_webhook_events_id'))
    op.drop_table('payment_webhook_events')
