"""Marca de envío al TMS en shipments (push del contrato canónico)

Revision ID: tms002
Revises: tms001
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "tms002"
down_revision: Union[str, None] = "tms001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shipments", sa.Column("tms_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("shipments", sa.Column("tms_order_id", sa.String(64), nullable=True))
    op.add_column("shipments", sa.Column("tms_last_error", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("shipments", "tms_last_error")
    op.drop_column("shipments", "tms_order_id")
    op.drop_column("shipments", "tms_sent_at")
