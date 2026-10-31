"""Alembic environment for Osiris.

Wires Alembic up to:
  - The same SQLite URL the FastAPI app uses (`database.SQLALCHEMY_DATABASE_URL`),
    so dev databases stay consistent without a separate config knob.
  - The full `models.Base.metadata` so `--autogenerate` can diff against it.

For PostgreSQL set `OSIRIS_DATABASE_URL` (or `OSIRIS_DATABASE_URL_FILE`); it is resolved by
`settings.database_url`, exactly as the app resolves it.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the backend package importable so `import database` / `import models` work
# regardless of where `alembic` is invoked from.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402  — uses SQLALCHEMY_DATABASE_URL
import models    # noqa: E402,F401 — needed so Base.metadata sees every table

config = context.config

# Migrate the database the app connects to (OSIRIS_DATABASE_URL wins over alembic.ini).
# The config is a ConfigParser: `%` in a URL-encoded password must be doubled.
db_url = database.SQLALCHEMY_DATABASE_URL
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = database.Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite needs batch mode for ALTER TABLE; harmless on Postgres.
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
