"""add crystal_purchases + stripe webhook event fields (Phase 3 payments)

Revision ID: c4f9a2b7e1d8
Revises: dffa10dffb73
Create Date: 2026-06-29 01:20:00.000000

Phase 3 Stripe integration:
  - new `crystal_purchases` table (player real-money one-way top-ups)
  - `payment_webhook_events.user_id` + `.event_type` so the same dedup table guards both
    merchant-pilot-fee and player-crystal-purchase webhooks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f9a2b7e1d8'
down_revision: Union[str, Sequence[str], None] = 'dffa10dffb73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # Local development historically used create_all before Alembic was introduced. Keep
    # this unreleased migration safe for those databases while preserving the normal clean
    # database path.
    if 'crystal_purchases' not in tables:
        op.create_table(
            'crystal_purchases',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('pack_id', sa.String(), nullable=False),
            sa.Column('crystal_amount', sa.Integer(), nullable=False),
            sa.Column('amount_cents', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(), nullable=True),
            sa.Column('stripe_payment_intent_id', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=True),
            sa.Column('crystal_ledger_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('fulfilled_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['crystal_ledger_id'], ['crystal_ledger.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if 'payment_webhook_events' in tables:
        columns = {column['name'] for column in inspector.get_columns('payment_webhook_events')}
        indexes = {index['name'] for index in inspector.get_indexes('payment_webhook_events')}
        with op.batch_alter_table('payment_webhook_events', schema=None) as batch_op:
            if 'user_id' not in columns:
                batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            if 'event_type' not in columns:
                batch_op.add_column(sa.Column('event_type', sa.String(), nullable=True))
            if 'ix_payment_webhook_events_user_id' not in indexes:
                batch_op.create_index(
                    batch_op.f('ix_payment_webhook_events_user_id'), ['user_id'], unique=False,
                )
            if 'user_id' not in columns:
                batch_op.create_foreign_key(
                    'fk_payment_webhook_events_user_id_users', 'users', ['user_id'], ['id'],
                )


def downgrade() -> None:
    with op.batch_alter_table('payment_webhook_events', schema=None) as batch_op:
        batch_op.drop_constraint('fk_payment_webhook_events_user_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_payment_webhook_events_user_id'))
        batch_op.drop_column('event_type')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('crystal_purchases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_crystal_purchases_stripe_payment_intent_id'))
        batch_op.drop_index(batch_op.f('ix_crystal_purchases_status'))
        batch_op.drop_index(batch_op.f('ix_crystal_purchases_user_id'))
        batch_op.drop_index(batch_op.f('ix_crystal_purchases_id'))
    op.drop_table('crystal_purchases')
