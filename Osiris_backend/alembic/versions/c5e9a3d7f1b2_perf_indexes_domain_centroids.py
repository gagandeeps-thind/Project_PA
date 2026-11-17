"""performance: indexes for hot filters, and domain centroid columns

Adds domains.centroid_lat / centroid_lng (filled from geometry_json here, kept in step by the model)
so nearby-domain searches prefilter in SQL, and the indexes the leaderboards, feeds, PR checks and
nightly jobs filter or sort on.

On PostgreSQL every index is built with CREATE INDEX CONCURRENTLY IF NOT EXISTS outside the
migration transaction, so a deploy never blocks writes while a large table is indexed, and a rerun
after a partial run only builds what is missing. Nothing is dropped on upgrade.

Revision ID: c5e9a3d7f1b2
Revises: b8e3f1a6c2d4
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5e9a3d7f1b2"
down_revision: Union[str, Sequence[str], None] = "b8e3f1a6c2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, table, columns); mirrored in models.py so `alembic check` stays clean.
INDEXES = [
    ("ix_run_sessions_verif_finished", "run_sessions", ["verification_status", "finished_at"]),
    ("ix_run_sessions_user_verif_finished", "run_sessions", ["user_id", "verification_status", "finished_at"]),
    ("ix_exercise_sessions_key_status_created", "exercise_sessions", ["exercise_key", "status", "created_at"]),
    ("ix_exercise_sessions_user_local_date", "exercise_sessions", ["user_id", "local_date"]),
    ("ix_challenge_attempts_outcome_decided", "challenge_attempts", ["outcome", "decided_at"]),
    ("ix_users_xp_id", "users", ["xp", "id"]),
    ("ix_training_sessions_user_local_date", "training_sessions", ["user_id", "local_date"]),
    ("ix_training_sessions_social_post_id", "training_sessions", ["social_post_id"]),
    ("ix_social_posts_user_id_id", "social_posts", ["user_id", "id"]),
    ("ix_player_notifications_user_read", "player_notifications", ["user_id", "read_at"]),
    ("ix_bounties_merchant_id", "bounties", ["merchant_id"]),
    ("ix_telemetry_sessions_created_at", "telemetry_sessions", ["created_at"]),
    ("ix_domains_owner_id", "domains", ["owner_id"]),
    ("ix_domains_type_centroid", "domains", ["defense_type", "centroid_lat"]),
]
BACKFILL_BATCH = 500


def _centroid(geometry_json):
    # Frozen copy of models.geometry_centroid: a migration must not change when app code does.
    try:
        points = json.loads(geometry_json or "[]")
        return (sum(p["lat"] for p in points) / len(points), sum(p["lng"] for p in points) / len(points))
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return None, None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("domains")}
    for column in ("centroid_lat", "centroid_lng"):
        if column not in existing:
            op.add_column("domains", sa.Column(column, sa.Float(), nullable=True))

    domains = sa.table("domains", sa.column("id", sa.Integer), sa.column("geometry_json", sa.String),
                       sa.column("centroid_lat", sa.Float), sa.column("centroid_lng", sa.Float))
    last_id = 0
    while True:
        rows = bind.execute(
            sa.select(domains.c.id, domains.c.geometry_json)
            .where(domains.c.id > last_id, domains.c.centroid_lat.is_(None), domains.c.geometry_json.isnot(None))
            .order_by(domains.c.id).limit(BACKFILL_BATCH)
        ).fetchall()
        if not rows:
            break
        for domain_id, geometry_json in rows:
            lat, lng = _centroid(geometry_json)
            if lat is not None:
                bind.execute(domains.update().where(domains.c.id == domain_id).values(centroid_lat=lat, centroid_lng=lng))
        last_id = rows[-1][0]

    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for name, table, columns in INDEXES:
                op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({", ".join(columns)})')
    else:
        for name, table, columns in INDEXES:
            op.create_index(name, table, columns, if_not_exists=True)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
    with op.batch_alter_table("domains") as batch:
        batch.drop_column("centroid_lng")
        batch.drop_column("centroid_lat")
