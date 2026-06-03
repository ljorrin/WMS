"""YMS — docks y yard_appointments (FR-060)

Revision ID: yms0001
Revises: bcf617d7ac65
Create Date: 2026-06-02

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "yms0001"
down_revision: Union[str, None] = "bcf617d7ac65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_columns():
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "docks",
        sa.Column("warehouse_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("dock_type", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_id", "code", name="uq_docks_warehouse_code"),
    )
    op.create_index("ix_docks_tenant_id", "docks", ["tenant_id"])
    op.create_index("ix_docks_warehouse_id", "docks", ["warehouse_id"])
    op.create_index("ix_docks_tenant_warehouse", "docks", ["tenant_id", "warehouse_id"])

    op.create_table(
        "yard_appointments",
        sa.Column("warehouse_id", sa.UUID(), nullable=False),
        sa.Column("dock_id", sa.UUID(), nullable=True),
        sa.Column("appointment_number", sa.String(length=50), nullable=False),
        sa.Column("appointment_type", sa.String(length=20), nullable=True),
        sa.Column("carrier_name", sa.String(length=200), nullable=True),
        sa.Column("vehicle_plate", sa.String(length=20), nullable=True),
        sa.Column("driver_name", sa.String(length=200), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("at_dock_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("queue_position", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dock_id"], ["docks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_id", "appointment_number", name="uq_yard_appt_warehouse_number"),
    )
    op.create_index("ix_yard_appointments_tenant_id", "yard_appointments", ["tenant_id"])
    op.create_index("ix_yard_appointments_warehouse_id", "yard_appointments", ["warehouse_id"])
    op.create_index("ix_yard_appointments_scheduled_at", "yard_appointments", ["scheduled_at"])
    op.create_index("ix_yard_appt_tenant_status", "yard_appointments", ["tenant_id", "status"])
    op.create_index("ix_yard_appt_dock", "yard_appointments", ["dock_id"])


def downgrade() -> None:
    op.drop_table("yard_appointments")
    op.drop_table("docks")
