"""Index route points by position for Arise heatmaps

Revision ID: c3d9e7f1b2a4
Revises: b8f2d1e3a5c7
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d9e7f1b2a4"
down_revision: Union[str, Sequence[str], None] = "b8f2d1e3a5c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_route_points_lat_lng", "route_points", ["lat", "lng"])


def downgrade() -> None:
    op.drop_index("ix_route_points_lat_lng", table_name="route_points")
