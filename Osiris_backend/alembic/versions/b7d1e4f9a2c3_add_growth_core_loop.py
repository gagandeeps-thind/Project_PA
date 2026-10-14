"""Growth G1: player profiles, quest awards, analytics events

Revision ID: b7d1e4f9a2c3
Revises: a3e8d5c2f710
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d1e4f9a2c3"
down_revision: Union[str, Sequence[str], None] = "a3e8d5c2f710"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("utc_offset_minutes", sa.Integer(), nullable=False),
        sa.Column("public_profile", sa.Boolean(), nullable=False),
        sa.Column("location_consent_at", sa.DateTime(), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(), nullable=True),
        sa.Column("referral_code", sa.String(), nullable=False),
        sa.Column("referred_by_user_id", sa.Integer(), nullable=True),
        sa.Column("referral_rewarded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["referred_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_profiles_id", "player_profiles", ["id"])
    op.create_index("ix_player_profiles_user_id", "player_profiles", ["user_id"], unique=True)
    op.create_index("ix_player_profiles_referral_code", "player_profiles", ["referral_code"], unique=True)
    op.create_index("ix_player_profiles_referred_by_user_id", "player_profiles", ["referred_by_user_id"])

    op.create_table(
        "quest_awards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("quest_key", sa.String(), nullable=False),
        sa.Column("rules_version", sa.String(), nullable=False),
        sa.Column("target_m", sa.Integer(), nullable=True),
        sa.Column("xp_awarded", sa.Integer(), nullable=False),
        sa.Column("run_session_id", sa.Integer(), nullable=True),
        sa.Column("awarded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["run_session_id"], ["run_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "quest_key", name="uq_quest_awards_user_key"),
    )
    op.create_index("ix_quest_awards_id", "quest_awards", ["id"])
    op.create_index("ix_quest_awards_user_id", "quest_awards", ["user_id"])

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("install_id", sa.String(), nullable=True),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("properties_json", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analytics_events_id", "analytics_events", ["id"])
    op.create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    op.create_index("ix_analytics_events_install_id", "analytics_events", ["install_id"])
    op.create_index("ix_analytics_events_event_name", "analytics_events", ["event_name"])
    op.create_index("ix_analytics_events_occurred_at", "analytics_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("analytics_events")
    op.drop_table("quest_awards")
    op.drop_table("player_profiles")
