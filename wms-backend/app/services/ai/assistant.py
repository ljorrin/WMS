"""
WMS Panama — Asistente WMS agéntico (tool-calling) — Fase 5
==============================================================
Asistente conversacional especializado en operaciones de almacén, con
capacidad de EJECUTAR acciones reales (no solo responder preguntas) via
tool-calling del LLM: el modelo decide qué herramienta(s) invocar
(app/services/ai/tools.py), estas ejecutan contra los servicios/repos
reales del WMS, y el resultado se realimenta al modelo hasta producir una
respuesta final. Mantiene memoria conversacional real (turnos previos de
la misma conversación se pasan al LLM).

Arquitectura del loop agéntico:
  Usuario ──▶ LLM (bind_tools) ──▶ ¿tool_calls? ──sí──▶ ejecutar tool real
                  ▲                                          │
                  └──────────── ToolMessage(resultado) ◀──────┘
                  │
                  no
                  ▼
             Respuesta final

Fallback SIN LLM configurado (sin OPENAI_API_KEY): motor de respuestas por
templates + consultas de solo lectura a la BD — NO ejecuta acciones (el
tool-calling requiere que un LLM interprete la intención y extraiga
argumentos como UUIDs; sin LLM no hay forma confiable de hacerlo desde
texto libre).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from uuid import UUID, uuid4

import structlog

log = structlog.get_logger(__name__)

MAX_TOOL_ITERATIONS = 4
MAX_HISTORY_MESSAGES = 20

_MD_CHARS_RE = re.compile(r"[*_`#~]")
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]+",
    flags=re.UNICODE,
)


def _clean_text_for_speech(text: str) -> str:
    """Quita markdown/emojis antes de sintetizar voz — si no, el TTS los lee literal."""
    text = _EMOJI_RE.sub("", text)
    text = _MD_CHARS_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()

# ── System prompt del asistente ────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Asistente Inteligente del WMS Panama.
Tu misión es ayudar a los operadores, supervisores y gerentes a
gestionar eficientemente el almacén. Tienes acceso a herramientas (tools)
que consultan y MODIFICAN datos reales del sistema — úsalas siempre que
necesites datos actuales o el usuario te pida ejecutar una acción (asignar
una tarea, resolver una anomalía o alerta, etc.). No inventes resultados:
si una acción requiere una herramienta, invócala.

Reglas:
  1. Responde siempre en español (Panamá).
  2. Sé conciso y específico. Evita respuestas genéricas.
  3. Antes de responder con datos (stock, KPIs, alertas), invoca la
     herramienta correspondiente — no asumas ni inventes números.
  4. Si una herramienta devuelve "ok": false (p. ej. permiso denegado o
     dato no encontrado), informa el problema claramente al usuario en
     vez de inventar una respuesta alternativa.
  5. Antes de ejecutar una acción irreversible o de asignación (asignar
     tarea, resolver anomalía/alerta), confirma que entendiste bien qué
     pidió el usuario; si falta un dato requerido (p. ej. a qué operario
     asignar), pregúntalo en vez de adivinar.
  6. Para datos financieros usa USD como moneda predeterminada.
  7. Si detectas una situación urgente (stockout, vencimiento), dilo explícitamente.
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

    def __init__(
        self, db, tenant_id: UUID, user_id: UUID,
        permissions: frozenset[str] = frozenset(), is_superadmin: bool = False,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.permissions = permissions
        self.is_superadmin = is_superadmin

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

        # Cargar historial ANTES de guardar el mensaje nuevo (memoria conversacional real)
        history = await self._load_history(conv.id)

        # Guardar mensaje del usuario
        await self._save_message(conv.id, "user", message)

        # Generar respuesta
        start_ms = _now_ms()
        response_text, sources, tokens = await self._generate_response(
            message=message,
            conversation=conv,
            history=history,
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
        from sqlalchemy.orm import selectinload
        from app.models.ai import AIConversation

        result = await self.db.execute(
            select(AIConversation)
            .options(selectinload(AIConversation.messages))
            .where(
                and_(
                    AIConversation.id == conversation_id,
                    AIConversation.tenant_id == self.tenant_id,
                    AIConversation.user_id == self.user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    # ── Transcripción de voz (dictado) ─────────────────────────────────────────

    async def transcribe_audio(self, audio_bytes: bytes, filename: str, content_type: str) -> str:
        """Transcribe audio a texto en español via Whisper (OpenAI). Requiere OPENAI_API_KEY."""
        from app.core.config import settings

        if not getattr(settings, "OPENAI_API_KEY", ""):
            raise ValueError("El dictado por voz requiere OPENAI_API_KEY configurada en el servidor.")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        transcript = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename or "audio.webm", audio_bytes, content_type or "audio/webm"),
            language="es",
        )
        return transcript.text.strip()

    async def synthesize_speech(self, text: str) -> bytes:
        """Sintetiza texto a voz (mp3) via TTS (OpenAI). Requiere OPENAI_API_KEY."""
        from app.core.config import settings

        if not getattr(settings, "OPENAI_API_KEY", ""):
            raise ValueError("La respuesta por voz requiere OPENAI_API_KEY configurada en el servidor.")

        clean = _clean_text_for_speech(text)
        if not clean:
            raise ValueError("No hay texto para sintetizar.")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=clean,
            response_format="mp3",
        )
        return await response.aread()

    # ── Generación de respuesta ───────────────────────────────────────────────

    async def _generate_response(
        self,
        message: str,
        conversation,
        history: list[dict],
        context_type: Optional[str],
        context_id: Optional[UUID],
    ) -> tuple[str, list, int]:
        """
        Intenta usar el LLM agéntico (tool-calling); si no está disponible
        o no hay API key configurada, usa el motor de templates + consultas
        directas (solo lectura, sin ejecución de acciones).
        """
        from app.core.config import settings

        if not getattr(settings, "OPENAI_API_KEY", ""):
            log.info("assistant.no_api_key", fallback="template_engine")
            context_data = await self._gather_context(message, context_type, context_id)
            return self._template_response(message, context_data), [], 0

        try:
            return await self._agentic_response(message, history)
        except ImportError:
            log.info("assistant.langchain_not_installed", fallback="template_engine")
            context_data = await self._gather_context(message, context_type, context_id)
            return self._template_response(message, context_data), [], 0
        except Exception as e:
            log.warning("assistant.agentic_error", error=str(e))
            context_data = await self._gather_context(message, context_type, context_id)
            return self._template_response(message, context_data), [], 0

    async def _agentic_response(
        self, message: str, history: list[dict],
    ) -> tuple[str, list, int]:
        """
        Loop agéntico real: el LLM decide qué herramienta(s) invocar
        (app/services/ai/tools.py), estas ejecutan contra la BD real, y el
        resultado se realimenta al modelo hasta que produce una respuesta
        final (sin más tool_calls) o se alcanza MAX_TOOL_ITERATIONS.
        """
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
        from langchain_openai import ChatOpenAI

        from app.core.config import settings
        from app.services.ai import tools as ai_tools

        llm = ChatOpenAI(
            model_name=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.1,
            openai_api_key=getattr(settings, "OPENAI_API_KEY", ""),
            max_tokens=800,
        )
        llm_with_tools = llm.bind_tools(ai_tools.to_openai_tool_schemas())

        messages: list = [SystemMessage(content=SYSTEM_PROMPT)]
        for turn in history:
            if turn["role"] == "user":
                messages.append(HumanMessage(content=turn["content"]))
            elif turn["role"] == "assistant":
                messages.append(AIMessage(content=turn["content"]))
        messages.append(HumanMessage(content=message))

        ctx = ai_tools.ToolContext(
            db=self.db, tenant_id=self.tenant_id, user_id=self.user_id,
            permissions=self.permissions, is_superadmin=self.is_superadmin,
        )
        total_tokens = 0
        tool_trace: list = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await llm_with_tools.ainvoke(messages)
            usage = getattr(response, "usage_metadata", None) or {}
            total_tokens += usage.get("total_tokens", 0)

            if not response.tool_calls:
                return response.content, tool_trace, total_tokens

            messages.append(response)
            for call in response.tool_calls:
                result = await ai_tools.execute_tool(call["name"], call["args"], ctx)
                # Normalizar tipos no serializables (Decimal, UUID, datetime) antes de
                # persistir en la columna JSON `sources` — el JSON encoder por defecto
                # de SQLAlchemy no sabe convertirlos.
                safe_result = json.loads(json.dumps(result, ensure_ascii=False, default=str))
                tool_trace.append({"tool": call["name"], "args": call["args"], "result": safe_result})
                messages.append(ToolMessage(
                    content=json.dumps(result, ensure_ascii=False, default=str),
                    tool_call_id=call["id"],
                ))

        return (
            "No pude completar tu solicitud tras varios pasos — intenta reformularla "
            "o hacerla más específica.",
            tool_trace, total_tokens,
        )

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

    # ── Memoria conversacional ─────────────────────────────────────────────────

    async def _load_history(self, conversation_id: UUID) -> list[dict]:
        """Últimos MAX_HISTORY_MESSAGES turnos de la conversación, orden cronológico."""
        from sqlalchemy import select

        from app.models.ai import AIConversationMessage

        rows = (await self.db.execute(
            select(AIConversationMessage.role, AIConversationMessage.content)
            .where(AIConversationMessage.conversation_id == conversation_id)
            .order_by(AIConversationMessage.created_at.desc())
            .limit(MAX_HISTORY_MESSAGES)
        )).all()
        return [{"role": r.value if hasattr(r, "value") else r, "content": c} for r, c in reversed(rows)]

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
