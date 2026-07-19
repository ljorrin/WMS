"""
WMS Panama — Tests Unitarios: Asistente IA agéntico (Fase 5)
================================================================
Tests PUROS sin BD real ni red: la ejecución de una tool concreta que sí
toca BD (p. ej. `_get_stock_summary`) requiere Postgres real y se cubre en
`tests/integration_db/test_ai_agent_tools.py`. Aquí se prueba:

  - El registro de tools (schemas válidos, sin duplicados).
  - El gate de permisos de `execute_tool` (se corta ANTES de tocar BD).
  - El loop agéntico multi-paso de `WMSAssistant._agentic_response` contra
    un LLM falso inyectado (sin red real), verificando que: invoca la(s)
    tool(s) correctas con los argumentos que decidió el LLM, realimenta el
    resultado, se detiene al no haber más tool_calls, y respeta el tope de
    iteraciones si el LLM nunca deja de pedir tools.

Ejecutar:  pytest tests/unit/test_ai_agent.py --noconftest
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.ai import tools as ai_tools
from app.services.ai.assistant import MAX_TOOL_ITERATIONS, WMSAssistant


# ══════════════════════════════════════════════════════════════════════════════
# 1. REGISTRO DE TOOLS
# ══════════════════════════════════════════════════════════════════════════════

class TestToolRegistry:

    def test_no_duplicate_names(self):
        names = list(ai_tools.AGENT_TOOLS.keys())
        assert len(names) == len(set(names))

    def test_openai_schema_shape(self):
        schemas = ai_tools.to_openai_tool_schemas()
        assert len(schemas) == len(ai_tools.AGENT_TOOLS)
        for schema in schemas:
            assert schema["type"] == "function"
            fn = schema["function"]
            assert isinstance(fn["name"], str) and fn["name"]
            assert isinstance(fn["description"], str) and fn["description"]
            assert fn["parameters"]["type"] == "object"
            assert "properties" in fn["parameters"]

    def test_write_actions_declare_permission(self):
        """Las tools que ejecutan escritura deben requerir un permiso explícito."""
        write_tools = ["resolve_anomaly", "resolve_replenishment_alert", "assign_next_labor_task"]
        for name in write_tools:
            assert ai_tools.AGENT_TOOLS[name].permission is not None


# ══════════════════════════════════════════════════════════════════════════════
# 2. GATE DE PERMISOS (sin BD — se corta antes del handler)
# ══════════════════════════════════════════════════════════════════════════════

class TestPermissionGate:

    @pytest.mark.asyncio
    async def test_denies_without_permission(self):
        ctx = ai_tools.ToolContext(
            db=None, tenant_id=uuid4(), user_id=uuid4(),
            permissions=frozenset(), is_superadmin=False,
        )
        result = await ai_tools.execute_tool(
            "resolve_anomaly", {"anomaly_id": str(uuid4()), "resolution_notes": "x"}, ctx,
        )
        assert result["ok"] is False
        assert "Permiso denegado" in result["error"]

    @pytest.mark.asyncio
    async def test_superadmin_bypasses_gate(self, monkeypatch):
        called = {}

        async def fake_handler(ctx, args):
            called["yes"] = True
            return {"ok": True}

        monkeypatch.setitem(
            ai_tools.AGENT_TOOLS, "resolve_anomaly",
            ai_tools.AgentTool(
                name="resolve_anomaly", description="x",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=fake_handler, permission="ai:anomaly:manage",
            ),
        )
        ctx = ai_tools.ToolContext(
            db=None, tenant_id=uuid4(), user_id=uuid4(),
            permissions=frozenset(), is_superadmin=True,
        )
        result = await ai_tools.execute_tool("resolve_anomaly", {}, ctx)
        assert result["ok"] is True
        assert called.get("yes") is True

    @pytest.mark.asyncio
    async def test_unknown_tool_reports_error(self):
        ctx = ai_tools.ToolContext(db=None, tenant_id=uuid4(), user_id=uuid4())
        result = await ai_tools.execute_tool("no_existe", {}, ctx)
        assert result["ok"] is False
        assert "desconocida" in result["error"]

    @pytest.mark.asyncio
    async def test_handler_exception_is_reported_not_raised(self, monkeypatch):
        async def boom(ctx, args):
            raise RuntimeError("fallo simulado")

        monkeypatch.setitem(
            ai_tools.AGENT_TOOLS, "get_dashboard_kpis",
            ai_tools.AgentTool(
                name="get_dashboard_kpis", description="x",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=boom, permission=None,
            ),
        )
        ctx = ai_tools.ToolContext(db=None, tenant_id=uuid4(), user_id=uuid4())
        result = await ai_tools.execute_tool("get_dashboard_kpis", {}, ctx)
        assert result["ok"] is False
        assert "fallo simulado" in result["error"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. LOOP AGÉNTICO (LLM falso, sin red)
# ══════════════════════════════════════════════════════════════════════════════

class _FakeAIMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage_metadata = {"total_tokens": 7}


class _FakeBoundLLM:
    """Sustituye a `llm.bind_tools(...)`: encola respuestas y registra qué se le envió."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.invocations: list[list] = []

    async def ainvoke(self, messages):
        self.invocations.append(list(messages))
        return self._responses.pop(0)


class _FakeChatOpenAI:
    """Sustituye a `ChatOpenAI(...)`: `bind_tools()` devuelve el bound LLM falso configurado."""
    _next_bound = None

    def __init__(self, **kwargs):
        pass

    def bind_tools(self, schemas):
        return _FakeChatOpenAI._next_bound


def _patch_llm(monkeypatch, bound_llm: _FakeBoundLLM):
    _FakeChatOpenAI._next_bound = bound_llm
    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "sk-fake-para-test")


@pytest.mark.asyncio
class TestAgenticLoop:

    async def test_single_tool_call_then_final_answer(self, monkeypatch):
        tool_call = {"name": "get_dashboard_kpis", "args": {"module": "inbound"}, "id": "call_1"}
        bound = _FakeBoundLLM([
            _FakeAIMessage(tool_calls=[tool_call]),
            _FakeAIMessage(content="Tienes 3 GRNs pendientes hoy."),
        ])
        _patch_llm(monkeypatch, bound)

        executed = []

        async def fake_execute_tool(name, args, ctx):
            executed.append((name, args))
            return {"ok": True, "grns_today": 3}

        monkeypatch.setattr(ai_tools, "execute_tool", fake_execute_tool)

        assistant = WMSAssistant(db=None, tenant_id=uuid4(), user_id=uuid4())
        text, trace, tokens = await assistant._agentic_response("¿cuántos GRNs hay hoy?", history=[])

        assert text == "Tienes 3 GRNs pendientes hoy."
        assert executed == [("get_dashboard_kpis", {"module": "inbound"})]
        assert trace[0]["tool"] == "get_dashboard_kpis"
        assert trace[0]["result"]["grns_today"] == 3
        assert tokens == 14  # 7 + 7 (dos invocaciones al LLM)
        assert len(bound.invocations) == 2  # 1ra pide la tool, 2da ya trae el resultado

    async def test_multiple_tool_calls_in_one_turn(self, monkeypatch):
        calls = [
            {"name": "list_active_alerts", "args": {}, "id": "call_1"},
            {"name": "list_open_anomalies", "args": {}, "id": "call_2"},
        ]
        bound = _FakeBoundLLM([
            _FakeAIMessage(tool_calls=calls),
            _FakeAIMessage(content="Resumen listo."),
        ])
        _patch_llm(monkeypatch, bound)

        executed = []

        async def fake_execute_tool(name, args, ctx):
            executed.append(name)
            return {"ok": True}

        monkeypatch.setattr(ai_tools, "execute_tool", fake_execute_tool)

        assistant = WMSAssistant(db=None, tenant_id=uuid4(), user_id=uuid4())
        text, trace, _ = await assistant._agentic_response("dame un resumen de riesgos", history=[])

        assert text == "Resumen listo."
        assert executed == ["list_active_alerts", "list_open_anomalies"]
        assert len(trace) == 2

    async def test_respects_conversation_history(self, monkeypatch):
        bound = _FakeBoundLLM([_FakeAIMessage(content="Sigo el hilo.")])
        _patch_llm(monkeypatch, bound)

        assistant = WMSAssistant(db=None, tenant_id=uuid4(), user_id=uuid4())
        history = [
            {"role": "user", "content": "hola, soy Juan"},
            {"role": "assistant", "content": "hola Juan, ¿en qué te ayudo?"},
        ]
        await assistant._agentic_response("¿recuerdas mi nombre?", history=history)

        sent_messages = bound.invocations[0]
        # System + 2 turnos de historial + mensaje nuevo = 4
        assert len(sent_messages) == 4
        assert sent_messages[1].content == "hola, soy Juan"
        assert sent_messages[2].content == "hola Juan, ¿en qué te ayudo?"
        assert sent_messages[3].content == "¿recuerdas mi nombre?"

    async def test_stops_after_max_iterations(self, monkeypatch):
        never_ending_call = {"name": "list_active_alerts", "args": {}, "id": "call_x"}
        # El LLM SIEMPRE pide una tool — nunca da respuesta final.
        responses = [_FakeAIMessage(tool_calls=[never_ending_call]) for _ in range(MAX_TOOL_ITERATIONS)]
        bound = _FakeBoundLLM(responses)
        _patch_llm(monkeypatch, bound)

        call_count = {"n": 0}

        async def fake_execute_tool(name, args, ctx):
            call_count["n"] += 1
            return {"ok": True}

        monkeypatch.setattr(ai_tools, "execute_tool", fake_execute_tool)

        assistant = WMSAssistant(db=None, tenant_id=uuid4(), user_id=uuid4())
        text, trace, _ = await assistant._agentic_response("hazlo", history=[])

        assert call_count["n"] == MAX_TOOL_ITERATIONS
        assert len(trace) == MAX_TOOL_ITERATIONS
        assert "No pude completar" in text

    async def test_falls_back_to_templates_without_api_key(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "")
        assistant = WMSAssistant(db=None, tenant_id=uuid4(), user_id=uuid4())

        async def fake_gather_context(message, context_type, context_id):
            return {}

        monkeypatch.setattr(assistant, "_gather_context", fake_gather_context)
        text, sources, tokens = await assistant._generate_response(
            "hola", conversation=None, history=[], context_type=None, context_id=None,
        )
        assert sources == []
        assert tokens == 0
        assert "Asistente WMS Panama" in text
