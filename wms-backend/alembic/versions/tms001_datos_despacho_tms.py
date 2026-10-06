"""Datos de despacho para el TMS: coordenadas, contacto, ventana y tipo de carga

Revision ID: tms001
Revises: 65415b0a6ae3
Create Date: 2026-10-05

Añade a `sales_orders` y `customers` los datos que el contrato canónico del TMS
necesita para rutear sin geocodificar ni completar a mano.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "tms001"
down_revision: Union[str, None] = "65415b0a6ae3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SO_COLUMNS = [
    ("ship_to_province", sa.String(100)),
    ("ship_to_contact_name", sa.String(200)),
    ("ship_to_email", sa.String(200)),
    ("ship_to_latitude", sa.Numeric(10, 7)),
    ("ship_to_longitude", sa.Numeric(11, 7)),
    ("ship_to_gln", sa.String(13)),
    ("delivery_window_start", sa.DateTime(timezone=True)),
    ("delivery_window_end", sa.DateTime(timezone=True)),
    ("service_time_min", sa.Integer()),
    ("cargo_type", sa.String(30)),
]

CUSTOMER_COLUMNS = [
    ("delivery_latitude", sa.Numeric(10, 7)),
    ("delivery_longitude", sa.Numeric(11, 7)),
    ("receiving_hours_from", sa.String(5)),
    ("receiving_hours_to", sa.String(5)),
    ("service_time_min", sa.Integer()),
]


def upgrade() -> None:
    for name, type_ in SO_COLUMNS:
        op.add_column("sales_orders", sa.Column(name, type_, nullable=True))
    for name, type_ in CUSTOMER_COLUMNS:
        op.add_column("customers", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(CUSTOMER_COLUMNS):
        op.drop_column("customers", name)
    for name, _ in reversed(SO_COLUMNS):
        op.drop_column("sales_orders", name)
