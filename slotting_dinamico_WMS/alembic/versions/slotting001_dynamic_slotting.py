"""Slotting Dinámico — slotting_policies y slotting_recommendations (FR-094…097)

Revision ID: slotting001
Revises: labor001
Create Date: 2026-07-15

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "slotting001"
down_revision: Union[str, None] = "labor001"
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
        "slotting_policies",
        sa.Column("warehouse_id", sa.UUID(), nullable=True),
        sa.Column("strategy", sa.String(length=20), nullable=True),
        sa.Column("velocity_window_days", sa.Integer(), nullable=True),
        sa.Column("abc_a_threshold", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("abc_b_threshold", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("golden_zone_code", sa.String(length=10), nullable=True),
        sa.Column("bulk_zone_code", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "warehouse_id", name="uq_slotting_policy_scope"),
    )
    op.create_index("ix_slotting_policies_tenant_id", "slotting_policies", ["tenant_id"])
    op.create_index("ix_slotting_policies_warehouse_id", "slotting_policies", ["warehouse_id"])

    op.create_table(
        "slotting_recommendations",
        sa.Column("warehouse_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("abc_class", sa.String(length=1), nullable=True),
        sa.Column("velocity_score", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("pick_count", sa.Integer(), nullable=True),
        sa.Column("current_location_id", sa.UUID(), nullable=True),
        sa.Column("current_zone_code", sa.String(length=10), nullable=True),
        sa.Column("recommended_location_id", sa.UUID(), nullable=True),
        sa.Column("recommended_zone_code", sa.String(length=10), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("score_delta", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", sa.UUID(), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recommended_location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_slotting_recommendations_tenant_id", "slotting_recommendations", ["tenant_id"])
    op.create_index("ix_slotting_recommendations_warehouse_id", "slotting_recommendations", ["warehouse_id"])
    op.create_index("ix_slotting_recommendations_product_id", "slotting_recommendations", ["product_id"])
    op.create_index("ix_slotting_recs_tenant_status", "slotting_recommendations", ["tenant_id", "status"])
    op.create_index("ix_slotting_recs_wh_status", "slotting_recommendations", ["warehouse_id", "status"])


def downgrade() -> None:
    op.drop_table("slotting_recommendations")
    op.drop_table("slotting_policies")
