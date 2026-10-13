"""Growth G3: communities, featured challenges, seasons, local ranking fields

Revision ID: d4a9c7e2f1b6
Revises: c2f6a8d3b915
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4a9c7e2f1b6"
down_revision: Union[str, Sequence[str], None] = "c2f6a8d3b915"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("player_profiles") as batch:
        batch.add_column(sa.Column("city", sa.String(), nullable=True))
        batch.add_column(sa.Column("leaderboard_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_index("ix_player_profiles_city", ["city"])

    op.create_table(
        "communities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("brand_color", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("join_code", sa.String(), nullable=True),
        sa.Column("weekly_team_goal_km", sa.Float(), nullable=False),
        sa.Column("perk_text", sa.String(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("status_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_communities_id", "communities", ["id"])
    op.create_index("ix_communities_slug", "communities", ["slug"], unique=True)
    op.create_index("ix_communities_city", "communities", ["city"])
    op.create_index("ix_communities_owner_user_id", "communities", ["owner_user_id"])
    op.create_index("ix_communities_status", "communities", ["status"])

    op.create_table(
        "community_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("community_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("community_id", "user_id", name="uq_community_members_community_user"),
    )
    op.create_index("ix_community_members_id", "community_members", ["id"])
    op.create_index("ix_community_members_community_id", "community_members", ["community_id"])
    op.create_index("ix_community_members_user_id", "community_members", ["user_id"])

    op.create_table(
        "community_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("community_id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("added_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"]),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"]),
        sa.ForeignKeyConstraint(["added_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("community_id", "challenge_id", name="uq_community_challenges"),
    )
    op.create_index("ix_community_challenges_id", "community_challenges", ["id"])
    op.create_index("ix_community_challenges_community_id", "community_challenges", ["community_id"])
    op.create_index("ix_community_challenges_challenge_id", "community_challenges", ["challenge_id"])

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("perk_text", sa.String(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seasons_id", "seasons", ["id"])
    op.create_index("ix_seasons_slug", "seasons", ["slug"], unique=True)
    op.create_index("ix_seasons_city", "seasons", ["city"])

    op.create_table(
        "season_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "user_id", name="uq_season_entries_season_user"),
    )
    op.create_index("ix_season_entries_id", "season_entries", ["id"])
    op.create_index("ix_season_entries_season_id", "season_entries", ["season_id"])
    op.create_index("ix_season_entries_user_id", "season_entries", ["user_id"])


def downgrade() -> None:
    op.drop_table("season_entries")
    op.drop_table("seasons")
    op.drop_table("community_challenges")
    op.drop_table("community_members")
    op.drop_table("communities")
    with op.batch_alter_table("player_profiles") as batch:
        batch.drop_index("ix_player_profiles_city")
        batch.drop_column("leaderboard_opt_in")
        batch.drop_column("city")
