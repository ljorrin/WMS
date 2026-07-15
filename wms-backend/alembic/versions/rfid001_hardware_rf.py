"""Hardware RFID/RF — rfid_readers, rfid_antennas, rfid_tag_reads (Fase 2)

Revision ID: rfid001
Revises: slotting001
Create Date: 2026-07-15

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "rfid001"
down_revision: Union[str, None] = "slotting001"
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
        "rfid_readers",
        sa.Column("warehouse_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("vendor", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False, server_default="5084"),
        sa.Column("protocol", sa.String(length=10), nullable=False, server_default="LLRP"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="inactive"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_rfid_reader_code"),
    )
    op.create_index("ix_rfid_readers_tenant_id", "rfid_readers", ["tenant_id"])
    op.create_index("ix_rfid_readers_warehouse_id", "rfid_readers", ["warehouse_id"])
    op.create_index("ix_rfid_readers_warehouse", "rfid_readers", ["warehouse_id", "status"])

    op.create_table(
        "rfid_antennas",
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("antenna_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("zone_id", sa.UUID(), nullable=True),
        sa.Column("transmit_power_dbm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_base_columns(),
        sa.ForeignKeyConstraint(["reader_id"], ["rfid_readers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reader_id", "antenna_number", name="uq_rfid_antenna_port"),
    )
    op.create_index("ix_rfid_antennas_tenant_id", "rfid_antennas", ["tenant_id"])
    op.create_index("ix_rfid_antennas_reader_id", "rfid_antennas", ["reader_id"])

    op.create_table(
        "rfid_tag_reads",
        sa.Column("warehouse_id", sa.UUID(), nullable=False),
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("antenna_id", sa.UUID(), nullable=True),
        sa.Column("epc_hex", sa.String(length=24), nullable=False),
        sa.Column("epc_scheme", sa.String(length=10), nullable=False, server_default="unknown"),
        sa.Column("gtin", sa.String(length=14), nullable=True),
        sa.Column("sscc", sa.String(length=18), nullable=True),
        sa.Column("serial", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.UUID(), nullable=True),
        sa.Column("rssi_dbm", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("process_notes", sa.String(length=255), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reader_id"], ["rfid_readers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["antenna_id"], ["rfid_antennas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rfid_tag_reads_tenant_id", "rfid_tag_reads", ["tenant_id"])
    op.create_index("ix_rfid_tag_reads_epc_hex", "rfid_tag_reads", ["epc_hex"])
    op.create_index("ix_rfid_tag_reads_warehouse_time", "rfid_tag_reads", ["warehouse_id", "read_at"])
    op.create_index("ix_rfid_tag_reads_epc", "rfid_tag_reads", ["tenant_id", "epc_hex"])
    op.create_index("ix_rfid_tag_reads_unprocessed", "rfid_tag_reads", ["warehouse_id", "processed"])


def downgrade() -> None:
    op.drop_table("rfid_tag_reads")
    op.drop_table("rfid_antennas")
    op.drop_table("rfid_readers")
