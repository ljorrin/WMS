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
