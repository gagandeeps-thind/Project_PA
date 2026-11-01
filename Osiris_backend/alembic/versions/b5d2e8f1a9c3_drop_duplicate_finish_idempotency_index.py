"""drop the duplicate unique constraint on run_sessions.finish_idempotency_key

7c2a4b1d9e01 created both a UniqueConstraint and the unique index ix_run_sessions_finish_idempotency_key
on the same column. Keep the index (it is what models.py declares) and drop the constraint.

Revision ID: b5d2e8f1a9c3
Revises: a7c3e9f2b4d1
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b5d2e8f1a9c3"
down_revision: Union[str, Sequence[str], None] = "a7c3e9f2b4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = "run_sessions_finish_idempotency_key_key"


def upgrade() -> None:
    # SQLite keeps it as an unnamed autoindex that only a table rebuild could drop; leave dev databases as they are.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE run_sessions DROP CONSTRAINT IF EXISTS {CONSTRAINT}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint(CONSTRAINT, "run_sessions", ["finish_idempotency_key"])
