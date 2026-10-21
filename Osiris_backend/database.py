from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

import os

import settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# We use SQLite for local development. It will create a file named 'fitness_mvp.db'
# NOTE: For Production Phase 2 (Domain Expansion), this MUST be migrated to 
# PostgreSQL with the PostGIS extension to handle spatial polygon intersect queries.
SQLALCHEMY_DATABASE_URL = settings.database_url(f"sqlite:///{os.path.join(BASE_DIR, 'fitness_mvp.db')}")

# The engine is the actual connection to the database.
# (check_same_thread=False is a specific requirement just for SQLite in FastAPI)
_IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite")


def _pool_options() -> dict:
    """Connection pool for a server database. FastAPI runs sync endpoints on a 40-thread pool,
    so the default 5 + 10 overflow makes requests queue for a connection under load. Pre-ping
    drops connections the server or a proxy closed while idle; recycle stays under typical
    idle timeouts. SQLite keeps SQLAlchemy's own per-file pool."""
    if _IS_SQLITE:
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": int(os.environ.get("OSIRIS_DB_POOL_SIZE", "20")),
        "max_overflow": int(os.environ.get("OSIRIS_DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.environ.get("OSIRIS_DB_POOL_TIMEOUT", "10")),
        "pool_recycle": int(os.environ.get("OSIRIS_DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True,
    }


engine = create_engine(SQLALCHEMY_DATABASE_URL, **_pool_options())


def _sqlite_pragmas(dbapi_connection, _record):
    """Endpoints run concurrently in FastAPI's thread pool. In SQLite's default rollback
    journal a reader blocks the writer's commit, and the writer's retry back-off produced
    second-long tail latencies on write endpoints. WAL lets readers and the single writer
    proceed together; busy_timeout bounds the wait instead of failing fast.

    `optimize=0x10002` refreshes planner statistics where they are missing or stale. Without
    them SQLite picked the index on verification_status (nearly every run is "accepted") over
    the one on user_id, so one player's run totals scanned every run: 15 ms -> 0.05 ms at 100k
    runs. SQLite before 3.46 ignores the 0x10000 bit and this is a no-op."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA optimize=0x10002")
    cursor.close()


if _IS_SQLITE:
    event.listen(engine, "connect", _sqlite_pragmas)

def optimize(bind=None) -> None:
    """Refresh SQLite planner statistics; pooled connections live for days, so the API runs this
    nightly as well as on connect. Other databases keep their own statistics."""
    target = bind if bind is not None else engine
    if target.dialect.name != "sqlite":
        return
    with target.connect() as conn:
        conn.exec_driver_sql("PRAGMA optimize")


# SessionLocal is what we will use to actually talk to the database in our API endpoints
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class that all of our Database Models will inherit from
Base = declarative_base()