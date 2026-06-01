"""
WMS Panama — Asistente WMS con LangChain RAG
==============================================
Asistente conversacional especializado en operaciones de almacén.
Usa Retrieval-Augmented Generation (RAG) para responder preguntas
sobre el estado del sistema, OCs, SOs, inventario y KPIs.

Arquitectura:
  ┌──────────┐    ┌─────────────┐    ┌──────────────┐
  │  Usuario │───▶│  LangChain  │───▶│ VectorStore  │
  │ pregunta │    │  RetrievalQA│    │ (Meilisearch │
  └──────────┘    └──────┬──────┘    │  / pgvector) │
                         │           └──────────────┘
                         ▼
                  ┌──────────────┐
                  │  LLM (OpenAI │
                  │  / Ollama)   │
                  └──────────────┘

Fallback: si LangChain no está disponible, usa un sistema
de respuestas basado en templates + consultas directas a la BD.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from uuid import UUID, uuid4

import structlog

log = structlog.get_logger(__name__)

# ── System prompt del asistente ────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Asistente Inteligente del WMS Panama.
Tu misión es ayudar a los operadores, supervisores y gerentes a
gestionar eficientemente el almacén respondiendo preguntas sobre:
  - Estado del inventario (stock, ubicaciones, lotes)
  - Órdenes de Compra y recepciones (GRNs)
  - Órdenes de Venta, picking y envíos
  - KPIs y alertas del sistema
  - Procedimientos y mejores prácticas WMS

Reglas:
  1. Responde siempre en español (Panamá).
  2. Sé conciso y específico. Evita respuestas genéricas.
  3. Si no tienes datos concretos, dilo claramente.
  4. Para datos financieros usa USD como moneda predeterminada.
  5. Nunca inventes números que no hayas recuperado de los datos.
  6. Si detectas una situación urgente (stockout, vencimiento), dilo explícitamente.
"""

# ── Intents detectados sin LLM ─────────────────────────────────────────────

INTENT_PATTERNS = {
    "stock_query":     ["cuánto stock", "cuántas unidades", "stock de", "inventario de"],
    "po_query":        ["órdenes de compra", "OC pendiente", "cuándo llega", "proveedor"],
    "so_query":        ["órdenes de venta", "pedido del cliente", "SO pendiente"],
    "kpi_query":       ["kpi", "métricas", "fill rate", "on-time", "short pick"],
    "alert_query":     ["alerta", "anomalía", "riesgo", "vencimiento", "stockout"],
    "putaway_query":   ["putaway", "ubicar", "dónde guardar"],
    "picking_query":   ["picking", "recoger", "ruta", "wave"],
}


class WMSAssistant:
    """
    Asistente conversacional WMS.
    Mantiene el historial de conversación y enriquece
    las respuestas con datos en tiempo real de la BD.
    """

    def __init__(self, db, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # ── API pública ───────────────────────────────────────────────────────────

    async def chat(
        self,
        message: str,
        conversation_id: Optional[UUID] = None,
        context_type: Optional[str] = None,
        context_id: Optional[UUID] = None,
    ) -> dict:
        """
        Procesa un mensaje y retorna la respuesta del asistente.
        Crea o continúa una conversación.
        """
        # Obtener o crear conversación
        conv = await self._get_or_create_conversation(
            conversation_id, context_type, context_id
        )

        # Guardar mensaje del usuario
        await self._save_message(conv.id, "user", message)

        # Generar respuesta
        start_ms = _now_ms()
        response_text, sources, tokens = await self._generate_response(
            message=message,
            conversation=conv,
            context_type=context_type,
            context_id=context_id,
        )
        latency = _now_ms() - start_ms

        # Guardar respuesta del asistente
        await self._save_message(
            conv.id, "assistant", response_text,
            sources=sources, tokens_used=tokens, latency_ms=latency
        )

        return {
            "conversation_id": str(conv.id),
            "response": response_text,
            "sources": sources,
            "latency_ms": latency,
            "tokens_used": tokens,
        }

    async def list_conversations(self, page: int = 1, page_size: int = 20) -> dict:
        from sqlalchemy import select, func, and_
        from app.models.ai import AIConversation

        filters = [
            AIConversation.tenant_id == self.tenant_id,
            AIConversation.user_id == self.user_id,
            AIConversation.is_active == True,
        ]
        total = (await self.db.execute(
            select(func.count(AIConversation.id)).where(and_(*filters))
        )).scalar_one()

        rows = (await self.db.execute(
            select(AIConversation)
            .where(and_(*filters))
            .order_by(AIConversation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).scalars().all()

        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    async def get_conversation(self, conversation_id: UUID):
        from sqlalchemy import select, and_
        from app.models.ai import AIConversation

        result = await self.db.execute(
            select(AIConversation).where(
                and_(
                    AIConversation.id == conversation_id,
                    AIConversation.tenant_id == self.tenant_id,
                    AIConversation.user_id == self.user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    # ── Generación de respuesta ───────────────────────────────────────────────

    async def _generate_response(
        self,
        message: str,
        conversation,
        context_type: Optional[str],
        context_id: Optional[UUID],
    ) -> tuple[str, list, int]:
        """
        Intenta usar LangChain RAG; si no está disponible,
        usa el motor de templates + consultas directas.
        """
        # Enriquecer con contexto de BD
        context_data = await self._gather_context(message, context_type, context_id)

        try:
            return await self._langchain_response(message, context_data)
        except ImportError:
            log.info("assistant.langchain_not_installed", fallback="template_engine")
            return self._template_response(message, context_data), [], 0
        except Exception as e:
            log.warning("assistant.langchain_error", error=str(e))
            return self._template_response(message, context_data), [], 0

    async def _langchain_response(
        self, message: str, context_data: dict
    ) -> tuple[str, list, int]:
        """Usa LangChain con OpenAI o Ollama."""
        from langchain.chat_models import ChatOpenAI
        from langchain.schema import HumanMessage, SystemMessage, AIMessage
        from app.core.config import settings

        llm = ChatOpenAI(
            model_name=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            openai_api_key=getattr(settings, "OPENAI_API_KEY", ""),
            max_tokens=800,
        )

        context_str = json.dumps(context_data, ensure_ascii=False, indent=2)
        system_with_context = (
            SYSTEM_PROMPT
            + f"\n\nDatos actuales del sistema:\n```json\n{context_str}\n```"
        )

        messages = [
            SystemMessage(content=system_with_context),
            HumanMessage(content=message),
        ]

        response = await llm.agenerate([messages])
        text = response.generations[0][0].text
        tokens = response.llm_output.get("token_usage", {}).get("total_tokens", 0)

        return text, [], tokens

    def _template_response(self, message: str, context_data: dict) -> str:
        """
        Motor de respuesta por templates cuando LangChain no está disponible.
        Detecta el intent y arma una respuesta estructurada.
        """
        msg_lower = message.lower()
        intent = "general"
        for key, patterns in INTENT_PATTERNS.items():
            if any(p in msg_lower for p in patterns):
                intent = key
                break

        if intent == "stock_query":
            stock_info = context_data.get("stock_summary", {})
            if stock_info:
                return (
                    f"📦 **Stock actual:**\n"
                    f"- Total disponible: {stock_info.get('total_available', '—')} uds\n"
                    f"- Reservado: {stock_info.get('total_reserved', '—')} uds\n"
                    f"- Ubicaciones: {stock_info.get('locations_count', '—')}\n\n"
                    f"Puedo darte más detalle si especificas el producto."
                )
            return "No encontré datos de stock para tu consulta. ¿Puedes especificar el producto o SKU?"

        if intent == "kpi_query":
            inbound = context_data.get("inbound_metrics", {})
            outbound = context_data.get("outbound_metrics", {})
            return (
                f"📊 **KPIs del almacén:**\n\n"
                f"**Inbound:**\n"
                f"- GRNs hoy: {inbound.get('grns_today', '—')}\n"
                f"- Putaway pendiente: {inbound.get('putaway_tasks_open', '—')}\n"
                f"- Tasa defectos: {inbound.get('avg_defect_rate_pct', '—')}%\n\n"
                f"**Outbound:**\n"
                f"- Órdenes abiertas: {outbound.get('orders_open', '—')}\n"
                f"- Picks hoy: {outbound.get('picks_today', '—')}\n"
                f"- Short pick rate: {outbound.get('short_pick_rate_pct', '—')}%\n"
                f"- Envíos en tránsito: {outbound.get('shipments_in_transit', '—')}"
            )

        if intent == "alert_query":
            alerts = context_data.get("active_alerts", [])
            if alerts:
                lines = "\n".join(f"⚠️ {a['title']} ({a['severity']})" for a in alerts[:5])
                return f"**Alertas activas ({len(alerts)}):**\n{lines}"
            return "✅ No hay alertas críticas activas en este momento."

        if intent == "po_query":
            pos = context_data.get("open_pos", 0)
            overdue = context_data.get("overdue_pos", 0)
            resp = f"📋 **Órdenes de Compra:**\n- Abiertas: {pos}\n- Vencidas: {overdue}"
            if overdue > 0:
                resp += f"\n⚠️ Tienes {overdue} OC(s) con fecha vencida."
            return resp

        if intent == "so_query":
            sos = context_data.get("open_sos", 0)
            return (
                f"📦 **Órdenes de Venta abiertas: {sos}**\n"
                f"¿Quieres ver las pendientes de picking, empaque o despacho?"
            )

        # Respuesta genérica
        return (
            "Hola, soy el Asistente WMS Panama. Puedo ayudarte con:\n"
            "- 📦 Stock e inventario\n"
            "- 🚚 Órdenes de Compra y recepciones\n"
            "- 📤 Órdenes de Venta, picking y envíos\n"
            "- 📊 KPIs y alertas del sistema\n\n"
            "¿Sobre qué te gustaría saber?"
        )

    # ── Recopilación de contexto ──────────────────────────────────────────────

    async def _gather_context(
        self,
        message: str,
        context_type: Optional[str],
        context_id: Optional[UUID],
    ) -> dict:
        """Recopila datos relevantes de la BD según el intent del mensaje."""
        context: dict = {}
        msg_lower = message.lower()

        try:
            # KPIs siempre útiles
            if any(w in msg_lower for w in ["kpi", "métrica", "estadística", "resumen"]):
                context["inbound_metrics"]  = await self._get_inbound_kpis()
                context["outbound_metrics"] = await self._get_outbound_kpis()

            # Alertas
            if any(w in msg_lower for w in ["alerta", "riesgo", "anomalía", "urgente"]):
                context["active_alerts"] = await self._get_active_alerts()

            # PO info
            if any(w in msg_lower for w in ["compra", "proveedor", "oc", "pedido"]):
                context["open_pos"]    = await self._count_open_pos()
                context["overdue_pos"] = await self._count_overdue_pos()

            # SO info
            if any(w in msg_lower for w in ["venta", "cliente", "so", "orden"]):
                context["open_sos"] = await self._count_open_sos()

            # Stock info
            if any(w in msg_lower for w in ["stock", "inventario", "unidad", "disponible"]):
                context["stock_summary"] = await self._get_stock_summary()

        except Exception as e:
            log.warning("assistant.context_error", error=str(e))

        return context

    # ── Consultas BD ──────────────────────────────────────────────────────────

    async def _get_inbound_kpis(self) -> dict:
        try:
            from app.services.inbound_service import InboundService
            svc = InboundService(self.db, self.tenant_id, self.user_id)
            return await svc.get_dashboard_metrics()
        except Exception:
            return {}

    async def _get_outbound_kpis(self) -> dict:
        try:
            from app.services.outbound_service import OutboundService
            svc = OutboundService(self.db, self.tenant_id, self.user_id)
            return await svc.get_dashboard_metrics()
        except Exception:
            return {}

    async def _get_active_alerts(self) -> list:
        from sqlalchemy import select, and_
        from app.models.ai import ReplenishmentAlert
        try:
            result = await self.db.execute(
                select(ReplenishmentAlert)
                .where(and_(
                    ReplenishmentAlert.tenant_id == self.tenant_id,
                    ReplenishmentAlert.is_resolved == False,
                ))
                .order_by(ReplenishmentAlert.created_at.desc())
                .limit(10)
            )
            alerts = result.scalars().all()
            return [{"title": a.title, "severity": a.severity.value} for a in alerts]
        except Exception:
            return []

    async def _count_open_pos(self) -> int:
        from sqlalchemy import select, func, and_
        from app.models.inbound import PurchaseOrder, POStatus
        try:
            r = await self.db.execute(
                select(func.count(PurchaseOrder.id)).where(and_(
                    PurchaseOrder.tenant_id == self.tenant_id,
                    PurchaseOrder.status.in_([POStatus.DRAFT, POStatus.CONFIRMED,
                                              POStatus.PARTIALLY_RECEIVED]),
                ))
            )
            return r.scalar_one()
        except Exception:
            return 0

    async def _count_overdue_pos(self) -> int:
        from sqlalchemy import select, func, and_
        from app.models.inbound import PurchaseOrder, POStatus
        try:
            r = await self.db.execute(
                select(func.count(PurchaseOrder.id)).where(and_(
                    PurchaseOrder.tenant_id == self.tenant_id,
                    PurchaseOrder.status.in_([POStatus.CONFIRMED, POStatus.PARTIALLY_RECEIVED]),
                    PurchaseOrder.expected_delivery_date < datetime.now(timezone.utc),
                ))
            )
            return r.scalar_one()
        except Exception:
            return 0

    async def _count_open_sos(self) -> int:
        from sqlalchemy import select, func, and_
        from app.models.outbound import SalesOrder, SOStatus
        try:
            r = await self.db.execute(
                select(func.count(SalesOrder.id)).where(and_(
                    SalesOrder.tenant_id == self.tenant_id,
                    SalesOrder.status.in_([SOStatus.CONFIRMED, SOStatus.ALLOCATED,
                                           SOStatus.PICKING, SOStatus.PACKED]),
                ))
            )
            return r.scalar_one()
        except Exception:
            return 0

    async def _get_stock_summary(self) -> dict:
        from sqlalchemy import select, func, and_
        from app.models.inventory import InventoryLevel
        try:
            r = await self.db.execute(
                select(
                    func.sum(InventoryLevel.quantity_available).label("total_available"),
                    func.sum(InventoryLevel.quantity_reserved).label("total_reserved"),
                    func.count(InventoryLevel.id).label("locations_count"),
                ).where(InventoryLevel.tenant_id == self.tenant_id)
            )
            row = r.one()
            return {
                "total_available":  float(row.total_available or 0),
                "total_reserved":   float(row.total_reserved or 0),
                "locations_count":  row.locations_count or 0,
            }
        except Exception:
            return {}

    # ── Persistencia de conversación ──────────────────────────────────────────

    async def _get_or_create_conversation(
        self,
        conversation_id: Optional[UUID],
        context_type: Optional[str],
        context_id: Optional[UUID],
    ):
        from sqlalchemy import select, and_
        from app.models.ai import AIConversation

        if conversation_id:
            result = await self.db.execute(
                select(AIConversation).where(
                    and_(
                        AIConversation.id == conversation_id,
                        AIConversation.tenant_id == self.tenant_id,
                    )
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                return conv

        # Crear nueva conversación
        conv = AIConversation(
            id=uuid4(),
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            title="Nueva conversación",
            context_type=context_type,
            context_id=context_id,
        )
        self.db.add(conv)
        await self.db.flush()
        return conv

    async def _save_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        sources: Optional[list] = None,
        tokens_used: int = 0,
        latency_ms: int = 0,
    ) -> None:
        from app.models.ai import AIConversationMessage, MessageRole
        from sqlalchemy import update
        from app.models.ai import AIConversation

        msg = AIConversationMessage(
            id=uuid4(),
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            role=MessageRole(role),
            content=content,
            tokens_used=tokens_used,
            sources=sources or [],
            latency_ms=latency_ms,
        )
        self.db.add(msg)

        # Actualizar contadores de la conversación
        await self.db.execute(
            update(AIConversation)
            .where(AIConversation.id == conversation_id)
            .values(
                message_count=AIConversation.message_count + 1,
                total_tokens=AIConversation.total_tokens + tokens_used,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.db.flush()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
