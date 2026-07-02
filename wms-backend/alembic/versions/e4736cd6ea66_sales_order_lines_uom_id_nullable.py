"""sales_order_lines.uom_id nullable

Revision ID: e4736cd6ea66
Revises: 9f76b3221a22
Create Date: 2026-07-02 00:34:16.658233

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e4736cd6ea66'
down_revision: Union[str, None] = '9f76b3221a22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('sales_order_lines', 'uom_id',
               existing_type=sa.UUID(),
               nullable=True)


def downgrade() -> None:
    op.alter_column('sales_order_lines', 'uom_id',
               existing_type=sa.UUID(),
               nullable=False)
