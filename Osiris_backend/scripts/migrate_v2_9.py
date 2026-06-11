"""One-time migration to bring an existing `fitness_mvp.db` up to the v2.9 schema.

What it adds (idempotent — safe to re-run):
  - merchants.payment_status        (default 'payment_pending')
  - merchants.payment_provider_id   (NULL)
  - merchants.pilot_fee_cents       (default 5000)
  - merchants.last_payment_at       (NULL)

Why a script and not a SQLAlchemy auto-migration: SQLAlchemy's `Base.metadata.create_all`
only creates missing tables; it never adds columns to existing ones. Phase 2 introduces
Alembic for proper migrations; for now this script is the bridge.

Run it from the Osiris_backend dir:

    python scripts/migrate_v2_9.py
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
DB_PATH = os.path.join(BACKEND_DIR, "fitness_mvp.db")

ADDITIONS = [
    ("payment_status",       "TEXT DEFAULT 'payment_pending'"),
    ("payment_provider_id",  "TEXT"),
    ("pilot_fee_cents",      "INTEGER DEFAULT 5000"),
    ("last_payment_at",      "DATETIME"),
]


def existing_columns(conn: sqlite3.Connection, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"No DB at {DB_PATH} — nothing to migrate. (A fresh start will use the v2.9 schema automatically.)")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        # Ensure the merchants table exists at all
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "merchants" not in tables:
            print("merchants table doesn't exist yet — start the app once to create it, then re-run this script.")
            return

        existing = existing_columns(conn, "merchants")
        added = []
        for col, ddl in ADDITIONS:
            if col in existing:
                continue
            conn.execute(f"ALTER TABLE merchants ADD COLUMN {col} {ddl}")
            added.append(col)
        conn.commit()

        if added:
            print(f"Added columns to merchants: {', '.join(added)}")
        else:
            print("merchants table already at v2.9 schema — nothing to do.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
