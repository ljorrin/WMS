"""
WMS Panama — Excepciones de Dominio
=====================================
Clases base de excepción para todos los servicios.
Sin importaciones de modelos ni SQLAlchemy — importable en tests puros.
"""


# ── Base ──────────────────────────────────────────────────────────────────────

class WMSError(Exception):
    """Excepción raíz de dominio WMS."""


# ── Inventory ─────────────────────────────────────────────────────────────────

class InventoryServiceError(WMSError):
    """Error genérico del servicio de inventario."""


class InsufficientStockError(InventoryServiceError):
    """Stock insuficiente para completar la operación."""


# ── Inbound ───────────────────────────────────────────────────────────────────

class InboundServiceError(WMSError):
    """Error genérico del servicio inbound."""


class POStateError(InboundServiceError):
    """La OC no está en un estado válido para la operación."""


class GRNStateError(InboundServiceError):
    """El GRN no está en un estado válido para la operación."""


class QCStateError(InboundServiceError):
    """La inspección de calidad no está en estado válido."""


class PutawayStateError(InboundServiceError):
    """La tarea de putaway no está en estado válido."""


# ── Outbound (futuro) ─────────────────────────────────────────────────────────

class OutboundServiceError(WMSError):
    """Error genérico del servicio outbound."""


class OrderStateError(OutboundServiceError):
    """La orden de venta no está en un estado válido."""


class PickingStateError(OutboundServiceError):
    """La tarea de picking no está en estado válido."""


# -- Labor Management (FR-090...093) --------------------------------------------

class LaborServiceError(WMSError):
    """Error generico del servicio de gestion de mano de obra."""


class LaborStandardError(LaborServiceError):
    """Conflicto o invalidez en un estandar de labor."""


class LaborTaskStateError(LaborServiceError):
    """La tarea de labor no esta en un estado valido para la operacion."""


# -- Slotting dinamico (FR-094...097) --------------------------------------------

class SlottingServiceError(WMSError):
    """Error generico del servicio de slotting."""


class SlottingPolicyError(SlottingServiceError):
    """Conflicto o invalidez en una politica de slotting."""


class SlottingStateError(SlottingServiceError):
    """La recomendacion de slotting no esta en un estado valido."""


# -- Hardware RFID/RF (Fase 2) ---------------------------------------------------

class RfidServiceError(WMSError):
    """Error generico del servicio de hardware RFID."""


class RfidDeviceError(RfidServiceError):
    """Conflicto o invalidez en un reader/antena registrado."""
