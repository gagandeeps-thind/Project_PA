"""R2: courses, challenges, attempts, badges, audit events, user suspension

Revision ID: a3e8d5c2f710
Revises: 7c2a4b1d9e01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3e8d5c2f710"
down_revision: Union[str, Sequence[str], None] = "7c2a4b1d9e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _user_columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade() -> None:
    existing = _user_columns()
    with op.batch_alter_table("users") as batch:
        if "suspended_at" not in existing:
            batch.add_column(sa.Column("suspended_at", sa.DateTime(), nullable=True))
        if "suspension_reason" not in existing:
            batch.add_column(sa.Column("suspension_reason", sa.String(), nullable=True))

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("source_run_session_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules_version", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("benchmark_seconds", sa.Float(), nullable=False),
        sa.Column("is_loop", sa.Boolean(), nullable=False),
        sa.Column("start_lat", sa.Float(), nullable=False),
        sa.Column("start_lng", sa.Float(), nullable=False),
        sa.Column("finish_lat", sa.Float(), nullable=False),
        sa.Column("finish_lng", sa.Float(), nullable=False),
        sa.Column("route_json", sa.String(), nullable=False),
        sa.Column("route_hash", sa.String(), nullable=False),
        sa.Column("public_lat", sa.Float(), nullable=False),
        sa.Column("public_lng", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_run_session_id"], ["run_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_run_session_id"),
        if_not_exists=True,
    )
    for col in ("id", "owner_id", "status", "route_hash", "public_lat", "public_lng"):
        op.create_index(f"ix_courses_{col}", "courses", [col], unique=False, if_not_exists=True)

    op.create_table(
        "challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("rules_version", sa.String(), nullable=False),
        sa.Column("course_version", sa.Integer(), nullable=False),
        sa.Column("target_seconds", sa.Float(), nullable=False),
        sa.Column("entry_crystals", sa.Integer(), nullable=False),
        sa.Column("reward_policy", sa.String(), nullable=False),
        sa.Column("win_xp", sa.Integer(), nullable=False),
        sa.Column("participation_xp", sa.Integer(), nullable=False),
        sa.Column("eligibility", sa.String(), nullable=False),
        sa.Column("privacy_mode", sa.String(), nullable=False),
        sa.Column("safety_notes", sa.String(), nullable=True),
        sa.Column("opens_at", sa.DateTime(), nullable=False),
        sa.Column("closes_at", sa.DateTime(), nullable=False),
        sa.Column("terms_hash", sa.String(), nullable=False),
        sa.Column("publish_idempotency_key", sa.String(), nullable=True),
        sa.Column("status_reason", sa.String(), nullable=True),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("publish_idempotency_key"),
        if_not_exists=True,
    )
    for col in ("id", "course_id", "creator_id", "status", "closes_at"):
        op.create_index(f"ix_challenges_{col}", "challenges", [col], unique=False, if_not_exists=True)

    op.create_table(
        "challenge_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("terms_hash", sa.String(), nullable=False),
        sa.Column("run_session_id", sa.Integer(), nullable=True),
        sa.Column("elapsed_seconds", sa.Float(), nullable=True),
        sa.Column("course_coverage", sa.Float(), nullable=True),
        sa.Column("reason_codes_json", sa.String(), nullable=False),
        sa.Column("xp_awarded", sa.Integer(), nullable=False),
        sa.Column("defender_xp_awarded", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("review_note", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["run_session_id"], ["run_sessions.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_admin_id"], ["admins.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_session_id"),
        sa.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_attempts_challenge_user"),
        if_not_exists=True,
    )
    for col in ("id", "challenge_id", "user_id", "status"):
        op.create_index(f"ix_challenge_attempts_{col}", "challenge_attempts", [col], unique=False, if_not_exists=True)

    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("badge_code", sa.String(), nullable=False),
        sa.Column("awarded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "badge_code", name="uq_user_badges_user_badge"),
        if_not_exists=True,
    )
    op.create_index("ix_user_badges_id", "user_badges", ["id"], unique=False, if_not_exists=True)
    op.create_index("ix_user_badges_user_id", "user_badges", ["user_id"], unique=False, if_not_exists=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    for col in ("id", "action", "entity_type", "entity_id", "created_at"):
        op.create_index(f"ix_audit_events_{col}", "audit_events", [col], unique=False, if_not_exists=True)


def downgrade() -> None:
    for col in ("id", "action", "entity_type", "entity_id", "created_at"):
        op.drop_index(f"ix_audit_events_{col}", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_user_badges_user_id", table_name="user_badges")
    op.drop_index("ix_user_badges_id", table_name="user_badges")
    op.drop_table("user_badges")
    for col in ("id", "challenge_id", "user_id", "status"):
        op.drop_index(f"ix_challenge_attempts_{col}", table_name="challenge_attempts")
    op.drop_table("challenge_attempts")
    for col in ("id", "course_id", "creator_id", "status", "closes_at"):
        op.drop_index(f"ix_challenges_{col}", table_name="challenges")
    op.drop_table("challenges")
    for col in ("id", "owner_id", "status", "route_hash", "public_lat", "public_lng"):
        op.drop_index(f"ix_courses_{col}", table_name="courses")
    op.drop_table("courses")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("suspension_reason")
        batch.drop_column("suspended_at")
