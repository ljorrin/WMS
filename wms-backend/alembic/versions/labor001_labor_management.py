"""Labor Management — labor_standards y labor_tasks (FR-090…093)

Revision ID: labor001
Revises: c75aced0efec
Create Date: 2026-07-14

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "labor001"
down_revision: Union[str, None] = "c75aced0efec"
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
        "labor_standards",
        sa.Column("warehouse_id", sa.UUID(), nullable=True),
        sa.Column("activity_type", sa.String(length=20), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=True),
        sa.Column("fixed_minutes", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("std_minutes_per_unit", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "warehouse_id", "activity_type", "uom", name="uq_labor_standard_scope"),
    )
    op.create_index("ix_labor_standards_tenant_id", "labor_standards", ["tenant_id"])
    op.create_index("ix_labor_standards_warehouse_id", "labor_standards", ["warehouse_id"])
    op.create_index("ix_labor_standards_tenant_activity", "labor_standards", ["tenant_id", "activity_type"])

    op.create_table(
        "labor_tasks",
        sa.Column("warehouse_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("activity_type", sa.String(length=20), nullable=False),
        sa.Column("reference_type", sa.String(length=30), nullable=True),
        sa.Column("reference_id", sa.UUID(), nullable=True),
        sa.Column("reference_number", sa.String(length=50), nullable=True),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("zone", sa.String(length=50), nullable=True),
        sa.Column("priority", sa.Numeric(precision=4, scale=0), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("uom", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_minutes", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("standard_minutes", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("performance_pct", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("is_interleaved", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_labor_tasks_tenant_id", "labor_tasks", ["tenant_id"])
    op.create_index("ix_labor_tasks_warehouse_id", "labor_tasks", ["warehouse_id"])
    op.create_index("ix_labor_tasks_user_id", "labor_tasks", ["user_id"])
    op.create_index("ix_labor_tasks_zone", "labor_tasks", ["zone"])
    op.create_index("ix_labor_tasks_tenant_status", "labor_tasks", ["tenant_id", "status"])
    op.create_index("ix_labor_tasks_user_status", "labor_tasks", ["user_id", "status"])
    op.create_index("ix_labor_tasks_queue", "labor_tasks", ["tenant_id", "warehouse_id", "status", "priority"])


def downgrade() -> None:
    op.drop_table("labor_tasks")
    op.drop_table("labor_standards")
