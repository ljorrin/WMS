import asyncio
from app.db.session import AsyncSessionLocal
from app.services.inventory_service import InventoryService
from app.services.inbound_service import InboundService
from app.models.core import Tenant

async def test_dashboards():
    async with AsyncSessionLocal() as db:
        # Get the first tenant
        from sqlalchemy import select
        tenant = (await db.execute(select(Tenant))).scalars().first()
        if not tenant:
            print("No tenant found!")
            return
        
        print(f"Testing with tenant_id: {tenant.id}")
        
        # Test Inventory Dashboard
        inv_service = InventoryService(db, tenant.id)
        try:
            inv_metrics = await inv_service.get_dashboard_metrics()
            print("Inventory metrics SUCCESS:", inv_metrics)
        except Exception as e:
            print("Inventory metrics FAILED:", e)

        # Test Inbound Dashboard
        inb_service = InboundService(db, tenant.id)
        try:
            inb_metrics = await inb_service.get_dashboard_metrics()
            print("Inbound metrics SUCCESS:", inb_metrics)
        except Exception as e:
            print("Inbound metrics FAILED:", e)

if __name__ == "__main__":
    asyncio.run(test_dashboards())
