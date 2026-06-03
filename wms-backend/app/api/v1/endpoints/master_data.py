"""
WMS Panama — Master Data Endpoints (solo lectura)
==================================================
Listados de datos maestros usados por los formularios del frontend
(selectores de producto, proveedor y ubicacion en Inbound/Outbound).

Son endpoints de SOLO LECTURA: el alta/edicion de maestros se gestiona
por procesos dedicados. Aqui solo exponemos catalogos paginados y
buscables, siempre acotados al tenant del usuario autenticado.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_

from app.core.dependencies import (
    DBDep, CurrentUserDep, PaginationDep, require_permission,
)
from app.models.master_data import (
    Product, ProductStatus,
    Supplier, SupplierStatus,
    Location, LocationType, LocationStatus,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────
# Schemas de respuesta (ligeros, pensados para selectores)
# ─────────────────────────────────────────────────────────────
class ProductLite(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    uom: str
    status: ProductStatus
    gtin_13: Optional[str] = None
    model_config = {"from_attributes": True}


class SupplierLite(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: SupplierStatus
    supplier_type: str
    lead_time_days: Optional[int] = None
    model_config = {"from_attributes": True}


class LocationLite(BaseModel):
    id: uuid.UUID
    code: str
    warehouse_id: uuid.UUID
    location_type: LocationType
    status: LocationStatus
    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: list[ProductLite]
    total: int
    page: int
    page_size: int


class SupplierListResponse(BaseModel):
    items: list[SupplierLite]
    total: int
    page: int
    page_size: int


class LocationListResponse(BaseModel):
    items: list[LocationLite]
    total: int
    page: int
    page_size: int


# ─────────────────────────────────────────────────────────────
# Productos
# ─────────────────────────────────────────────────────────────
@router.get("/products", response_model=ProductListResponse)
async def list_products(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(None, description="Busca por SKU o nombre"),
    status_filter: Optional[ProductStatus] = Query(None, alias="status"),
) -> ProductListResponse:
    """Catalogo de productos del tenant (para selectores de SKU)."""
    stmt = select(Product).where(Product.tenant_id == current_user.tenant_id)

    if search:
        stmt = stmt.where(
            Product.sku.ilike(f"%{search}%") | Product.name.ilike(f"%{search}%")
        )
    if status_filter:
        stmt = stmt.where(Product.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Product.sku).offset(pagination.offset).limit(pagination.limit)
    items = (await db.execute(stmt)).scalars().all()

    return ProductListResponse(
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


# ─────────────────────────────────────────────────────────────
# Proveedores
# ─────────────────────────────────────────────────────────────
@router.get("/suppliers", response_model=SupplierListResponse)
async def list_suppliers(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(None, description="Busca por codigo o nombre"),
    status_filter: Optional[SupplierStatus] = Query(None, alias="status"),
) -> SupplierListResponse:
    """Catalogo de proveedores del tenant (para selectores de proveedor)."""
    stmt = select(Supplier).where(Supplier.tenant_id == current_user.tenant_id)

    if search:
        stmt = stmt.where(
            Supplier.code.ilike(f"%{search}%") | Supplier.name.ilike(f"%{search}%")
        )
    if status_filter:
        stmt = stmt.where(Supplier.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Supplier.name).offset(pagination.offset).limit(pagination.limit)
    items = (await db.execute(stmt)).scalars().all()

    return SupplierListResponse(
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


# ─────────────────────────────────────────────────────────────
# Ubicaciones
# ─────────────────────────────────────────────────────────────
@router.get("/locations", response_model=LocationListResponse)
async def list_locations(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None, description="Filtra por bodega"),
    search: Optional[str] = Query(None, description="Busca por codigo de ubicacion"),
    type_filter: Optional[LocationType] = Query(None, alias="type"),
    status_filter: Optional[LocationStatus] = Query(None, alias="status"),
) -> LocationListResponse:
    """Catalogo de ubicaciones del tenant (para selectores de ubicacion/staging)."""
    stmt = select(Location).where(Location.tenant_id == current_user.tenant_id)

    if warehouse_id:
        stmt = stmt.where(Location.warehouse_id == warehouse_id)
    if search:
        stmt = stmt.where(Location.code.ilike(f"%{search}%"))
    if type_filter:
        stmt = stmt.where(Location.location_type == type_filter)
    if status_filter:
        stmt = stmt.where(Location.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Location.code).offset(pagination.offset).limit(pagination.limit)
    items = (await db.execute(stmt)).scalars().all()

    return LocationListResponse(
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


# ══════════════════════════════════════════════════════════════════════════════
# ALTA / EDICIÓN DE MAESTROS (CRUD) + CARGA MASIVA  (FR-010/012/013/014/015)
# ══════════════════════════════════════════════════════════════════════════════

# ── Schemas de escritura ──────────────────────────────────────────────────────
class ProductCreate(BaseModel):
    sku: str = Field(..., max_length=100)
    name: str = Field(..., max_length=300)
    description: Optional[str] = None
    name_en: Optional[str] = Field(None, max_length=300)
    gtin_13: Optional[str] = Field(None, max_length=14)
    gtin_14: Optional[str] = Field(None, max_length=14)
    uom: str = Field("UN", max_length=20)
    status: ProductStatus = ProductStatus.ACTIVE
    category_id: Optional[uuid.UUID] = None
    cost_price: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    currency: str = Field("USD", max_length=3)
    weight_kg: Optional[Decimal] = None
    min_temp_celsius: Optional[Decimal] = None
    max_temp_celsius: Optional[Decimal] = None
    reorder_point: Optional[int] = None
    safety_stock: Optional[int] = None
    lead_time_days: Optional[int] = None
    sanitary_registry: Optional[str] = Field(None, max_length=100)
    model_config = {"extra": "ignore"}


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    name_en: Optional[str] = Field(None, max_length=300)
    gtin_13: Optional[str] = Field(None, max_length=14)
    gtin_14: Optional[str] = Field(None, max_length=14)
    uom: Optional[str] = Field(None, max_length=20)
    status: Optional[ProductStatus] = None
    cost_price: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    reorder_point: Optional[int] = None
    safety_stock: Optional[int] = None
    lead_time_days: Optional[int] = None
    model_config = {"extra": "ignore"}


class SupplierCreate(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=300)
    legal_name: Optional[str] = Field(None, max_length=300)
    ruc: Optional[str] = Field(None, max_length=50)
    status: SupplierStatus = SupplierStatus.ACTIVE
    supplier_type: str = Field("standard", max_length=50)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = Field("PA", max_length=2)
    lead_time_days: Optional[int] = None
    payment_terms_days: Optional[int] = None
    is_importer: bool = False
    model_config = {"extra": "ignore"}


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=300)
    legal_name: Optional[str] = None
    ruc: Optional[str] = None
    status: Optional[SupplierStatus] = None
    supplier_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    lead_time_days: Optional[int] = None
    payment_terms_days: Optional[int] = None
    is_blocked: Optional[bool] = None
    blocked_reason: Optional[str] = None
    model_config = {"extra": "ignore"}


class LocationCreate(BaseModel):
    warehouse_id: uuid.UUID
    code: str = Field(..., max_length=50)
    zone_id: Optional[uuid.UUID] = None
    aisle: Optional[str] = Field(None, max_length=20)
    rack: Optional[str] = Field(None, max_length=20)
    level: Optional[str] = Field(None, max_length=20)
    position: Optional[str] = Field(None, max_length=20)
    location_type: LocationType = LocationType.STANDARD
    status: LocationStatus = LocationStatus.ACTIVE
    max_weight_kg: Optional[Decimal] = None
    max_volume_m3: Optional[Decimal] = None
    max_units: Optional[int] = None
    pick_sequence: Optional[int] = None
    model_config = {"extra": "ignore"}


class LocationUpdate(BaseModel):
    aisle: Optional[str] = None
    rack: Optional[str] = None
    level: Optional[str] = None
    position: Optional[str] = None
    location_type: Optional[LocationType] = None
    status: Optional[LocationStatus] = None
    max_weight_kg: Optional[Decimal] = None
    max_volume_m3: Optional[Decimal] = None
    max_units: Optional[int] = None
    pick_sequence: Optional[int] = None
    model_config = {"extra": "ignore"}


class BulkImportResult(BaseModel):
    total: int
    valid: int
    invalid: int
    created: int
    dry_run: bool
    errors: list[dict] = []


class ProductBulkImport(BaseModel):
    dry_run: bool = True
    rows: list[ProductCreate] = Field(..., min_length=1, max_length=5000)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _exists(db, model, tenant_id, field, value) -> bool:
    col = getattr(model, field)
    q = select(func.count()).select_from(model).where(
        and_(model.tenant_id == tenant_id, col == value)
    )
    return ((await db.execute(q)).scalar_one() or 0) > 0


# ── Productos: alta / edición / carga masiva ─────────────────────────────────
@router.post(
    "/products", response_model=ProductLite, status_code=status.HTTP_201_CREATED,
    summary="Crear producto",
    dependencies=[Depends(require_permission("master:product:create"))],
)
async def create_product(payload: ProductCreate, db: DBDep, current_user: CurrentUserDep) -> ProductLite:
    if await _exists(db, Product, current_user.tenant_id, "sku", payload.sku):
        raise HTTPException(status_code=409, detail=f"Ya existe un producto con SKU '{payload.sku}'.")
    prod = Product(id=uuid.uuid4(), tenant_id=current_user.tenant_id, created_by_id=current_user.id,
                   **payload.model_dump(exclude_none=True))
    db.add(prod)
    await db.commit()
    await db.refresh(prod)
    return prod


@router.put(
    "/products/{product_id}", response_model=ProductLite, summary="Editar producto",
    dependencies=[Depends(require_permission("master:product:update"))],
)
async def update_product(product_id: uuid.UUID, payload: ProductUpdate, db: DBDep, current_user: CurrentUserDep) -> ProductLite:
    prod = (await db.execute(select(Product).where(
        and_(Product.id == product_id, Product.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(prod, k, v)
    prod.updated_by_id = current_user.id
    await db.commit()
    await db.refresh(prod)
    return prod


@router.post(
    "/products/bulk-import", response_model=BulkImportResult,
    summary="Carga masiva de productos (Excel/CSV → filas; con dry-run)",
    dependencies=[Depends(require_permission("master:product:create"))],
)
async def bulk_import_products(payload: ProductBulkImport, db: DBDep, current_user: CurrentUserDep) -> BulkImportResult:
    """Valida un lote de productos y, si dry_run=False, inserta los válidos.

    Las filas ya vienen validadas estructuralmente por Pydantic (ProductCreate).
    Aquí se detectan duplicados por SKU (en BD y dentro del mismo lote).
    Para Excel/CSV, el cliente convierte las filas a JSON; el esquema es idéntico.
    """
    errors: list[dict] = []
    seen: set[str] = set()
    valid_rows: list[ProductCreate] = []
    for i, row in enumerate(payload.rows, start=1):
        if row.sku in seen:
            errors.append({"row": i, "sku": row.sku, "detail": "SKU duplicado dentro del archivo."})
            continue
        seen.add(row.sku)
        if await _exists(db, Product, current_user.tenant_id, "sku", row.sku):
            errors.append({"row": i, "sku": row.sku, "detail": "SKU ya existe en la base de datos."})
            continue
        valid_rows.append(row)

    created = 0
    if not payload.dry_run and valid_rows:
        for row in valid_rows:
            db.add(Product(id=uuid.uuid4(), tenant_id=current_user.tenant_id,
                           created_by_id=current_user.id, **row.model_dump(exclude_none=True)))
        await db.commit()
        created = len(valid_rows)

    return BulkImportResult(
        total=len(payload.rows), valid=len(valid_rows), invalid=len(errors),
        created=created, dry_run=payload.dry_run, errors=errors[:200],
    )


# ── Proveedores: alta / edición ───────────────────────────────────────────────
@router.post(
    "/suppliers", response_model=SupplierLite, status_code=status.HTTP_201_CREATED,
    summary="Crear proveedor",
    dependencies=[Depends(require_permission("master:supplier:manage"))],
)
async def create_supplier(payload: SupplierCreate, db: DBDep, current_user: CurrentUserDep) -> SupplierLite:
    if await _exists(db, Supplier, current_user.tenant_id, "code", payload.code):
        raise HTTPException(status_code=409, detail=f"Ya existe un proveedor con código '{payload.code}'.")
    sup = Supplier(id=uuid.uuid4(), tenant_id=current_user.tenant_id, created_by_id=current_user.id,
                   **payload.model_dump(exclude_none=True))
    db.add(sup)
    await db.commit()
    await db.refresh(sup)
    return sup


@router.put(
    "/suppliers/{supplier_id}", response_model=SupplierLite, summary="Editar proveedor",
    dependencies=[Depends(require_permission("master:supplier:manage"))],
)
async def update_supplier(supplier_id: uuid.UUID, payload: SupplierUpdate, db: DBDep, current_user: CurrentUserDep) -> SupplierLite:
    sup = (await db.execute(select(Supplier).where(
        and_(Supplier.id == supplier_id, Supplier.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
    if not sup:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sup, k, v)
    sup.updated_by_id = current_user.id
    await db.commit()
    await db.refresh(sup)
    return sup


# ── Ubicaciones: alta / edición ───────────────────────────────────────────────
@router.post(
    "/locations", response_model=LocationLite, status_code=status.HTTP_201_CREATED,
    summary="Crear ubicación",
    dependencies=[Depends(require_permission("master:location:manage"))],
)
async def create_location(payload: LocationCreate, db: DBDep, current_user: CurrentUserDep) -> LocationLite:
    dup = (await db.execute(select(func.count()).select_from(Location).where(and_(
        Location.tenant_id == current_user.tenant_id,
        Location.warehouse_id == payload.warehouse_id,
        Location.code == payload.code,
    )))).scalar_one()
    if dup:
        raise HTTPException(status_code=409, detail=f"Ya existe la ubicación '{payload.code}' en esa bodega.")
    loc = Location(id=uuid.uuid4(), tenant_id=current_user.tenant_id, created_by_id=current_user.id,
                   **payload.model_dump(exclude_none=True))
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return loc


@router.put(
    "/locations/{location_id}", response_model=LocationLite, summary="Editar ubicación",
    dependencies=[Depends(require_permission("master:location:manage"))],
)
async def update_location(location_id: uuid.UUID, payload: LocationUpdate, db: DBDep, current_user: CurrentUserDep) -> LocationLite:
    loc = (await db.execute(select(Location).where(
        and_(Location.id == location_id, Location.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
    if not loc:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(loc, k, v)
    loc.updated_by_id = current_user.id
    await db.commit()
    await db.refresh(loc)
    return loc


# ══════════════════════════════════════════════════════════════════════════════
# CARGA MASIVA (proveedores/ubicaciones), DEDUPLICACIÓN y SLA (FR-014/015/013)
# ══════════════════════════════════════════════════════════════════════════════

class SupplierBulkImport(BaseModel):
    dry_run: bool = True
    rows: list[SupplierCreate] = Field(..., min_length=1, max_length=5000)


class LocationBulkImport(BaseModel):
    dry_run: bool = True
    rows: list[LocationCreate] = Field(..., min_length=1, max_length=5000)


@router.post(
    "/suppliers/bulk-import", response_model=BulkImportResult,
    summary="Carga masiva de proveedores (con dry-run)",
    dependencies=[Depends(require_permission("master:supplier:manage"))],
)
async def bulk_import_suppliers(payload: SupplierBulkImport, db: DBDep, current_user: CurrentUserDep) -> BulkImportResult:
    errors: list[dict] = []
    seen: set[str] = set()
    valid: list[SupplierCreate] = []
    for i, row in enumerate(payload.rows, start=1):
        if row.code in seen:
            errors.append({"row": i, "code": row.code, "detail": "Código duplicado en el archivo."}); continue
        seen.add(row.code)
        if await _exists(db, Supplier, current_user.tenant_id, "code", row.code):
            errors.append({"row": i, "code": row.code, "detail": "Código ya existe en la base de datos."}); continue
        valid.append(row)
    created = 0
    if not payload.dry_run and valid:
        for row in valid:
            db.add(Supplier(id=uuid.uuid4(), tenant_id=current_user.tenant_id,
                            created_by_id=current_user.id, **row.model_dump(exclude_none=True)))
        await db.commit(); created = len(valid)
    return BulkImportResult(total=len(payload.rows), valid=len(valid), invalid=len(errors),
                            created=created, dry_run=payload.dry_run, errors=errors[:200])


@router.post(
    "/locations/bulk-import", response_model=BulkImportResult,
    summary="Carga masiva de ubicaciones (con dry-run)",
    dependencies=[Depends(require_permission("master:location:manage"))],
)
async def bulk_import_locations(payload: LocationBulkImport, db: DBDep, current_user: CurrentUserDep) -> BulkImportResult:
    errors: list[dict] = []
    seen: set[tuple] = set()
    valid: list[LocationCreate] = []
    for i, row in enumerate(payload.rows, start=1):
        key = (str(row.warehouse_id), row.code)
        if key in seen:
            errors.append({"row": i, "code": row.code, "detail": "Ubicación duplicada en el archivo."}); continue
        seen.add(key)
        dup = (await db.execute(select(func.count()).select_from(Location).where(and_(
            Location.tenant_id == current_user.tenant_id,
            Location.warehouse_id == row.warehouse_id, Location.code == row.code)))).scalar_one()
        if dup:
            errors.append({"row": i, "code": row.code, "detail": "Ya existe en esa bodega."}); continue
        valid.append(row)
    created = 0
    if not payload.dry_run and valid:
        for row in valid:
            db.add(Location(id=uuid.uuid4(), tenant_id=current_user.tenant_id,
                            created_by_id=current_user.id, **row.model_dump(exclude_none=True)))
        await db.commit(); created = len(valid)
    return BulkImportResult(total=len(payload.rows), valid=len(valid), invalid=len(errors),
                            created=created, dry_run=payload.dry_run, errors=errors[:200])


@router.get(
    "/products/duplicates", summary="Detectar posibles productos duplicados (FR-015)",
    dependencies=[Depends(require_permission("master:product:read"))],
)
async def product_duplicates(db: DBDep, current_user: CurrentUserDep,
                             threshold: float = Query(0.85, ge=0.5, le=1.0)) -> dict:
    """Detecta duplicados por GTIN exacto y por similitud de nombre (difflib)."""
    import difflib
    rows = (await db.execute(
        select(Product.id, Product.sku, Product.name, Product.gtin_13)
        .where(Product.tenant_id == current_user.tenant_id).limit(500)
    )).all()
    groups: list[dict] = []
    by_gtin: dict[str, list] = {}
    for r in rows:
        if r.gtin_13:
            by_gtin.setdefault(r.gtin_13, []).append(r)
    for gtin, members in by_gtin.items():
        if len(members) > 1:
            groups.append({"reason": "GTIN duplicado", "key": gtin,
                           "items": [{"id": str(m.id), "sku": m.sku, "name": m.name} for m in members]})
    names = [(r, (r.name or "").lower()) for r in rows]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ratio = difflib.SequenceMatcher(None, names[i][1], names[j][1]).ratio()
            if ratio >= threshold:
                a, b = names[i][0], names[j][0]
                groups.append({"reason": f"Nombre similar ({ratio:.2f})",
                               "items": [{"id": str(a.id), "sku": a.sku, "name": a.name},
                                         {"id": str(b.id), "sku": b.sku, "name": b.name}]})
    return {"groups": groups, "total": len(groups)}


@router.get(
    "/suppliers/duplicates", summary="Detectar posibles proveedores duplicados (FR-015)",
    dependencies=[Depends(require_permission("master:supplier:manage"))],
)
async def supplier_duplicates(db: DBDep, current_user: CurrentUserDep,
                              threshold: float = Query(0.85, ge=0.5, le=1.0)) -> dict:
    import difflib
    rows = (await db.execute(
        select(Supplier.id, Supplier.code, Supplier.name, Supplier.ruc)
        .where(Supplier.tenant_id == current_user.tenant_id).limit(500)
    )).all()
    groups: list[dict] = []
    by_ruc: dict[str, list] = {}
    for r in rows:
        if r.ruc:
            by_ruc.setdefault(r.ruc, []).append(r)
    for ruc, members in by_ruc.items():
        if len(members) > 1:
            groups.append({"reason": "RUC duplicado", "key": ruc,
                           "items": [{"id": str(m.id), "code": m.code, "name": m.name} for m in members]})
    names = [(r, (r.name or "").lower()) for r in rows]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ratio = difflib.SequenceMatcher(None, names[i][1], names[j][1]).ratio()
            if ratio >= threshold:
                a, b = names[i][0], names[j][0]
                groups.append({"reason": f"Nombre similar ({ratio:.2f})",
                               "items": [{"id": str(a.id), "code": a.code, "name": a.name},
                                         {"id": str(b.id), "code": b.code, "name": b.name}]})
    return {"groups": groups, "total": len(groups)}


@router.get(
    "/suppliers/{supplier_id}/sla", summary="SLA de cumplimiento del proveedor (FR-013)",
    dependencies=[Depends(require_permission("master:supplier:manage"))],
)
async def supplier_sla(supplier_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep) -> dict:
    """Calcula el % de entregas a tiempo del proveedor (GRN.received_at <= OC.expected_delivery_date)
    y alerta si el incumplimiento supera el 15% en las recepciones registradas."""
    from sqlalchemy import case
    from app.models.inbound import PurchaseOrder, GoodsReceipt

    sup = (await db.execute(select(Supplier).where(and_(
        Supplier.id == supplier_id, Supplier.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
    if not sup:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")

    on_time_expr = func.sum(case((GoodsReceipt.received_at <= PurchaseOrder.expected_delivery_date, 1), else_=0))
    row = (await db.execute(
        select(func.count(GoodsReceipt.id), on_time_expr)
        .select_from(GoodsReceipt)
        .join(PurchaseOrder, GoodsReceipt.purchase_order_id == PurchaseOrder.id)
        .where(and_(
            GoodsReceipt.tenant_id == current_user.tenant_id,
            GoodsReceipt.supplier_id == supplier_id,
            PurchaseOrder.expected_delivery_date.isnot(None),
        ))
    )).one()
    total = int(row[0] or 0)
    on_time = int(row[1] or 0)
    on_time_pct = round(on_time / total * 100, 2) if total else None
    return {
        "supplier_id": str(supplier_id), "code": sup.code, "name": sup.name,
        "receipts_evaluated": total, "on_time": on_time,
        "on_time_pct": on_time_pct,
        "sla_target_pct": float(sup.sla_on_time_pct) if sup.sla_on_time_pct is not None else 85.0,
        "breach": (on_time_pct is not None and on_time_pct < 85.0),
        "is_blocked": bool(getattr(sup, "is_blocked", False)),
    }
