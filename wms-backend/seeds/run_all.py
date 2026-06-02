"""
WMS Panama — Seed Runner
==========================
Carga datos iniciales mínimos necesarios para que el sistema funcione:
1. Permisos del sistema (permission catalog)
2. Roles del sistema (Admin, Supervisor, Operador, etc.)
3. Tenant demo + superadmin inicial

Ejecutar: python -m seeds.run_all
"""

from __future__ import annotations

import asyncio
import os
import sys

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.core import (
    Permission, Role, RolePermission, Tenant, TenantPlan,
    TenantStatus, User, UserStatus, UserRole,
)


# ── Catálogo de Permisos ───────────────────────────────────────────────────────

SYSTEM_PERMISSIONS = [
    # ── Inventory ──
    ("inventory:read",           "Ver Inventario",           "inventory"),
    ("inventory:adjustment:create", "Crear Ajuste",          "inventory"),
    ("inventory:adjustment:approve", "Aprobar Ajuste",       "inventory"),
    ("inventory:cycle_count:manage", "Gestionar Conteo",     "inventory"),
    ("inventory:transfer:create", "Crear Transferencia",     "inventory"),

    # ── Inbound ──
    ("inbound:po:read",          "Ver Órdenes de Compra",        "inbound"),
    ("inbound:po:create",        "Crear Orden de Compra",        "inbound"),
    ("inbound:po:update",        "Editar Orden de Compra",       "inbound"),
    ("inbound:po:confirm",       "Confirmar Orden de Compra",    "inbound"),
    ("inbound:po:cancel",        "Cancelar Orden de Compra",     "inbound"),
    ("inbound:po:delete",        "Eliminar Orden de Compra",     "inbound"),
    ("inbound:asn:create",       "Crear ASN",                    "inbound"),
    ("inbound:asn:read",         "Ver ASN",                      "inbound"),
    ("inbound:grn:create",       "Crear GRN",                    "inbound"),
    ("inbound:grn:read",         "Ver GRN",                      "inbound"),
    ("inbound:grn:confirm",      "Confirmar GRN",                "inbound"),
    ("inbound:qc:create",        "Crear Inspección de Calidad",  "inbound"),
    ("inbound:qc:resolve",       "Resolver Inspección de Calidad","inbound"),
    ("inbound:putaway:manage",   "Gestionar Putaway",            "inbound"),
    ("inbound:rtv:create",       "Crear Devolución a Proveedor", "inbound"),
    ("inbound:rtv:manage",       "Gestionar Devolución a Proveedor","inbound"),

    # ── Outbound ──
    ("outbound:order:read",      "Ver Órdenes de Salida",    "outbound"),
    ("outbound:order:create",    "Crear Orden de Salida",    "outbound"),
    ("outbound:picking:execute", "Ejecutar Picking",         "outbound"),
    ("outbound:packing:execute", "Ejecutar Packing",         "outbound"),
    ("outbound:shipping:approve", "Aprobar Despacho",        "outbound"),

    # ── Master Data ──
    ("master:product:read",      "Ver Productos",            "master"),
    ("master:product:create",    "Crear Productos",          "master"),
    ("master:product:update",    "Editar Productos",         "master"),
    ("master:supplier:manage",   "Gestionar Proveedores",    "master"),
    ("master:customer:manage",   "Gestionar Clientes",       "master"),
    ("master:location:manage",   "Gestionar Ubicaciones",    "master"),

    # ── Users & Roles ──
    ("admin:user:manage",        "Gestionar Usuarios",       "admin"),
    ("admin:role:manage",        "Gestionar Roles",          "admin"),
    ("admin:warehouse:manage",   "Gestionar Bodegas",        "admin"),
    ("admin:audit:read",         "Ver Auditoría",            "admin"),
    ("admin:reports:export",     "Exportar Reportes",        "admin"),

    # ── AI ──
    ("ai:insights:read",         "Ver Insights de IA",       "ai"),
    ("ai:forecast:read",         "Ver Pronósticos",          "ai"),
    ("ai:optimization:run",      "Ejecutar Optimizaciones",  "ai"),
]


# ── Roles del sistema ─────────────────────────────────────────────────────────

SYSTEM_ROLES = {
    "Administrador WMS": {
        "description": "Acceso total al sistema. Sin restricciones.",
        "permissions": [p[0] for p in SYSTEM_PERMISSIONS],  # Todos los permisos
    },
    "Supervisor de Bodega": {
        "description": "Gestiona operaciones de inbound, outbound e inventario.",
        "permissions": [
            "inventory:read", "inventory:adjustment:create", "inventory:adjustment:approve",
            "inventory:cycle_count:manage", "inventory:transfer:create",
            "inbound:po:read", "inbound:po:create", "inbound:po:update", "inbound:po:confirm",
            "inbound:po:cancel", "inbound:po:delete",
            "inbound:asn:create", "inbound:asn:read",
            "inbound:grn:create", "inbound:grn:read", "inbound:grn:confirm",
            "inbound:qc:create", "inbound:qc:resolve",
            "inbound:putaway:manage", "inbound:rtv:create", "inbound:rtv:manage",
            "outbound:order:read", "outbound:order:create", "outbound:picking:execute",
            "outbound:packing:execute", "outbound:shipping:approve",
            "master:product:read", "admin:audit:read", "admin:reports:export",
        ],
    },
    "Operador de Bodega": {
        "description": "Ejecuta operaciones de campo (picking, packing, putaway).",
        "permissions": [
            "inventory:read",
            "inbound:po:read", "inbound:grn:create", "inbound:grn:read", "inbound:putaway:manage",
            "outbound:order:read", "outbound:picking:execute", "outbound:packing:execute",
            "master:product:read",
        ],
    },
    "Auditor / Contador": {
        "description": "Solo lectura y acceso a reportes. Ideal para auditores.",
        "permissions": [
            "inventory:read", "inventory:cycle_count:manage",
            "inbound:po:read", "outbound:order:read",
            "master:product:read", "admin:audit:read", "admin:reports:export",
        ],
    },
    "Analista IA": {
        "description": "Acceso a módulos de IA, pronósticos y optimización.",
        "permissions": [
            "inventory:read", "master:product:read",
            "ai:insights:read", "ai:forecast:read", "ai:optimization:run",
            "admin:reports:export",
        ],
    },
}


# ── Seed Principal ─────────────────────────────────────────────────────────────

async def seed_permissions(db: AsyncSession) -> dict[str, Permission]:
    """Crea o actualiza el catálogo de permisos del sistema."""
    from sqlalchemy import select

    permission_map: dict[str, Permission] = {}

    for code, name, module in SYSTEM_PERMISSIONS:
        result = await db.execute(select(Permission).where(Permission.code == code))
        perm = result.scalar_one_or_none()

        if not perm:
            perm = Permission(code=code, name=name, module=module)
            db.add(perm)
            print(f"  ✅ Permiso creado: {code}")
        else:
            print(f"  ↩️  Permiso existente: {code}")

        permission_map[code] = perm

    await db.flush()
    return permission_map


async def seed_roles(
    db: AsyncSession,
    tenant_id,
    permission_map: dict[str, Permission],
) -> dict[str, Role]:
    """Crea o actualiza los roles del sistema para el tenant."""
    from sqlalchemy import select

    role_map: dict[str, Role] = {}

    for role_name, config in SYSTEM_ROLES.items():
        result = await db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name)
        )
        role = result.scalar_one_or_none()

        if not role:
            role = Role(
                tenant_id=tenant_id,
                name=role_name,
                description=config["description"],
                is_system=True,
            )
            db.add(role)
            await db.flush()
            print(f"  ✅ Rol creado: {role_name}")

            # Asignar permisos al rol
            for perm_code in config["permissions"]:
                if perm_code in permission_map:
                    rp = RolePermission(role_id=role.id, permission_id=permission_map[perm_code].id)
                    db.add(rp)
        else:
            print(f"  ↩️  Rol existente: {role_name}")

        role_map[role_name] = role

    await db.flush()
    return role_map


async def seed_demo_tenant(db: AsyncSession) -> Tenant:
    """Crea el tenant demo si no existe."""
    from sqlalchemy import select

    result = await db.execute(select(Tenant).where(Tenant.slug == "wms-demo"))
    tenant = result.scalar_one_or_none()

    if not tenant:
        tenant = Tenant(
            name="WMS Demo S.A.",
            slug="wms-demo",
            legal_name="WMS Demo Sociedad Anónima",
            ruc="155-123456-2-2024",
            plan=TenantPlan.ENTERPRISE,
            status=TenantStatus.ACTIVE,
            timezone="America/Panama",
            currency="USD",
            locale="es-PA",
            contact_email="admin@wmspanama.com",
            country="PA",
            max_warehouses=999,
            max_users=9999,
            max_skus=9_999_999,
        )
        db.add(tenant)
        await db.flush()
        print(f"  ✅ Tenant demo creado: {tenant.slug}")
    else:
        print(f"  ↩️  Tenant demo existente: {tenant.slug}")

    return tenant


async def seed_superadmin(db: AsyncSession, tenant: Tenant, admin_role: Role) -> User:
    """Crea el usuario superadmin si no existe."""
    from sqlalchemy import select

    superadmin_email = os.environ.get("SUPERADMIN_EMAIL", "admin@wmspanama.com")
    superadmin_password = os.environ.get("SUPERADMIN_PASSWORD", "Admin123!")

    result = await db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == superadmin_email)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            tenant_id=tenant.id,
            email=superadmin_email,
            first_name="Admin",
            last_name="WMS",
            hashed_password=hash_password(superadmin_password),
            status=UserStatus.ACTIVE,
            is_superadmin=True,
            language="es",
        )
        db.add(user)
        await db.flush()

        # Asignar rol Administrador WMS
        user_role = UserRole(user_id=user.id, role_id=admin_role.id)
        db.add(user_role)

        print(f"  ✅ Superadmin creado: {superadmin_email}")
        print(f"  ⚠️  Password inicial: {superadmin_password} — CAMBIAR EN PRODUCCIÓN")
    else:
        print(f"  ↩️  Superadmin existente: {superadmin_email}")

    return user


async def run_seeds() -> None:
    """Ejecuta todos los seeds en orden."""
    print("\n🌱 WMS Panama — Iniciando seeds...\n")

    async with AsyncSessionLocal() as db:
        print("📋 Sembrando permisos del sistema...")
        permission_map = await seed_permissions(db)

        print("\n🏢 Sembrando tenant demo...")
        tenant = await seed_demo_tenant(db)

        print("\n👥 Sembrando roles del sistema...")
        role_map = await seed_roles(db, tenant.id, permission_map)

        print("\n👤 Sembrando superadmin...")
        await seed_superadmin(db, tenant, role_map["Administrador WMS"])

        await db.commit()

    print("\n✅ Seeds completados exitosamente.")
    print(f"   API Docs:  http://localhost:{settings.PORT}/api/docs")
    print(f"   MailHog:   http://localhost:8025")
    print()


if __name__ == "__main__":
    asyncio.run(run_seeds())
