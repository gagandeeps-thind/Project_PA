from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# We use SQLite for local development. It will create a file named 'fitness_mvp.db'
# NOTE: For Production Phase 2 (Domain Expansion), this MUST be migrated to 
# PostgreSQL with the PostGIS extension to handle spatial polygon intersect queries.
SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'fitness_mvp.db')}"

# The engine is the actual connection to the database.
# (check_same_thread=False is a specific requirement just for SQLite in FastAPI)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


def _sqlite_pragmas(dbapi_connection, _record):
    """Endpoints run concurrently in FastAPI's thread pool. In SQLite's default rollback
    journal a reader blocks the writer's commit, and the writer's retry back-off produced
    second-long tail latencies on write endpoints. WAL lets readers and the single writer
    proceed together; busy_timeout bounds the wait instead of failing fast."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    event.listen(engine, "connect", _sqlite_pragmas)

# SessionLocal is what we will use to actually talk to the database in our API endpoints
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class that all of our Database Models will inherit from
Base = declarative_base()