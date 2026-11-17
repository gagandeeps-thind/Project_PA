"""enable row level security on every table (PostgreSQL only)

Supabase serves the public schema through its Data API (PostgREST) to anyone holding the project's
anon key. With RLS on and no policies, that API reads and writes nothing, while the backend, which
connects as the tables' owner, is not affected (RLS does not apply to a table's owner unless FORCEd).
Six feed tables and app_store_purchases already had it; this covers the rest, including tables added
later by hand. A no-op on SQLite.

Revision ID: b8e3f1a6c2d4
Revises: a7d2f4c9e1b6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e3f1a6c2d4"
down_revision: Union[str, Sequence[str], None] = "a7d2f4c9e1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Ordinary and partitioned tables in the migration's schema that the connected role owns (only the owner
# may ALTER them) and that have RLS off. Re-running finds nothing, so a repeated boot is a no-op.
_TABLES_WITHOUT_RLS = sa.text("""
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity
      AND pg_get_userbyid(c.relowner) = current_user
    ORDER BY c.relname
""")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for (table,) in bind.execute(_TABLES_WITHOUT_RLS).fetchall():
        # The name comes from the catalog; quoting keeps any unusual name a single identifier.
        op.execute(f'ALTER TABLE "{table.replace(chr(34), chr(34) * 2)}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    # Left on: the tables that had RLS before this revision cannot be told apart, and turning it off
    # would reopen the Data API.
    pass
