#!/usr/bin/env python3
"""
WMS Panamá — Controlador local del gateway LLRP (Fase 2)
============================================================
Servidor HTTP LOCAL (127.0.0.1) que el botón "Iniciar Lectura" / "Detener
Lectura" de la vista Pruebas RFID llama directamente desde el navegador —
NO pasa por el backend Docker, porque ese backend no tiene acceso de red al
reader físico (solo ESTA máquina lo tiene, vía el adaptador conectado al
switch del reader).

Este controlador simplemente inicia/detiene `rfid_llrp_gateway.py` como
subproceso bajo pedido, sin límite de duración — el frontend lo detiene
explícitamente cuando el usuario presiona "Detener Lectura".

IMPORTANTE: debe estar corriendo en ESTA máquina (la conectada al switch del
reader) para que los botones de la UI funcionen. Si no está corriendo, el
botón "Iniciar Lectura" mostrará un error claro en vez de fallar en silencio.

Uso:
    python rfid_gateway_controller.py
    (déjalo corriendo en una terminal mientras uses los botones de la UI;
    Ctrl+C para detenerlo — también detiene el gateway si estaba activo)
"""

from __future__ import annotations

import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PORT = 8765
GATEWAY_SCRIPT = Path(__file__).parent / "rfid_llrp_gateway.py"

_lock = threading.Lock()
_process: subprocess.Popen | None = None


def _is_running() -> bool:
    return _process is not None and _process.poll() is None


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        import json
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 — nombre exigido por BaseHTTPRequestHandler
        self._json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/status":
            self._json(200, {"running": _is_running()})
        else:
            self._json(404, {"error": "ruta no encontrada"})

    def do_POST(self) -> None:  # noqa: N802
        global _process
        if self.path == "/start":
            with _lock:
                if _is_running():
                    self._json(200, {"running": True, "message": "ya estaba corriendo"})
                    return
                print("▶️  Iniciando rfid_llrp_gateway.py (sesión de lectura)...")
                _process = subprocess.Popen(
                    [sys.executable, str(GATEWAY_SCRIPT)],
                    cwd=str(GATEWAY_SCRIPT.parent),
                )
            self._json(200, {"running": True})
        elif self.path == "/stop":
            with _lock:
                if _is_running():
                    print("🛑 Deteniendo rfid_llrp_gateway.py...")
                    _process.terminate()
                    try:
                        _process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        _process.kill()
                self._json(200, {"running": False})
        else:
            self._json(404, {"error": "ruta no encontrada"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002 — silenciar el access log default
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"🎛️  Controlador del gateway RFID escuchando en http://127.0.0.1:{PORT}")
    print("   Déjalo corriendo mientras uses los botones Iniciar/Detener Lectura en la UI.")
    print("   Ctrl+C para salir (detiene el gateway si estaba activo).\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if _is_running():
            _process.terminate()
        print("\nControlador detenido.")


if __name__ == "__main__":
    main()
