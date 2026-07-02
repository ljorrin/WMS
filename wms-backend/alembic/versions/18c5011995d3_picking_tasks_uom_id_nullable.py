"""picking_tasks.uom_id nullable

Revision ID: 18c5011995d3
Revises: e4736cd6ea66
Create Date: 2026-07-02 00:42:39.780412

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '18c5011995d3'
down_revision: Union[str, None] = 'e4736cd6ea66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('picking_tasks', 'uom_id',
               existing_type=sa.UUID(),
               nullable=True)


def downgrade() -> None:
    op.alter_column('picking_tasks', 'uom_id',
               existing_type=sa.UUID(),
               nullable=False)
