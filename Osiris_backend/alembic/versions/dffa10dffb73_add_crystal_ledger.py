"""add crystal_ledger

Revision ID: dffa10dffb73
Revises: 8426ded42cd0
Create Date: 2026-06-29 00:39:08.058759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dffa10dffb73'
down_revision: Union[str, Sequence[str], None] = '8426ded42cd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the player-side crystal_ledger journal."""
    op.create_table(
        'crystal_ledger',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('reason_code', sa.String(), nullable=False),
        sa.Column('related_siege_id', sa.Integer(), nullable=True),
        sa.Column('related_bounty_id', sa.Integer(), nullable=True),
        sa.Column('related_domain_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['related_siege_id'], ['sieges_log.id']),
        sa.ForeignKeyConstraint(['related_bounty_id'], ['bounties.id']),
        sa.ForeignKeyConstraint(['related_domain_id'], ['domains.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('crystal_ledger', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crystal_ledger_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crystal_ledger_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crystal_ledger_reason_code'), ['reason_code'], unique=False)


def downgrade() -> None:
    """Drop the crystal_ledger table (reversible)."""
    with op.batch_alter_table('crystal_ledger', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_crystal_ledger_reason_code'))
        batch_op.drop_index(batch_op.f('ix_crystal_ledger_user_id'))
        batch_op.drop_index(batch_op.f('ix_crystal_ledger_id'))
    op.drop_table('crystal_ledger')
