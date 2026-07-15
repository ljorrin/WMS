"""box_types (maestro de tipos de caja/empaque)

Revision ID: 44b1b3c2a183
Revises: 18c5011995d3
Create Date: 2026-07-14 00:00:00.000000

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '44b1b3c2a183'
down_revision: Union[str, None] = '18c5011995d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'box_types',
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('length_cm', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('width_cm', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('height_cm', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('max_weight_kg', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False, comment='Identificador unico universal del registro'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Fecha y hora de creacion del registro (UTC)'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Fecha y hora de ultima modificacion (UTC)'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='Fecha de eliminacion logica. NULL = activo.'),
        sa.Column('deleted_by', postgresql.UUID(), nullable=True, comment='Usuario que elimino logicamente el registro'),
        sa.Column('created_by', postgresql.UUID(), nullable=True, comment='UUID del usuario que creo el registro'),
        sa.Column('updated_by', postgresql.UUID(), nullable=True, comment='UUID del usuario que hizo la ultima modificacion'),
        sa.Column('tenant_id', postgresql.UUID(), nullable=False, comment='ID del tenant (empresa). Aislamiento de datos.'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_box_types_tenant_code'),
    )
    op.create_index(op.f('ix_box_types_tenant_id'), 'box_types', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_box_types_tenant_id'), table_name='box_types')
    op.drop_table('box_types')
