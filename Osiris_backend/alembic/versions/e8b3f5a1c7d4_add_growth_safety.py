"""Growth G4: consent records, reports, blocks, session revocation

Revision ID: e8b3f5a1c7d4
Revises: d4a9c7e2f1b6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8b3f5a1c7d4"
down_revision: Union[str, Sequence[str], None] = "d4a9c7e2f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("tokens_valid_after", sa.DateTime(), nullable=True))
    with op.batch_alter_table("player_profiles") as batch:
        batch.add_column(sa.Column("consent_required", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_records_id", "consent_records", ["id"])
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("resolution_note", sa.String(), nullable=True),
        sa.Column("reviewed_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_admin_id"], ["admins.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reporter_id", "target_type", "target_id", name="uq_reports_reporter_target"),
    )
    op.create_index("ix_reports_id", "reports", ["id"])
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_target_type", "reports", ["target_type"])
    op.create_index("ix_reports_target_id", "reports", ["target_id"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_created_at", "reports", ["created_at"])

    op.create_table(
        "user_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_pair"),
    )
    op.create_index("ix_user_blocks_id", "user_blocks", ["id"])
    op.create_index("ix_user_blocks_blocker_id", "user_blocks", ["blocker_id"])
    op.create_index("ix_user_blocks_blocked_id", "user_blocks", ["blocked_id"])


def downgrade() -> None:
    op.drop_table("user_blocks")
    op.drop_table("reports")
    op.drop_table("consent_records")
    with op.batch_alter_table("player_profiles") as batch:
        batch.drop_column("consent_required")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("tokens_valid_after")
