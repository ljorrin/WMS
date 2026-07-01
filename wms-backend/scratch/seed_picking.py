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
from app.models.master_data import Product, Location
from app.models.outbound import SalesOrder, SalesOrderLine, PickingWave, PickingTask, SOStatus, WaveStatus, PickingStatus

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
            print("No warehouse found. Creating one...")
            from app.models.core import Company
            company = (await db.execute(select(Company).limit(1))).scalar_one_or_none()
            if not company:
                company = Company(id=uuid4(), tenant_id=tenant.id, name="Test Company")
                db.add(company)
            warehouse = Warehouse(id=uuid4(), tenant_id=tenant.id, company_id=company.id, code="WH-TEST", name="Test WH")
            db.add(warehouse)
            await db.flush()

        # Get some products
        products = (await db.execute(select(Product).where(Product.tenant_id == tenant.id).limit(5))).scalars().all()
        if not products:
            print("No products found, as user stated they had them... creating dummies.")
            products = [
                Product(id=uuid4(), tenant_id=tenant.id, code=f"PROD-{i}", name=f"Product {i}", uom="UN")
                for i in range(3)
            ]
            db.add_all(products)
            await db.flush()

        # Get some locations
        locations = (await db.execute(select(Location).where(Location.tenant_id == tenant.id).limit(2))).scalars().all()
        if not locations:
            locations = [
                Location(id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code=f"LOC-A-{i}", type="bin")
                for i in range(2)
            ]
            db.add_all(locations)
            await db.flush()

        # Get a customer
        from app.models.master_data import Customer
        customer = (await db.execute(select(Customer).where(Customer.tenant_id == tenant.id).limit(1))).scalar_one_or_none()
        if not customer:
            customer = Customer(id=uuid4(), tenant_id=tenant.id, name="Test Customer")
            db.add(customer)
            await db.flush()

        # Create Sales Order
        so = SalesOrder(
            id=uuid4(),
            tenant_id=tenant.id,
            so_number=f"SO-{uuid4().hex[:6].upper()}",
            warehouse_id=warehouse.id,
            customer_id=customer.id,
            status=SOStatus.PICKING,
            order_date=datetime.now(timezone.utc),
            priority=1,
            created_by_id=user.id
        )
        db.add(so)
        
        # Create SO Lines
        so_lines = []
        for idx, prod in enumerate(products):
            line = SalesOrderLine(
                id=uuid4(),
                tenant_id=tenant.id,
                so_id=so.id,
                product_id=prod.id,
                line_number=idx + 1,
                uom_id=uuid4(),
                quantity_ordered=Decimal("10.0"),
                quantity_allocated=Decimal("10.0")
            )
            db.add(line)
            so_lines.append(line)
        await db.flush()

        # Create Wave
        wave = PickingWave(
            id=uuid4(),
            tenant_id=tenant.id,
            wave_number=f"WAVE-{uuid4().hex[:6].upper()}",
            warehouse_id=warehouse.id,
            status=WaveStatus.RELEASED,
            created_by_id=user.id,
            priority=1
        )
        db.add(wave)
        await db.flush()

        # Create Picking Tasks
        for i, prod in enumerate(products):
            loc = locations[i % len(locations)]
            pt = PickingTask(
                id=uuid4(),
                tenant_id=tenant.id,
                wave_id=wave.id,
                so_id=so.id,
                so_line_id=so_lines[i].id,
                product_id=prod.id,
                uom_id=uuid4(),
                from_location_id=loc.id,
                status=PickingStatus.PENDING if i % 2 == 0 else PickingStatus.IN_PROGRESS,
                quantity_requested=Decimal(10 + i),
                quantity_picked=Decimal(0),
                quantity_short=Decimal(0),
                priority=1,
                assigned_to_id=user.id if i % 2 != 0 else None
            )
            db.add(pt)

        # One completed
        pt_done = PickingTask(
            id=uuid4(),
            tenant_id=tenant.id,
            wave_id=wave.id,
            so_id=so.id,
            so_line_id=so_lines[0].id,
            product_id=products[0].id,
            uom_id=uuid4(),
            from_location_id=locations[0].id,
            status=PickingStatus.COMPLETED,
            quantity_requested=Decimal("5"),
            quantity_picked=Decimal("5"),
            quantity_short=Decimal("0"),
            priority=2,
            assigned_to_id=user.id,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            completed_at=datetime.now(timezone.utc)
        )
        db.add(pt_done)

        await db.commit()
        print("Successfully generated picking test data!")

if __name__ == "__main__":
    asyncio.run(main())
