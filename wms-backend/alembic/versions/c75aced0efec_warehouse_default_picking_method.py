"""warehouses.default_picking_method

Revision ID: c75aced0efec
Revises: 44b1b3c2a183
Create Date: 2026-07-15 00:00:00.000000

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c75aced0efec'
down_revision: Union[str, None] = '44b1b3c2a183'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'warehouses',
        sa.Column(
            'default_picking_method', sa.String(length=20),
            nullable=False, server_default='discrete',
            comment='Metodo de picking por defecto al crear una Wave: '
                    'discrete | batch | zone | cluster',
        ),
    )


def downgrade() -> None:
    op.drop_column('warehouses', 'default_picking_method')
