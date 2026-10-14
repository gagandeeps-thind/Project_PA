"""Growth G2: share cards, challenge invites, referral status

Revision ID: c2f6a8d3b915
Revises: b7d1e4f9a2c3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f6a8d3b915"
down_revision: Union[str, Sequence[str], None] = "b7d1e4f9a2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("player_profiles") as batch:
        batch.add_column(sa.Column("referral_status", sa.String(), nullable=False, server_default="none"))
        batch.add_column(sa.Column("signup_install_id", sa.String(), nullable=True))
        batch.create_index("ix_player_profiles_signup_install_id", ["signup_install_id"])

    op.create_table(
        "share_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("headline", sa.String(), nullable=False),
        sa.Column("stats_json", sa.String(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "entity_id", name="uq_share_cards_user_kind_entity"),
    )
    op.create_index("ix_share_cards_id", "share_cards", ["id"])
    op.create_index("ix_share_cards_token", "share_cards", ["token"], unique=True)
    op.create_index("ix_share_cards_user_id", "share_cards", ["user_id"])

    op.create_table(
        "challenge_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("inviter_id", sa.Integer(), nullable=False),
        sa.Column("opens", sa.Integer(), nullable=False),
        sa.Column("signups", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"]),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_id", "inviter_id", name="uq_challenge_invites_challenge_inviter"),
    )
    op.create_index("ix_challenge_invites_id", "challenge_invites", ["id"])
    op.create_index("ix_challenge_invites_token", "challenge_invites", ["token"], unique=True)
    op.create_index("ix_challenge_invites_challenge_id", "challenge_invites", ["challenge_id"])
    op.create_index("ix_challenge_invites_inviter_id", "challenge_invites", ["inviter_id"])


def downgrade() -> None:
    op.drop_table("challenge_invites")
    op.drop_table("share_cards")
    with op.batch_alter_table("player_profiles") as batch:
        batch.drop_index("ix_player_profiles_signup_install_id")
        batch.drop_column("signup_install_id")
        batch.drop_column("referral_status")
