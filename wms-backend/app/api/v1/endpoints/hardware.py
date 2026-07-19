"""
WMS Panamá — Hardware RFID/RF y Etiquetas ZPL — Fase 2 del plan de implementación
====================================================================================
GET/POST /hardware/readers          — registro y listado de readers RFID fijos
GET/POST /hardware/readers/{id}/antennas — antenas por reader
POST     /hardware/tag-reads        — ingesta de lecturas (llamado por el
                                       gateway LLRP o por un service-account
                                       dedicado; ver scripts/rfid_reader_simulator.py)
GET      /hardware/tag-reads        — historial de lecturas
GET      /hardware/dashboard        — KPIs de readers/lecturas
POST     /hardware/labels/zpl/sscc  — genera el ZPL de una etiqueta de pallet (SSCC)
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import CurrentUserDep, DBDep, PaginationDep, require_permission
from app.core.exceptions import RfidDeviceError, RfidServiceError
from app.schemas.rfid import (
    RfidAntennaCreate, RfidAntennaResponse, RfidReaderCreate, RfidReaderResponse,
    RfidReaderUpdate, RfidTagReadIngest, RfidTagReadResponse, ZplLabelResponse, ZplPalletLabelRequest,
)
from app.services.rfid_service import RfidService
from app.services.zpl_service import ZplGenerationError, build_sscc_pallet_label_zpl

router = APIRouter()


def _svc(db) -> RfidService:
    return RfidService(db)


# ── Readers ────────────────────────────────────────────────────────────────────
@router.post(
    "/readers", response_model=RfidReaderResponse, summary="Registrar reader RFID",
    dependencies=[Depends(require_permission("hardware:manage"))],
)
async def register_reader(
    payload: RfidReaderCreate, db: DBDep, current_user: CurrentUserDep,
) -> RfidReaderResponse:
    try:
        reader = await _svc(db).register_reader(
            current_user.tenant_id, payload.model_dump(), current_user.id
        )
    except RfidDeviceError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return reader


@router.put(
    "/readers/{reader_id}", response_model=RfidReaderResponse,
    summary="Editar reader RFID (IP, modelo, vendor, notas)",
    dependencies=[Depends(require_permission("hardware:manage"))],
)
async def update_reader(
    reader_id: uuid.UUID, payload: RfidReaderUpdate, db: DBDep, current_user: CurrentUserDep,
) -> RfidReaderResponse:
    try:
        reader = await _svc(db).update_reader(
            current_user.tenant_id, reader_id, payload.model_dump(exclude_unset=True)
        )
    except RfidServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return reader


@router.get(
    "/readers", summary="Listar readers RFID",
    dependencies=[Depends(require_permission("hardware:read"))],
)
async def list_readers(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
) -> dict:
    rows = await _svc(db).list_readers(current_user.tenant_id, warehouse_id)
    return {"items": [RfidReaderResponse.model_validate(r) for r in rows]}


# ── Antenas ────────────────────────────────────────────────────────────────────
@router.post(
    "/readers/{reader_id}/antennas", response_model=RfidAntennaResponse,
    summary="Registrar antena en un reader",
    dependencies=[Depends(require_permission("hardware:manage"))],
)
async def register_antenna(
    reader_id: uuid.UUID, payload: RfidAntennaCreate, db: DBDep, current_user: CurrentUserDep,
) -> RfidAntennaResponse:
    try:
        antenna = await _svc(db).register_antenna(
            current_user.tenant_id, reader_id, payload.model_dump()
        )
    except RfidDeviceError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RfidServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return antenna


@router.get(
    "/readers/{reader_id}/antennas", summary="Listar antenas de un reader",
    dependencies=[Depends(require_permission("hardware:read"))],
)
async def list_antennas(
    reader_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep,
) -> dict:
    rows = await _svc(db).list_antennas(current_user.tenant_id, reader_id)
    return {"items": [RfidAntennaResponse.model_validate(r) for r in rows]}


# ── Ingesta de lecturas ────────────────────────────────────────────────────────
# NOTA: en producción, este endpoint lo llama el gateway/middleware LLRP (no un
# usuario humano) con un service-account que solo tiene el permiso
# "hardware:ingest" — el reader físico habla LLRP con ese gateway, no con esta
# API HTTP directamente (ver docstring de app/models/rfid.py).
@router.post(
    "/tag-reads", response_model=RfidTagReadResponse, summary="Ingesta de una lectura de tag RFID",
    dependencies=[Depends(require_permission("hardware:ingest"))],
)
async def ingest_tag_read(
    payload: RfidTagReadIngest, db: DBDep, current_user: CurrentUserDep,
) -> RfidTagReadResponse:
    try:
        tag_read = await _svc(db).ingest_tag_read(current_user.tenant_id, payload.model_dump())
    except RfidServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return tag_read


@router.get(
    "/tag-reads", summary="Historial de lecturas de tags",
    dependencies=[Depends(require_permission("hardware:read"))],
)
async def list_tag_reads(
    db: DBDep, current_user: CurrentUserDep, pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
    reader_id: Optional[uuid.UUID] = Query(None),
    processed: Optional[bool] = Query(None),
) -> dict:
    rows, total = await _svc(db).list_tag_reads(
        current_user.tenant_id, warehouse_id=warehouse_id, reader_id=reader_id,
        processed=processed, offset=pagination.offset, limit=pagination.limit,
    )
    return {
        "items": [RfidTagReadResponse.model_validate(r) for r in rows],
        "total": total, "page": pagination.page, "page_size": pagination.page_size,
    }


@router.delete(
    "/tag-reads", summary="Limpiar historial de lecturas (borrado definitivo)",
    dependencies=[Depends(require_permission("hardware:manage"))],
)
async def clear_tag_reads(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
) -> dict:
    deleted = await _svc(db).clear_tag_reads(current_user.tenant_id, warehouse_id)
    return {"deleted": deleted}


# ── Dashboard ──────────────────────────────────────────────────────────────────
@router.get(
    "/dashboard", summary="KPIs de hardware RFID",
    dependencies=[Depends(require_permission("hardware:read"))],
)
async def dashboard(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
) -> dict:
    return await _svc(db).get_dashboard_metrics(current_user.tenant_id, warehouse_id)


# ── Etiquetas ZPL ──────────────────────────────────────────────────────────────
@router.post(
    "/labels/zpl/sscc", response_model=ZplLabelResponse,
    summary="Generar ZPL de etiqueta de pallet/bulto (GS1-128 SSCC, opcionalmente RFID)",
    dependencies=[Depends(require_permission("hardware:read"))],
)
async def generate_sscc_label(payload: ZplPalletLabelRequest) -> ZplLabelResponse:
    try:
        zpl, epc_hex, epc_uri = build_sscc_pallet_label_zpl(
            payload.sscc, company_prefix=payload.company_prefix,
            description=payload.description, encode_rfid=payload.encode_rfid,
        )
    except ZplGenerationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ZplLabelResponse(zpl=zpl, epc_hex=epc_hex, epc_uri=epc_uri)
