"""Social tab: post photos, workout attachments and direct messages

Revision ID: e5c1a9d7b3f2
Revises: d4e8a1b2c3f5
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5c1a9d7b3f2"
down_revision: Union[str, Sequence[str], None] = "d4e8a1b2c3f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive only: prod (Postgres) runs this on boot.
    op.add_column("social_posts", sa.Column("attachments_json", sa.String(), nullable=False, server_default="[]"))
    op.add_column("social_posts", sa.Column("chart_json", sa.String(), nullable=True))

    op.create_table(
        "post_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("social_posts.id"), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("jpeg", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("post_id", name="uq_post_photos_post_id"),
        sa.UniqueConstraint("token", name="uq_post_photos_token"),
    )
    op.create_index("ix_post_photos_id", "post_photos", ["id"])

    op.create_table(
        "direct_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pair_key", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_direct_messages_id", "direct_messages", ["id"])
    op.create_index("ix_direct_messages_sender_id", "direct_messages", ["sender_id"])
    op.create_index("ix_direct_messages_pair_id", "direct_messages", ["pair_key", "id"])
    op.create_index("ix_direct_messages_recipient_read", "direct_messages", ["recipient_id", "read_at"])


def downgrade() -> None:
    op.drop_table("direct_messages")
    op.drop_table("post_photos")
    with op.batch_alter_table("social_posts") as batch:
        batch.drop_column("chart_json")
        batch.drop_column("attachments_json")
