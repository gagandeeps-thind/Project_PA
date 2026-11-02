"""Start tab: training sessions and group challenges

Revision ID: d4e8a1b2c3f5
Revises: c3d9e7f1b2a4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e8a1b2c3f5"
down_revision: Union[str, Sequence[str], None] = "c3d9e7f1b2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATS = ("hr_avg", "hr_min", "hr_max", "power_avg", "power_min", "power_max",
         "speed_avg", "speed_max", "elev_min", "elev_max")


def upgrade() -> None:
    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_session_id", sa.String(), nullable=False),
        sa.Column("activity_key", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("elevation_gain_m", sa.Float(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("exercise_session_id", sa.Integer(), sa.ForeignKey("exercise_sessions.id"), nullable=True),
        *[sa.Column(name, sa.Float(), nullable=True) for name in STATS],
        sa.Column("series_json", sa.String(), nullable=False),
        sa.Column("devices_json", sa.String(), nullable=False),
        sa.Column("social_post_id", sa.Integer(), sa.ForeignKey("social_posts.id"), nullable=True),
        sa.Column("local_date", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "client_session_id", name="uq_training_sessions_user_client"),
        sa.UniqueConstraint("exercise_session_id", name="uq_training_sessions_exercise_session"),
    )
    op.create_index("ix_training_sessions_id", "training_sessions", ["id"])
    op.create_index("ix_training_sessions_user_id", "training_sessions", ["user_id"])
    op.create_index("ix_training_sessions_user_activity_started", "training_sessions",
                    ["user_id", "activity_key", "started_at"])

    op.create_table(
        "group_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_official", sa.Boolean(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("activity_key", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("target", sa.Float(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_group_challenges_id", "group_challenges", ["id"])
    op.create_index("ix_group_challenges_creator_id", "group_challenges", ["creator_id"])
    op.create_index("ix_group_challenges_is_official", "group_challenges", ["is_official"])
    op.create_index("ix_group_challenges_ends_at", "group_challenges", ["ends_at"])

    op.create_table(
        "group_challenge_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("challenge_id", sa.Integer(), sa.ForeignKey("group_challenges.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("invited_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("joined_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("challenge_id", "user_id", name="uq_group_challenge_members_pair"),
    )
    op.create_index("ix_group_challenge_members_id", "group_challenge_members", ["id"])
    op.create_index("ix_group_challenge_members_challenge_id", "group_challenge_members", ["challenge_id"])
    op.create_index("ix_group_challenge_members_user_id", "group_challenge_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("group_challenge_members")
    op.drop_table("group_challenges")
    op.drop_table("training_sessions")
