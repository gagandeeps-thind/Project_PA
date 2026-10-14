"""Camera-verified exercise sessions

Revision ID: a7c3e9f2b4d1
Revises: e8b3f5a1c7d4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c3e9f2b4d1"
down_revision: Union[str, Sequence[str], None] = "e8b3f5a1c7d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercise_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_session_id", sa.String(), nullable=False),
        sa.Column("exercise_key", sa.String(), nullable=False),
        sa.Column("rules_version", sa.String(), nullable=False),
        sa.Column("device_started_at", sa.DateTime(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("reps_attempted", sa.Integer(), nullable=False),
        sa.Column("reps_valid", sa.Integer(), nullable=False),
        sa.Column("hold_s", sa.Float(), nullable=False),
        sa.Column("form_score", sa.Float(), nullable=False),
        sa.Column("client_verdict", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason_codes_json", sa.String(), nullable=False),
        sa.Column("metrics_json", sa.String(), nullable=False),
        sa.Column("xp_awarded", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_session_id", name="uq_exercise_sessions_user_client"),
    )
    op.create_index("ix_exercise_sessions_id", "exercise_sessions", ["id"])
    op.create_index("ix_exercise_sessions_user_id", "exercise_sessions", ["user_id"])
    op.create_index("ix_exercise_sessions_exercise_key", "exercise_sessions", ["exercise_key"])
    op.create_index("ix_exercise_sessions_status", "exercise_sessions", ["status"])


def downgrade() -> None:
    op.drop_table("exercise_sessions")
