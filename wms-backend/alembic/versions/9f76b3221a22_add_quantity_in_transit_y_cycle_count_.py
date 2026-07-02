"""add quantity_in_transit y cycle_count name

Revision ID: 9f76b3221a22
Revises: yms0001
Create Date: 2026-07-01 23:53:34.406460

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9f76b3221a22'
down_revision: Union[str, None] = 'yms0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cycle_counts', sa.Column('name', sa.String(length=200), nullable=True, comment='Nombre descriptivo del conteo'))
    op.add_column('inventory_levels', sa.Column('quantity_in_transit', sa.Numeric(precision=15, scale=4), nullable=False, server_default='0', comment='Cantidad en movimiento entre bodegas/ubicaciones'))
    op.alter_column('inventory_levels', 'quantity_in_transit', server_default=None)
    # slug ya tenía un índice no-único (drift respecto al modelo, que declara unique=True);
    # se recrea como único para que coincida con la restricción real del modelo.
    op.drop_index('ix_tenants_slug', table_name='tenants')
    op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_tenants_slug'), table_name='tenants')
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=False)
    op.drop_column('inventory_levels', 'quantity_in_transit')
    op.drop_column('cycle_counts', 'name')
