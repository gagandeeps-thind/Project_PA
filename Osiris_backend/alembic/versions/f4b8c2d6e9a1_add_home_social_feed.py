"""add home social feed tables (notifications, follows, dismissed suggestions, posts, reactions, comments)

Revision ID: f4b8c2d6e9a1
Revises: e1a7c4d9b2f5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b8c2d6e9a1"
down_revision: Union[str, Sequence[str], None] = "e1a7c4d9b2f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_profiles", sa.Column("avatar_url", sa.String(), nullable=True))
    op.add_column("player_profiles", sa.Column("bio", sa.String(), nullable=True))

    op.create_table(
        "player_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("action_route", sa.String(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_notifications_id", "player_notifications", ["id"])
    op.create_index("ix_player_notifications_user_id", "player_notifications", ["user_id"])
    op.create_index("ix_player_notifications_kind", "player_notifications", ["kind"])
    op.create_index("ix_player_notifications_created_at", "player_notifications", ["created_at"])

    op.create_table(
        "user_follows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("follower_id", sa.Integer(), nullable=False),
        sa.Column("followed_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["followed_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("follower_id", "followed_id", name="uq_user_follows_pair"),
    )
    op.create_index("ix_user_follows_id", "user_follows", ["id"])
    op.create_index("ix_user_follows_follower_id", "user_follows", ["follower_id"])
    op.create_index("ix_user_follows_followed_id", "user_follows", ["followed_id"])

    op.create_table(
        "dismissed_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dismissed_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["dismissed_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dismissed_user_id", name="uq_dismissed_suggestions_pair"),
    )
    op.create_index("ix_dismissed_suggestions_id", "dismissed_suggestions", ["id"])
    op.create_index("ix_dismissed_suggestions_user_id", "dismissed_suggestions", ["user_id"])
    op.create_index("ix_dismissed_suggestions_dismissed_user_id", "dismissed_suggestions", ["dismissed_user_id"])

    op.create_table(
        "social_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("caption", sa.String(), nullable=False),
        sa.Column("media_url", sa.String(), nullable=True),
        sa.Column("workout_summary_json", sa.String(), nullable=False),
        sa.Column("related_run_id", sa.Integer(), nullable=True),
        sa.Column("related_exercise_session_id", sa.Integer(), nullable=True),
        sa.Column("related_domain_id", sa.Integer(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("share_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["related_run_id"], ["run_sessions.id"]),
        sa.ForeignKeyConstraint(["related_exercise_session_id"], ["exercise_sessions.id"]),
        sa.ForeignKeyConstraint(["related_domain_id"], ["domains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_posts_id", "social_posts", ["id"])
    op.create_index("ix_social_posts_user_id", "social_posts", ["user_id"])
    op.create_index("ix_social_posts_kind", "social_posts", ["kind"])
    op.create_index("ix_social_posts_visibility", "social_posts", ["visibility"])
    op.create_index("ix_social_posts_created_at", "social_posts", ["created_at"])

    op.create_table(
        "post_reactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reaction", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "user_id", name="uq_post_reactions_post_user"),
    )
    op.create_index("ix_post_reactions_id", "post_reactions", ["id"])
    op.create_index("ix_post_reactions_post_id", "post_reactions", ["post_id"])
    op.create_index("ix_post_reactions_user_id", "post_reactions", ["user_id"])

    op.create_table(
        "post_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_post_comments_id", "post_comments", ["id"])
    op.create_index("ix_post_comments_post_id", "post_comments", ["post_id"])
    op.create_index("ix_post_comments_user_id", "post_comments", ["user_id"])
    op.create_index("ix_post_comments_created_at", "post_comments", ["created_at"])

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "player_notifications",
            "user_follows",
            "dismissed_suggestions",
            "social_posts",
            "post_reactions",
            "post_comments",
        ):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("post_comments")
    op.drop_table("post_reactions")
    op.drop_table("social_posts")
    op.drop_table("dismissed_suggestions")
    op.drop_table("user_follows")
    op.drop_table("player_notifications")
    op.drop_column("player_profiles", "bio")
    op.drop_column("player_profiles", "avatar_url")
