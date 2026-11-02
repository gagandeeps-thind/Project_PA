"""Arise public routes: activity type, visibility and the public line on courses

Revision ID: a7e1c0d2f4b9
Revises: f4b8c2d6e9a1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7e1c0d2f4b9"
down_revision: Union[str, Sequence[str], None] = "f4b8c2d6e9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("activity_type", sa.String(), nullable=False, server_default="run"))
    op.add_column("courses", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("courses", sa.Column("hide_ends", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("courses", sa.Column("public_route_json", sa.String(), nullable=True))
    op.create_index("ix_courses_is_public", "courses", ["is_public"])


def downgrade() -> None:
    op.drop_index("ix_courses_is_public", table_name="courses")
    op.drop_column("courses", "public_route_json")
    op.drop_column("courses", "hide_ends")
    op.drop_column("courses", "is_public")
    op.drop_column("courses", "activity_type")
