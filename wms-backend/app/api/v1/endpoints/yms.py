"""
WMS Panamá — YMS (Yard Management) Endpoints — FR-060
======================================================
Muelles (docks), citas de transporte, cola de espera y estadías.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_

from app.core.dependencies import DBDep, CurrentUserDep, PaginationDep
from app.models.yms import Dock, YardAppointment

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────
class DockCreate(BaseModel):
    warehouse_id: uuid.UUID
    code: str = Field(..., max_length=50)
    name: Optional[str] = Field(None, max_length=200)
    dock_type: str = Field("both", pattern="^(receiving|shipping|both)$")


class DockResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    code: str
    name: Optional[str] = None
    dock_type: str
    status: str
    is_active: bool
    model_config = {"from_attributes": True}


class AppointmentCreate(BaseModel):
    warehouse_id: uuid.UUID
    appointment_type: str = Field("inbound", pattern="^(inbound|outbound)$")
    carrier_name: Optional[str] = Field(None, max_length=200)
    vehicle_plate: Optional[str] = Field(None, max_length=20)
    driver_name: Optional[str] = Field(None, max_length=200)
    reference: Optional[str] = Field(None, max_length=100)
    scheduled_at: Optional[datetime] = None
    dock_id: Optional[uuid.UUID] = None


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    dock_id: Optional[uuid.UUID] = None
    appointment_number: str
    appointment_type: str
    carrier_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    driver_name: Optional[str] = None
    reference: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    at_dock_at: Optional[datetime] = None
    departed_at: Optional[datetime] = None
    status: str
    queue_position: Optional[int] = None
    model_config = {"from_attributes": True}


# ── Docks ─────────────────────────────────────────────────────────────────────
@router.post("/docks", response_model=DockResponse, status_code=status.HTTP_201_CREATED, summary="Crear muelle")
async def create_dock(payload: DockCreate, db: DBDep, current_user: CurrentUserDep) -> DockResponse:
    dup = (await db.execute(select(func.count()).select_from(Dock).where(and_(
        Dock.tenant_id == current_user.tenant_id, Dock.warehouse_id == payload.warehouse_id,
        Dock.code == payload.code)))).scalar_one()
    if dup:
        raise HTTPException(status_code=409, detail=f"Ya existe el muelle '{payload.code}' en esa bodega.")
    dock = Dock(id=uuid.uuid4(), tenant_id=current_user.tenant_id, created_by_id=current_user.id,
                **payload.model_dump())
    db.add(dock); await db.commit(); await db.refresh(dock)
    return dock


@router.get("/docks", summary="Listar muelles")
async def list_docks(db: DBDep, current_user: CurrentUserDep, pagination: PaginationDep,
                     warehouse_id: Optional[uuid.UUID] = Query(None)) -> dict:
    filters = [Dock.tenant_id == current_user.tenant_id]
    if warehouse_id:
        filters.append(Dock.warehouse_id == warehouse_id)
    total = (await db.execute(select(func.count(Dock.id)).where(and_(*filters)))).scalar_one()
    rows = (await db.execute(select(Dock).where(and_(*filters)).order_by(Dock.code)
                             .offset(pagination.offset).limit(pagination.limit))).scalars().all()
    return {"items": [DockResponse.model_validate(d) for d in rows], "total": total,
            "page": pagination.page, "page_size": pagination.page_size}


# ── Citas (appointments) ──────────────────────────────────────────────────────
async def _next_appt_number(db, tenant_id) -> str:
    n = (await db.execute(select(func.count(YardAppointment.id)).where(
        YardAppointment.tenant_id == tenant_id))).scalar_one()
    return f"APT-{n + 1:06d}"


@router.post("/appointments", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED,
             summary="Programar cita de transporte")
async def create_appointment(payload: AppointmentCreate, db: DBDep, current_user: CurrentUserDep) -> AppointmentResponse:
    # Posición en cola = nº de citas activas de la bodega
    queue = (await db.execute(select(func.count(YardAppointment.id)).where(and_(
        YardAppointment.tenant_id == current_user.tenant_id,
        YardAppointment.warehouse_id == payload.warehouse_id,
        YardAppointment.status.in_(["scheduled", "arrived"]))))).scalar_one()
    appt = YardAppointment(
        id=uuid.uuid4(), tenant_id=current_user.tenant_id, created_by_id=current_user.id,
        appointment_number=await _next_appt_number(db, current_user.tenant_id),
        status="scheduled", queue_position=queue + 1,
        **payload.model_dump(exclude_none=True),
    )
    db.add(appt); await db.commit(); await db.refresh(appt)
    return appt


@router.get("/appointments", summary="Listar citas")
async def list_appointments(db: DBDep, current_user: CurrentUserDep, pagination: PaginationDep,
                            warehouse_id: Optional[uuid.UUID] = Query(None),
                            status_filter: Optional[str] = Query(None, alias="status")) -> dict:
    filters = [YardAppointment.tenant_id == current_user.tenant_id]
    if warehouse_id:
        filters.append(YardAppointment.warehouse_id == warehouse_id)
    if status_filter:
        filters.append(YardAppointment.status == status_filter)
    total = (await db.execute(select(func.count(YardAppointment.id)).where(and_(*filters)))).scalar_one()
    rows = (await db.execute(select(YardAppointment).where(and_(*filters))
            .order_by(YardAppointment.scheduled_at.asc().nullslast(), YardAppointment.queue_position)
            .offset(pagination.offset).limit(pagination.limit))).scalars().all()
    return {"items": [AppointmentResponse.model_validate(a) for a in rows], "total": total,
            "page": pagination.page, "page_size": pagination.page_size}


async def _get_appt(db, tenant_id, appt_id) -> YardAppointment:
    appt = (await db.execute(select(YardAppointment).where(and_(
        YardAppointment.id == appt_id, YardAppointment.tenant_id == tenant_id)))).scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    return appt


@router.post("/appointments/{appt_id}/assign-dock", response_model=AppointmentResponse, summary="Asignar muelle")
async def assign_dock(appt_id: uuid.UUID, dock_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep) -> AppointmentResponse:
    appt = await _get_appt(db, current_user.tenant_id, appt_id)
    dock = (await db.execute(select(Dock).where(and_(
        Dock.id == dock_id, Dock.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
    if not dock:
        raise HTTPException(status_code=404, detail="Muelle no encontrado.")
    appt.dock_id = dock_id
    appt.status = "at_dock"
    appt.at_dock_at = datetime.now(timezone.utc)
    dock.status = "occupied"
    await db.commit(); await db.refresh(appt)
    return appt


@router.post("/appointments/{appt_id}/arrive", response_model=AppointmentResponse, summary="Registrar llegada")
async def arrive(appt_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep) -> AppointmentResponse:
    appt = await _get_appt(db, current_user.tenant_id, appt_id)
    appt.status = "arrived"
    appt.arrived_at = datetime.now(timezone.utc)
    await db.commit(); await db.refresh(appt)
    return appt


@router.post("/appointments/{appt_id}/depart", response_model=AppointmentResponse, summary="Registrar salida")
async def depart(appt_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep) -> AppointmentResponse:
    appt = await _get_appt(db, current_user.tenant_id, appt_id)
    appt.status = "departed"
    appt.departed_at = datetime.now(timezone.utc)
    if appt.dock_id:
        dock = (await db.execute(select(Dock).where(Dock.id == appt.dock_id))).scalar_one_or_none()
        if dock:
            dock.status = "available"
    await db.commit(); await db.refresh(appt)
    return appt
