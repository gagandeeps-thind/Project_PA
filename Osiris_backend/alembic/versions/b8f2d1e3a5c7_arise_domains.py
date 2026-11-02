"""Arise domains: run stats and defense workout on domains, attacks and domain photos

Revision ID: b8f2d1e3a5c7
Revises: a7e1c0d2f4b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8f2d1e3a5c7"
down_revision: Union[str, Sequence[str], None] = "a7e1c0d2f4b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("domains") as batch:
        batch.add_column(sa.Column("distance_m", sa.Float(), nullable=True))
        batch.add_column(sa.Column("duration_s", sa.Float(), nullable=True))
        batch.add_column(sa.Column("source_run_session_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("defense_workout_json", sa.String(), nullable=True))
        batch.add_column(sa.Column("pending_workout_json", sa.String(), nullable=True))
        batch.add_column(sa.Column("pending_workout_issued_at", sa.DateTime(), nullable=True))
        batch.create_unique_constraint("uq_domains_source_run_session_id", ["source_run_session_id"])
        batch.create_foreign_key("fk_domains_source_run_session_id", "run_sessions", ["source_run_session_id"], ["id"])

    op.create_table(
        "arise_attacks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attacker_id", sa.Integer(), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("run_session_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reasons_json", sa.String(), nullable=False),
        sa.Column("workout_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["attacker_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.ForeignKeyConstraint(["run_session_id"], ["run_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_session_id"),
    )
    op.create_index("ix_arise_attacks_id", "arise_attacks", ["id"])
    op.create_index("ix_arise_attacks_attacker_id", "arise_attacks", ["attacker_id"])
    op.create_index("ix_arise_attacks_domain_id", "arise_attacks", ["domain_id"])

    op.create_table(
        "domain_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("jpeg", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain_id"),
    )
    op.create_index("ix_domain_photos_id", "domain_photos", ["id"])


def downgrade() -> None:
    op.drop_index("ix_domain_photos_id", table_name="domain_photos")
    op.drop_table("domain_photos")
    op.drop_index("ix_arise_attacks_domain_id", table_name="arise_attacks")
    op.drop_index("ix_arise_attacks_attacker_id", table_name="arise_attacks")
    op.drop_index("ix_arise_attacks_id", table_name="arise_attacks")
    op.drop_table("arise_attacks")
    with op.batch_alter_table("domains") as batch:
        batch.drop_constraint("fk_domains_source_run_session_id", type_="foreignkey")
        batch.drop_constraint("uq_domains_source_run_session_id", type_="unique")
        for col in ("pending_workout_issued_at", "pending_workout_json", "defense_workout_json",
                    "source_run_session_id", "duration_s", "distance_m"):
            batch.drop_column(col)
