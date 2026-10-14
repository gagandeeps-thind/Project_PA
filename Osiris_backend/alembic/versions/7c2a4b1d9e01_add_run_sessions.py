"""add first-release running sessions and route verification

Revision ID: 7c2a4b1d9e01
Revises: c4f9a2b7e1d8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c2a4b1d9e01"
down_revision: Union[str, Sequence[str], None] = "c4f9a2b7e1d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("device_started_at", sa.DateTime(), nullable=True),
        sa.Column("device_finished_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("point_count", sa.Integer(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("route_hash", sa.String(), nullable=True),
        sa.Column("finish_idempotency_key", sa.String(), nullable=True),
        sa.Column("verification_status", sa.String(), nullable=True),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finish_idempotency_key"),
        sa.UniqueConstraint("user_id", "id", name="uq_run_sessions_user_id_id"),
        if_not_exists=True,
    )
    op.create_index("ix_run_sessions_id", "run_sessions", ["id"], unique=False, if_not_exists=True)
    op.create_index("ix_run_sessions_user_id", "run_sessions", ["user_id"], unique=False, if_not_exists=True)
    op.create_index("ix_run_sessions_activity_type", "run_sessions", ["activity_type"], unique=False, if_not_exists=True)
    op.create_index("ix_run_sessions_status", "run_sessions", ["status"], unique=False, if_not_exists=True)
    op.create_index("ix_run_sessions_route_hash", "run_sessions", ["route_hash"], unique=False, if_not_exists=True)
    op.create_index("ix_run_sessions_finish_idempotency_key", "run_sessions", ["finish_idempotency_key"], unique=True, if_not_exists=True)
    op.create_index("ix_run_sessions_verification_status", "run_sessions", ["verification_status"], unique=False, if_not_exists=True)

    op.create_table(
        "route_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_session_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("t_ms", sa.Integer(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("altitude_m", sa.Float(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_session_id"], ["run_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_session_id", "sequence", name="uq_route_points_session_sequence"),
        if_not_exists=True,
    )
    op.create_index("ix_route_points_id", "route_points", ["id"], unique=False, if_not_exists=True)
    op.create_index("ix_route_points_run_session_id", "route_points", ["run_session_id"], unique=False, if_not_exists=True)

    op.create_table(
        "verification_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_session_id", sa.Integer(), nullable=False),
        sa.Column("rules_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason_codes_json", sa.String(), nullable=False),
        sa.Column("metrics_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_session_id"], ["run_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_session_id"),
        if_not_exists=True,
    )
    op.create_index("ix_verification_decisions_id", "verification_decisions", ["id"], unique=False, if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_verification_decisions_id", table_name="verification_decisions")
    op.drop_table("verification_decisions")
    op.drop_index("ix_route_points_run_session_id", table_name="route_points")
    op.drop_index("ix_route_points_id", table_name="route_points")
    op.drop_table("route_points")
    for name in (
        "ix_run_sessions_verification_status",
        "ix_run_sessions_finish_idempotency_key",
        "ix_run_sessions_route_hash",
        "ix_run_sessions_status",
        "ix_run_sessions_activity_type",
        "ix_run_sessions_user_id",
        "ix_run_sessions_id",
    ):
        op.drop_index(name, table_name="run_sessions")
    op.drop_table("run_sessions")
