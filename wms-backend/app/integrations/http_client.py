"""Cliente HTTP base para integraciones (async, con timeout y manejo de errores).

Si el endpoint no está configurado, NO realiza llamadas: devuelve un resultado
estructurado `configured=False`. Esto permite tener toda la lógica implementada
sin depender de credenciales reales en tiempo de desarrollo/pruebas.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.logging import get_logger
from app.integrations.config import EndpointConfig

log = get_logger(__name__)


async def call(cfg: EndpointConfig, method: str, path: str,
               json: Optional[dict] = None, params: Optional[dict] = None,
               timeout: float = 15.0) -> dict:
    """Realiza una llamada HTTP autenticada con Bearer token.

    Retorna {ok, configured, status_code?, data?, error?, missing?}.
    """
    if not cfg.configured:
        return {"ok": False, "configured": False, "missing": cfg.missing,
                "message": f"Integración {cfg.name} no configurada. Definir: {', '.join(cfg.missing)}."}
    try:
        import httpx
        url = cfg.base_url.rstrip("/") + "/" + path.lstrip("/")
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method.upper(), url, json=json, params=params, headers=headers)
        data: Any
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:2000]}
        return {"ok": resp.is_success, "configured": True,
                "status_code": resp.status_code, "data": data}
    except Exception as exc:  # red, DNS, timeout, etc.
        log.warning("integration_call_failed", integration=cfg.name, path=path, error=str(exc))
        return {"ok": False, "configured": True, "error": str(exc)}
