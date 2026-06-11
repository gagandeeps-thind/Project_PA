"""add_coupon_redemption_fields

Adds `coupon_redeemed_at` + `coupon_redeemed_by_merchant_id` to bounty_completions so
merchants can mark a coupon used at the till. Also indexes `coupon_code_issued` since
the redemption endpoint looks rows up by code.

Revision ID: 8426ded42cd0
Revises: 27dbe684fe1a
Create Date: 2026-05-22 23:45:30.787129
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8426ded42cd0'
down_revision: Union[str, Sequence[str], None] = '27dbe684fe1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bounty_completions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('coupon_redeemed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('coupon_redeemed_by_merchant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_bounty_completions_coupon_code_issued'), ['coupon_code_issued'], unique=False)
        batch_op.create_foreign_key(
            'fk_bounty_completions_coupon_redeemed_by_merchant_id',
            'merchants',
            ['coupon_redeemed_by_merchant_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('bounty_completions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bounty_completions_coupon_redeemed_by_merchant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_bounty_completions_coupon_code_issued'))
        batch_op.drop_column('coupon_redeemed_by_merchant_id')
        batch_op.drop_column('coupon_redeemed_at')
