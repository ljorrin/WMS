import asyncio
import os
import sys
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.core import Tenant, User, Warehouse
from app.models.master_data import Customer
from app.models.outbound import SalesOrder, ReturnOrder, ReturnOrderStatus

async def main():
    async with AsyncSessionLocal() as db:
        # Get Tenant
        tenant = (await db.execute(select(Tenant).limit(1))).scalar_one_or_none()
        if not tenant:
            print("No tenant found.")
            return

        # Get User
        user = (await db.execute(select(User).where(User.tenant_id == tenant.id).limit(1))).scalar_one_or_none()
        if not user:
            print("No user found.")
            return

        # Get Warehouse
        warehouse = (await db.execute(select(Warehouse).where(Warehouse.tenant_id == tenant.id).limit(1))).scalar_one_or_none()
        if not warehouse:
            print("No warehouse found.")
            return

        # Get a customer
        customer = (await db.execute(select(Customer).where(Customer.tenant_id == tenant.id).limit(1))).scalar_one_or_none()
        if not customer:
            customer = Customer(id=uuid4(), tenant_id=tenant.id, name="Test Customer", code="CUST-RMA-01")
            db.add(customer)
            await db.flush()

        # Get an existing SalesOrder or create a dummy one if none
        so = (await db.execute(select(SalesOrder).where(SalesOrder.tenant_id == tenant.id).limit(1))).scalar_one_or_none()
        
        returns_to_create = [
            {
                "status": ReturnOrderStatus.REQUESTED,
                "reason": "Producto dañado durante el transporte",
                "return_type": "refund",
                "notes": "El cliente reportó daños en el empaque.",
                "refund_amount": "50.00",
                "received_at": None,
                "inspection_notes": None,
            },
            {
                "status": ReturnOrderStatus.APPROVED,
                "reason": "Cliente ordenó el producto equivocado",
                "return_type": "exchange",
                "notes": "Aprobado para cambio por la talla correcta.",
                "refund_amount": "0",
                "received_at": None,
                "inspection_notes": None,
            },
            {
                "status": ReturnOrderStatus.RECEIVED,
                "reason": "Defecto de fábrica",
                "return_type": "credit",
                "notes": "Se recibió el paquete, pendiente de inspección de calidad.",
                "refund_amount": "120.00",
                "received_at": datetime.now(timezone.utc) - timedelta(hours=2),
                "inspection_notes": "Caja abierta, producto parece no haber sido usado.",
            },
            {
                "status": ReturnOrderStatus.CLOSED,
                "reason": "No cumplió expectativas",
                "return_type": "refund",
                "notes": "Devolución procesada y cerrada.",
                "refund_amount": "200.00",
                "received_at": datetime.now(timezone.utc) - timedelta(days=2),
                "inspection_notes": "Producto en perfecto estado.",
            },
            {
                "status": ReturnOrderStatus.REJECTED,
                "reason": "Fuera del periodo de garantía",
                "return_type": "refund",
                "notes": "Solicitud rechazada, pasaron más de 30 días.",
                "refund_amount": "0",
                "received_at": None,
                "inspection_notes": "Se envió correo al cliente explicando el rechazo.",
            }
        ]

        for idx, rma_data in enumerate(returns_to_create):
            rma = ReturnOrder(
                id=uuid4(),
                tenant_id=tenant.id,
                warehouse_id=warehouse.id,
                so_id=so.id if so else None,
                customer_id=customer.id,
                rma_number=f"RMA-{uuid4().hex[:6].upper()}",
                status=rma_data["status"],
                reason=rma_data["reason"],
                return_type=rma_data["return_type"],
                received_at=rma_data["received_at"],
                received_by_id=user.id if rma_data["received_at"] else None,
                inspection_notes=rma_data["inspection_notes"],
                restocking_eligible=True if rma_data["status"] == ReturnOrderStatus.CLOSED else False,
                refund_amount=Decimal(rma_data["refund_amount"]),
                notes=rma_data["notes"],
                created_by_id=user.id
            )
            db.add(rma)
            
        await db.commit()
        print("Successfully generated return orders test data!")

if __name__ == "__main__":
    asyncio.run(main())
